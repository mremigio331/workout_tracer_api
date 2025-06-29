from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.models.strava_profile_model import StravaAthleteModel
import os
import base64
from decimal import Decimal
from datetime import datetime
from typing import Any
from dynamodb.helpers.audit_actions_helper import AuditActions, AuditActionHelper


class StravaProfileHelper:
    """
    Helper class to interact with DynamoDB for Strava athlete profile info.
    """

    def __init__(self, request_id: str = None):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger()
        if request_id:
            self.logger.append_keys(request_id=request_id)
        self.sk = "STRAVA_PROFILE"
        self.audit_sk = "STRAVA_PROFILE_AUDIT"
        self.audit_action_helper = AuditActionHelper(request_id=request_id)

    def create_strava_profile(
        self,
        user_id: str,
        strava_id: int = None,
        username: str = None,
        resource_state: int = None,
        firstname: str = None,
        lastname: str = None,
        bio: str = None,
        city: str = None,
        state: str = None,
        country: str = None,
        sex: str = None,
        premium: bool = None,
        summit: bool = None,
        created_at: str = None,
        updated_at: str = None,
        badge_type_id: int = None,
        weight: int = None,
        profile_medium: str = None,
        profile: str = None,
        friend: Any = None,
        follower: Any = None,
        webhook_onboarded: bool = False,
    ) -> StravaAthleteModel:
        """
        Create or update a Strava athlete profile in DynamoDB.
        Assumes PK is '#USER:{user_id}' and SK is 'STRAVA_PROFILE'.
        Raises an exception if strava_id already exists for another user.
        """
        # Check if strava_id already exists for a different user
        if strava_id is not None:
            existing_user_id = self.get_user_id_by_strava_id(strava_id)
            if existing_user_id is not None and str(existing_user_id) != str(user_id):
                error_msg = f"Strava ID {strava_id} is already associated with user_id {existing_user_id}."
                self.logger.error(error_msg)
                raise Exception(error_msg)
        # Build the model instance with ISO string for created_at/updated_at
        profile = StravaAthleteModel(
            user_id=user_id,
            strava_id=locals().get("strava_id"),
            username=locals().get("username"),
            resource_state=(
                int(locals().get("resource_state"))
                if locals().get("resource_state") is not None
                else None
            ),
            firstname=locals().get("firstname"),
            lastname=locals().get("lastname"),
            bio=locals().get("bio"),
            city=locals().get("city"),
            state=locals().get("state"),
            country=locals().get("country"),
            sex=locals().get("sex"),
            premium=locals().get("premium"),
            summit=locals().get("summit"),
            created_at=created_at if created_at is not None else self.to_iso_str(None),
            updated_at=updated_at if updated_at is not None else self.to_iso_str(None),
            badge_type_id=(
                int(locals().get("badge_type_id"))
                if locals().get("badge_type_id") is not None
                else None
            ),
            # Fix: Only cast to int if the value is a whole number, otherwise set to None or handle gracefully
            weight=(
                int(float(locals().get("weight")))
                if locals().get("weight") is not None
                and float(locals().get("weight")).is_integer()
                else None
            ),
            profile_medium=locals().get("profile_medium"),
            profile=locals().get("profile"),
            friend=locals().get("friend"),
            follower=locals().get("follower"),
            webhook_onboarded=locals().get("webhook_onboarded", False),  # Added field
        )
        item = self._decimals_to_floats(profile.dict())
        item["PK"] = f"#USER:{user_id}"
        item["SK"] = self.sk

        try:
            # Fetch current profile for audit (before)
            before_item = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk}
            ).get("Item")
            self.logger.info(f"Fetched before_item for audit: {before_item}")
            try:
                before = StravaAthleteModel(**before_item) if before_item else None
                self.logger.info(
                    f"Parsed before_item into StravaAthleteModel: {before}"
                )
            except Exception as parse_exc:
                self.logger.error(
                    f"Error parsing before_item into StravaAthleteModel: {parse_exc}"
                )
                before = None

            self.table.put_item(Item=item)
            self.logger.info(f"Created/Updated Strava profile for {user_id}: {item}")
            # Use audit_action_helper for audit (pass model instances, not dicts)

            self.audit_action_helper.create_audit_record(
                user_id=user_id,
                sk=self.audit_sk,
                action=(
                    AuditActions.CREATE.value
                    if before is None
                    else AuditActions.UPDATE.value
                ),
                before=None,
                after=profile,
            )
            self.logger.info(
                f"Successfully created audit record for user_id: {user_id}"
            )
            return profile
        except ClientError as e:
            self.logger.error(
                f"Error creating/updating Strava profile for {user_id}: {e}"
            )
            raise
        except Exception as e:
            self.logger.error(
                f"Unexpected error in create_strava_profile for user_id: {user_id}: {e}"
            )
            raise

    def get_strava_profile(self, user_id: str) -> dict | None:
        """
        Retrieve Strava athlete profile from DynamoDB and return as a JSON-serializable dict.
        """
        try:
            response = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk}
            )
            item = response.get("Item")
            if not item:
                self.logger.warning(f"No Strava profile found for user_id: {user_id}")
                return None
            # Remove PK and SK before returning
            item.pop("PK", None)
            item.pop("SK", None)
            # Convert Decimals to floats for JSON serialization
            return self._decimals_to_floats(item)
        except ClientError as e:
            self.logger.error(
                f"Error retrieving Strava profile: {e.response['Error']['Message']}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_strava_profile for user_id: {user_id}: {e}"
            )
            return None

    def update_strava_profile(
        self,
        user_id: int,
        strava_id: int = None,
        username: str = None,
        resource_state: int = None,
        firstname: str = None,
        lastname: str = None,
        bio: str = None,
        city: str = None,
        state: str = None,
        country: str = None,
        sex: str = None,
        premium: bool = None,
        summit: bool = None,
        created_at: str = None,
        updated_at: str = None,
        badge_type_id: int = None,
        weight: float = None,
        profile_medium: str = None,
        profile: str = None,
        friend: Any = None,
        follower: Any = None,
        webhook_onboarded: bool = None,  # Added field
    ):
        # Collect all non-None parameters except self and user_id
        updated_changes = {
            key: value
            for key, value in locals().items()
            if key not in ("self", "user_id") and value is not None
        }
        if not updated_changes:
            self.logger.info("No changes to update for user_id: %s", user_id)
            return None

        # Convert floats to Decimal before updating DynamoDB
        updated_changes = self.convert_floats_to_decimal(updated_changes)

        update_expr = "SET " + ", ".join(f"#{k} = :{k}" for k in updated_changes)
        expr_attr_names = {f"#{k}": k for k in updated_changes}
        expr_attr_values = {f":{k}": v for k, v in updated_changes.items()}

        try:
            # Fetch current profile for audit
            before_item = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk}
            ).get("Item")
            before = StravaAthleteModel(**before_item) if before_item else None

            response = self.table.update_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
                ReturnValues="ALL_NEW",
            )
            updated_item = response.get("Attributes")
            self.logger.info(
                f"Updated Strava profile for user_id: {user_id}: {updated_item}"
            )
            if updated_item:
                after = StravaAthleteModel(**updated_item)

                self.audit_action_helper.create_audit_record(
                    user_id=str(user_id),
                    sk=self.audit_sk,
                    action=AuditActions.UPDATE.value,
                    before=before,
                    after=after,
                )
                self.logger.info(
                    f"Successfully created audit record for user_id: {user_id}"
                )
                return after
            else:
                self.logger.warning(
                    f"No attributes returned after update for user_id: {user_id}"
                )
                return None
        except ClientError as e:
            self.logger.error(
                f"Error updating Strava profile: {e.response['Error']['Message']}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error in update_strava_profile for user_id: {user_id}: {e}"
            )
            return None

    def get_user_id_by_strava_id(self, strava_id: int) -> str | None:
        """
        Find the user_id for a given strava_id. Assumes 1-1 mapping.
        """
        try:
            response = self.table.scan(
                FilterExpression="strava_id = :sid AND SK = :sk",
                ExpressionAttributeValues={
                    ":sid": strava_id,
                    ":sk": self.sk,
                },
                ProjectionExpression="user_id",
            )
            items = response.get("Items", [])
            if items:
                return items[0].get("user_id")
            else:
                self.logger.warning(f"No user found for strava_id: {strava_id}")
                return None
        except ClientError as e:
            self.logger.error(
                f"Error finding user_id by strava_id: {e.response['Error']['Message']}"
            )
            return None
        except Exception as e:
            self.logger.error(
                f"Unexpected error in get_user_id_by_strava_id for strava_id: {strava_id}: {e}"
            )
            return None

    @staticmethod
    def to_iso_str(val):
        if val is None:
            return datetime.utcnow().isoformat()
        if isinstance(val, str):
            if val.endswith("Z"):
                val = val[:-1] + "+00:00"
            try:
                return datetime.fromisoformat(val).isoformat()
            except Exception:
                return val
        if isinstance(val, datetime):
            return val.isoformat()
        return str(val)

    @staticmethod
    def convert_floats_to_decimal(obj):
        """
        Recursively convert all float values in a dict or list to Decimal,
        and all datetime objects to ISO 8601 strings.
        """
        if isinstance(obj, dict):
            return {
                k: StravaProfileHelper.convert_floats_to_decimal(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [StravaProfileHelper.convert_floats_to_decimal(v) for v in obj]
        elif isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            # Convert Decimal to float for JSON serialization
            return str(obj)
        else:
            return obj

    @staticmethod
    def _decimals_to_floats(obj):
        """
        Recursively convert all Decimal values in a dict or list to float for JSON serialization.
        """
        if isinstance(obj, dict):
            return {
                k: StravaProfileHelper._decimals_to_floats(v) for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [StravaProfileHelper._decimals_to_floats(v) for v in obj]
        elif isinstance(obj, Decimal):
            return float(obj)
        else:
            return obj

    @staticmethod
    def serialize_model(model: Any) -> dict:
        """
        Recursively convert datetimes and Decimals in a model or dict to JSON-serializable types.
        """
        if model is None:
            return None
        if isinstance(model, dict):
            return {k: StravaProfileHelper.serialize_model(v) for k, v in model.items()}
        elif isinstance(model, list):
            return [StravaProfileHelper.serialize_model(i) for i in model]
        elif isinstance(model, datetime):
            return model.isoformat()
        elif isinstance(model, Decimal):
            return float(model)
        elif hasattr(model, "dict"):
            return StravaProfileHelper.serialize_model(model.dict())
        return model
