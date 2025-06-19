from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.models.user_profile_model import UserProfileModel
from datetime import datetime
from dynamodb.helpers.audit_actions_helper import AuditActions, AuditActionHelper
import os


class UserProfileHelper:
    """
    A class to interact with DynamoDB for the WorkoutTracer application.
    """

    def __init__(self, request_id: str = None):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger()
        if request_id:
            self.logger.append_keys(request_id=request_id)
        self.sk = "USER_PROFILE"
        self.audit_sk = "USER_PROFILE_AUDIT"
        self.audit_action_helper = AuditActionHelper(request_id=request_id)

    def create_user_profile(self, user_id: str, email: str, name: str):
        """
        Create a new user profile in DynamoDB.
        Assumes PK is '#USER:{user_id}' and SK is 'USER_PROFILE'.
        """
        profile = UserProfileModel(
            user_id=user_id,
            email=email,
            name=name,
            created_at=datetime.utcnow().isoformat(),  # always a string
            # cached_map_location will default to Manhattan if not provided
        )
        item = profile.dict()
        item["PK"] = f"#USER:{user_id}"
        item["SK"] = self.sk

        try:
            self.table.put_item(Item=item)
            self.logger.info(f"Created user profile for {user_id}: {item}")
            self.audit_action_helper.create_audit_record(
                user_id=user_id,
                sk=self.audit_sk,
                action=AuditActions.CREATE.value,
                before=None,
                after=profile,
            )
        except ClientError as e:
            self.logger.error(f"Error creating user profile for {user_id}: {e}")
            raise

    def get_user_profile(self, user_id: str) -> dict | None:
        """
        Fetch a user profile from DynamoDB by user_id.
        Returns a dict with user_id, email, name, and public_profile.
        """
        try:
            response = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk}
            )
            item = response.get("Item")
            if item:
                self.logger.info(f"Fetched user profile for {user_id}: {item}")
                pk_value = item.get("PK", "")
                user_id_value = (
                    pk_value.replace("#USER:", "")
                    if pk_value.startswith("#USER:")
                    else pk_value
                )
                result = {
                    "user_id": user_id_value,
                    "email": item.get("email"),
                    "name": item.get("name"),
                    "public_profile": item.get("public_profile"),
                    "created_at": item.get("created_at"),
                    "beta_features": item.get("beta_features", []),
                    "cached_map_location": item.get(
                        "cached_map_location", (40.7831, -73.9712)
                    ),
                }
                return result
            else:
                self.logger.info(f"No user profile found for {user_id}")
                return None
        except ClientError as e:
            self.logger.error(f"Error fetching user profile for {user_id}: {e}")
            raise

    def update_user_profile_fields(
        self,
        user_id: str,
        name: str = None,
        email: str = None,
        public_profile: bool = None,
        beta_features: bool = None,
        cached_map_location: tuple = None,
    ):
        """
        Update only the provided fields (name, email, public_profile, beta_features, cached_map_location) of the user profile.
        Only fields that are not None will be updated.
        """
        # Use locals() to build updated_changes dict
        updated_changes = {
            key: value
            for key, value in locals().items()
            if key not in ("self", "user_id") and value is not None
        }

        if not updated_changes:
            self.logger.info(f"No fields to update for user {user_id}")
            return None

        update_expr = []
        expr_attr_names = {}
        expr_attr_values = {}

        for key, value in updated_changes.items():
            placeholder_name = f"#{key[0]}"
            placeholder_value = f":{key}"
            update_expr.append(f"{placeholder_name} = {placeholder_value}")
            expr_attr_names[placeholder_name] = key
            expr_attr_values[placeholder_value] = value

        update_expression = "SET " + ", ".join(update_expr)

        try:
            # Fetch current profile for audit
            before_item = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk}
            ).get("Item")
            before = UserProfileModel(**before_item) if before_item else None

            response = self.table.update_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
                ReturnValues="ALL_NEW",
            )
            self.logger.info(
                f"Updated user profile fields for {user_id}: {response.get('Attributes')}"
            )
            if "Attributes" in response:
                attrs = response["Attributes"]
                after = UserProfileModel(**attrs)
                # Audit: before and after as UserProfileModel
                self.audit_action_helper.create_audit_record(
                    user_id=user_id,
                    sk=self.audit_sk,
                    action=AuditActions.UPDATE.value,
                    before=before,
                    after=after,
                )
                return after
            else:
                return None
        except ClientError as e:
            self.logger.error(f"Error updating user profile fields for {user_id}: {e}")
            raise
