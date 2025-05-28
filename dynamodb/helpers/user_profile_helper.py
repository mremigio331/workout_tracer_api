from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.models.user_profile_model import UserProfileModel
from datetime import datetime
import os


class UserProfileHelper:
    """
    A class to interact with DynamoDB for the WorkoutTracer application.
    """

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger()

    def create_user_profile(self, user_id: str, email: str, name: str):
        """
        Create a new user profile in DynamoDB.
        Assumes PK is 'USER#{user_id}' and SK is 'PROFILE'.
        """
        profile = UserProfileModel(
            user_id=user_id, email=email, name=name, created_at=datetime.utcnow()
        )
        item = profile.to_dynamodb()

        try:
            self.table.put_item(Item=item)
            self.logger.info(f"Created user profile for {user_id}: {item}")
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
                Key={"PK": f"#USER:{user_id}", "SK": "PROFILE"}
            )
            item = response.get("Item")
            if item:
                self.logger.info(f"Fetched user profile for {user_id}: {item}")
                # Extract user_id from PK
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
    ):
        """
        Update only the provided fields (name, email, public_profile) of the user profile.
        Only fields that are not None will be updated.
        """
        update_expr = []
        expr_attr_names = {}
        expr_attr_values = {}

        if name is not None:
            update_expr.append("#n = :name")
            expr_attr_names["#n"] = "name"
            expr_attr_values[":name"] = name
        if email is not None:
            update_expr.append("#e = :email")
            expr_attr_names["#e"] = "email"
            expr_attr_values[":email"] = email
        if public_profile is not None:
            update_expr.append("#p = :public_profile")
            expr_attr_names["#p"] = "public_profile"
            expr_attr_values[":public_profile"] = public_profile

        if not update_expr:
            self.logger.info(f"No fields to update for user {user_id}")
            return None

        update_expression = "SET " + ", ".join(update_expr)

        try:
            response = self.table.update_item(
                Key={"PK": f"#USER:{user_id}", "SK": "PROFILE"},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
                ReturnValues="ALL_NEW",
            )
            self.logger.info(
                f"Updated user profile fields for {user_id}: {response.get('Attributes')}"
            )
            if "Attributes" in response:
                # Convert flat dict to DynamoDB type-wrapped dict
                attrs = response["Attributes"]
                attrs_wrapped = {
                    k: (
                        {"S": v}
                        if isinstance(v, str)
                        else (
                            {"BOOL": v}
                            if isinstance(v, bool)
                            else {"N": str(v)} if isinstance(v, (int, float)) else v
                        )
                    )
                    for k, v in attrs.items()
                }
                return UserProfileModel.from_dynamodb(attrs_wrapped)
            else:
                return None
        except ClientError as e:
            self.logger.error(f"Error updating user profile fields for {user_id}: {e}")
            raise
