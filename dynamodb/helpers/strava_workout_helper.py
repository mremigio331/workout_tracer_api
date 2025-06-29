from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.models.strava_workout_model import StravaWorkoutModel
import os
from decimal import Decimal
from datetime import datetime
from typing import Any, List, Dict
from dynamodb.helpers.audit_actions_helper import AuditActions, AuditActionHelper
from constants.general import SERVICE_NAME


class StravaWorkoutHelper:
    """
    Helper class to interact with DynamoDB for Strava workout/activity info.
    """

    def __init__(self, request_id: str = None):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger(service=SERVICE_NAME)
        if request_id:
            self.logger.append_keys(request_id=request_id)
        self.sk = "STRAVA_WORKOUT"
        self.audit_sk = "STRAVA_WORKOUT_AUDIT"
        self.audit_action_helper = AuditActionHelper(request_id=request_id)

    def put_strava_workout(
        self, user_id: int, workout_data: dict
    ) -> tuple[StravaWorkoutModel, str]:
        """
        Create or overwrite a Strava workout in DynamoDB.
        Returns a tuple: (StravaWorkoutModel, "create" or "update")
        Assumes PK is '#USER:{user_id}' and SK is 'STRAVA_WORKOUT#{workout_id}'.
        """
        workout = StravaWorkoutModel(**workout_data)
        workout_id = getattr(workout, "id", None)
        if not workout_id:
            self.logger.error("Workout data must include an 'id' field.")
            raise ValueError("Workout data must include an 'id' field.")

        sk = f"{self.sk}#{workout_id}"
        item = self.convert_floats_to_decimal(workout.dict())
        item["PK"] = f"#USER:{user_id}"
        item["SK"] = sk

        try:
            self.logger.info(
                f"Attempting to put workout for user_id={user_id}, workout_id={workout_id}"
            )
            self.logger.debug(f"Incoming workout_data: {workout_data}")

            before_item = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": sk}
            ).get("Item")
            action = "update" if before_item else "create"
            self.table.put_item(Item=item)
            self.logger.debug(
                f"Sucessfully Put Strava workout {workout_id} for {user_id}"
            )
            return workout, action
        except ClientError as e:
            self.logger.error(f"Error putting Strava workout for {user_id}: {e}")
            self.logger.error(f"Workout data that caused error: {workout_data}")
            self.logger.error(f"Item that caused error: {item}")
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error in put_strava_workout for user_id: {user_id}: {e}"
            )
            self.logger.error(f"Workout data that caused error: {workout_data}")
            self.logger.error(f"Item that caused error: {item}")
            raise

    def get_strava_workout(self, user_id: str, workout_id: int = None) -> dict | None:
        """
        Retrieve Strava workout from DynamoDB and return as a JSON-serializable dict.
        If workout_id is provided, fetch that specific workout.
        """
        try:
            sk = f"{self.sk}#{workout_id}" if workout_id else self.sk
            response = self.table.get_item(Key={"PK": f"#USER:{user_id}", "SK": sk})
            item = response.get("Item")
            if not item:
                self.logger.warning(
                    f"No Strava workout found for user_id: {user_id}, workout_id: {workout_id}"
                )
                return None
            item.pop("PK", None)
            item.pop("SK", None)
            return self._decimals_to_floats(item)
        except ClientError as e:
            self.logger.error(
                f"Error retrieving Strava workout: {e.response['Error']['Message']}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_strava_workout for user_id: {user_id}: {e}"
            )
            return None

    def get_all_workout_ids(self, user_id: str) -> List[int]:
        """
        Retrieve all Strava workout IDs for a user.
        Returns a list of workout IDs.
        """
        try:
            response = self.table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(
                    f"#USER:{user_id}"
                )
                & boto3.dynamodb.conditions.Key("SK").begins_with(self.sk)
            )
            items = response.get("Items", [])
            return [int(item["SK"].split("#")[-1]) for item in items if "SK" in item]
        except ClientError as e:
            self.logger.error(
                f"Error retrieving all Strava workout IDs for user_id {user_id}: {e}"
            )
            return []
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_all_workout_ids for user_id: {user_id}: {e}"
            )
            return []

    def get_all_workouts(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all Strava workouts for a user.
        Returns a list of workout dicts.
        """
        try:
            response = self.table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(
                    f"#USER:{user_id}"
                )
                & boto3.dynamodb.conditions.Key("SK").begins_with(self.sk)
            )
            items = response.get("Items", [])
            workouts = [self._decimals_to_floats(item) for item in items]
            return workouts
        except ClientError as e:
            self.logger.error(
                f"Error retrieving all Strava workouts for user_id {user_id}: {e}"
            )
            return []
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_all_workouts for user_id: {user_id}: {e}"
            )
            return []

    def delete_strava_workout(self, user_id: str, workout_id: int) -> bool:
        """
        Delete a Strava workout from DynamoDB.
        Returns True if deletion was successful, False otherwise.
        """
        sk = f"{self.sk}#{workout_id}"
        try:
            response = self.table.delete_item(
                Key={"PK": f"#USER:{user_id}", "SK": sk}, ReturnValues="ALL_OLD"
            )
            if "Attributes" in response:
                self.logger.info(
                    f"Successfully deleted Strava workout {workout_id} for user_id {user_id}"
                )
                return True
            else:
                self.logger.warning(
                    f"No Strava workout found for user_id: {user_id}, workout_id: {workout_id}"
                )
                return False
        except ClientError as e:
            self.logger.error(
                f"Error deleting Strava workout for user_id {user_id}, workout_id {workout_id}: {e}"
            )
            return False

    @staticmethod
    def convert_floats_to_decimal(obj):
        """
        Recursively convert all float values in a dict or list to Decimal,
        and all datetime objects to ISO 8601 strings.
        """
        if isinstance(obj, dict):
            return {
                k: StravaWorkoutHelper.convert_floats_to_decimal(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [StravaWorkoutHelper.convert_floats_to_decimal(v) for v in obj]
        elif isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return obj
        else:
            return obj

    @staticmethod
    def _decimals_to_floats(obj):
        """
        Recursively convert all Decimal values in a dict or list to float for JSON serialization.
        """
        if isinstance(obj, dict):
            return {
                k: StravaWorkoutHelper._decimals_to_floats(v) for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [StravaWorkoutHelper._decimals_to_floats(v) for v in obj]
        elif isinstance(obj, Decimal):
            return float(obj)
        else:
            return obj

    @staticmethod
    def serialize_model(model: Any) -> dict:
        if model is None:
            return None
        if isinstance(model, dict):
            return {k: StravaWorkoutHelper.serialize_model(v) for k, v in model.items()}
        elif isinstance(model, list):
            return [StravaWorkoutHelper.serialize_model(i) for i in model]
        elif isinstance(model, datetime):
            return model.isoformat()
        elif isinstance(model, Decimal):
            return float(model)
        elif hasattr(model, "dict"):
            return StravaWorkoutHelper.serialize_model(model.dict())
        return model
