from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.models.apple_health_workout_model import AppleHealthWorkoutModel
from dynamodb.helpers.location_helper import LocationHelper
import os
from decimal import Decimal
from datetime import datetime
from typing import Any, List, Dict, Tuple
from constants.general import SERVICE_NAME


class AppleHealthWorkoutHelper:
    """
    Helper class to interact with DynamoDB for Apple Health workout info.
    """

    def __init__(self, request_id: str = None):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger(service=SERVICE_NAME)
        if request_id:
            self.logger.append_keys(request_id=request_id)
        self._location_helper = LocationHelper(request_id=request_id)

    @property
    def _kml_cache(self) -> Dict[str, bytes]:
        return self._location_helper._kml_cache

    def put_apple_health_workout(
        self, user_id: str, workout_data: dict
    ) -> tuple[AppleHealthWorkoutModel, str]:
        """
        Create or overwrite an Apple Health workout in DynamoDB.
        Returns a tuple: (AppleHealthWorkoutModel, "create" or "update")
        """
        workout = AppleHealthWorkoutModel(**workout_data)
        workout_uuid = workout.workout_uuid
        if not workout_uuid:
            self.logger.error("Workout data must include a 'workout_uuid' field.")
            raise ValueError("Workout data must include a 'workout_uuid' field.")

        pk = AppleHealthWorkoutModel.create_pk(user_id)
        sk = AppleHealthWorkoutModel.create_sk(workout_uuid)
        item = self.convert_floats_to_decimal(workout.dict())
        item["PK"] = pk
        item["SK"] = sk

        try:
            self.logger.info(
                f"Attempting to put Apple Health workout for user_id={user_id}, workout_uuid={workout_uuid}"
            )

            before_item = self.table.get_item(Key={"PK": pk, "SK": sk}).get("Item")
            action = "update" if before_item else "create"
            self.table.put_item(Item=item)
            self.logger.debug(
                f"Successfully put Apple Health workout {workout_uuid} for {user_id}"
            )

            # Enqueue enrichment if summary_polyline is present
            enrich_sqs_url = os.getenv("ENRICH_SQS_QUEUE_URL")
            if enrich_sqs_url and workout.summary_polyline:
                try:
                    import json

                    boto3.client("sqs").send_message(
                        QueueUrl=enrich_sqs_url,
                        MessageBody=json.dumps(
                            {
                                "user_id": user_id,
                                "workout_id": workout_uuid,
                                "source": "apple_health",
                            }
                        ),
                        MessageGroupId=str(user_id),
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to enqueue workout {workout_uuid} for enrichment: {e}"
                    )

            return workout, action
        except ClientError as e:
            self.logger.error(f"Error putting Apple Health workout for {user_id}: {e}")
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error in put_apple_health_workout for user_id: {user_id}: {e}"
            )
            raise

    def get_apple_health_workout(self, user_id: str, workout_uuid: str) -> dict | None:
        """
        Retrieve an Apple Health workout from DynamoDB and return as a JSON-serializable dict.
        """
        try:
            pk = AppleHealthWorkoutModel.create_pk(user_id)
            sk = AppleHealthWorkoutModel.create_sk(workout_uuid)
            response = self.table.get_item(Key={"PK": pk, "SK": sk})
            item = response.get("Item")
            if not item:
                self.logger.warning(
                    f"No Apple Health workout found for user_id: {user_id}, workout_uuid: {workout_uuid}"
                )
                return None
            item.pop("PK", None)
            item.pop("SK", None)
            return self._decimals_to_floats(item)
        except ClientError as e:
            self.logger.error(
                f"Error retrieving Apple Health workout: {e.response['Error']['Message']}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_apple_health_workout for user_id: {user_id}: {e}"
            )
            return None

    def get_all_workouts(
        self,
        user_id: str,
        limit: int = 500,
        next_token: dict = None,
        projection_expression: str = None,
        expression_attribute_names: dict = None,
    ) -> dict:
        """
        Retrieve up to 'limit' Apple Health workouts for a user.
        Returns a dict: { "workouts": [...], "next_token": ... }
        """
        try:
            pk = AppleHealthWorkoutModel.create_pk(user_id)
            sk_prefix = AppleHealthWorkoutModel.create_sk("")
            query_kwargs = {
                "KeyConditionExpression": boto3.dynamodb.conditions.Key("PK").eq(pk)
                & boto3.dynamodb.conditions.Key("SK").begins_with(sk_prefix),
                "Limit": limit,
            }
            if next_token:
                query_kwargs["ExclusiveStartKey"] = next_token
            if projection_expression:
                query_kwargs["ProjectionExpression"] = projection_expression
            if expression_attribute_names:
                query_kwargs["ExpressionAttributeNames"] = expression_attribute_names

            response = self.table.query(**query_kwargs)
            items = response.get("Items", [])
            workouts = [self._decimals_to_floats(item) for item in items]
            result = {"workouts": workouts}
            last_evaluated_key = response.get("LastEvaluatedKey")

            if items and last_evaluated_key:
                if next_token and last_evaluated_key == next_token:
                    self.logger.warning(
                        "LastEvaluatedKey is same as ExclusiveStartKey, breaking pagination loop."
                    )
                    result["next_token"] = None
                else:
                    result["next_token"] = last_evaluated_key
            else:
                result["next_token"] = None
            return result
        except ClientError as e:
            self.logger.error(
                f"Error retrieving all Apple Health workouts for user_id {user_id}: {e}"
            )
            return {"workouts": [], "next_token": None}
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_all_workouts for user_id: {user_id}: {e}"
            )
            return {"workouts": [], "next_token": None}

    def get_all_workout_ids(self, user_id: str) -> List[str]:
        """
        Retrieve all Apple Health workout UUIDs for a user.
        Returns a list of UUID strings.
        """
        try:
            ids = []
            pk = AppleHealthWorkoutModel.create_pk(user_id)
            sk_prefix = AppleHealthWorkoutModel.create_sk("")
            query_kwargs = {
                "KeyConditionExpression": boto3.dynamodb.conditions.Key("PK").eq(pk)
                & boto3.dynamodb.conditions.Key("SK").begins_with(sk_prefix),
                "ProjectionExpression": "SK",
            }
            while True:
                response = self.table.query(**query_kwargs)
                ids.extend(
                    item["SK"].split("#", 1)[-1]
                    for item in response.get("Items", [])
                    if "SK" in item
                )
                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                query_kwargs["ExclusiveStartKey"] = last_key
            return ids
        except ClientError as e:
            self.logger.error(
                f"Error retrieving all Apple Health workout IDs for user_id {user_id}: {e}"
            )
            return []
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_all_workout_ids for user_id: {user_id}: {e}"
            )
            return []

    def delete_apple_health_workout(self, user_id: str, workout_uuid: str) -> bool:
        """
        Delete an Apple Health workout from DynamoDB.
        Returns True if deletion was successful, False otherwise.
        """
        pk = AppleHealthWorkoutModel.create_pk(user_id)
        sk = AppleHealthWorkoutModel.create_sk(workout_uuid)
        try:
            response = self.table.delete_item(
                Key={"PK": pk, "SK": sk}, ReturnValues="ALL_OLD"
            )
            if "Attributes" in response:
                self.logger.info(
                    f"Successfully deleted Apple Health workout {workout_uuid} for user_id {user_id}"
                )
                return True
            else:
                self.logger.warning(
                    f"No Apple Health workout found for user_id: {user_id}, workout_uuid: {workout_uuid}"
                )
                return False
        except ClientError as e:
            self.logger.error(
                f"Error deleting Apple Health workout for user_id {user_id}, workout_uuid {workout_uuid}: {e}"
            )
            return False

    def update_workout_locations(
        self, user_id: str, workout_uuid: str, locations: dict
    ) -> bool:
        """
        Updates only the `locations` field on a stored Apple Health workout in DynamoDB.
        """
        pk = AppleHealthWorkoutModel.create_pk(user_id)
        sk = AppleHealthWorkoutModel.create_sk(workout_uuid)
        try:
            self.table.update_item(
                Key={"PK": pk, "SK": sk},
                UpdateExpression="SET #loc = :locations",
                ExpressionAttributeNames={"#loc": "locations"},
                ExpressionAttributeValues={":locations": locations},
            )
            self.logger.info(
                f"Updated locations for Apple Health workout {workout_uuid}, user {user_id}"
            )
            return True
        except ClientError as e:
            self.logger.error(
                f"Error updating locations for workout {workout_uuid}, user {user_id}: {e}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"Unexpected error updating locations for workout {workout_uuid}, user {user_id}: {e}"
            )
            return False

    def get_location_badges(
        self, workout_polyline: str, kml_file_name: str
    ) -> Dict[str, bool]:
        """
        Given an encoded polyline and a KML file name in S3, returns a dict
        mapping each location name to True/False based on route intersection.
        Delegates to the shared LocationHelper.
        """
        return self._location_helper.get_location_badges(
            workout_polyline, kml_file_name
        )

    @staticmethod
    def convert_floats_to_decimal(obj):
        """
        Recursively convert all float values in a dict or list to Decimal,
        and all datetime objects to ISO 8601 strings.
        """
        if isinstance(obj, dict):
            return {
                k: AppleHealthWorkoutHelper.convert_floats_to_decimal(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [AppleHealthWorkoutHelper.convert_floats_to_decimal(v) for v in obj]
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
                k: AppleHealthWorkoutHelper._decimals_to_floats(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [AppleHealthWorkoutHelper._decimals_to_floats(v) for v in obj]
        elif isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        else:
            return obj
