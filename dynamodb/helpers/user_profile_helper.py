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

    def get_user_profile(self, user_id: str) -> UserProfileModel | None:
        """
        Fetch a user profile from DynamoDB by user_id.
        """
        try:
            response = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": "PROFILE"}
            )
            item = response.get("Item")
            if item:
                self.logger.info(f"Fetched user profile for {user_id}: {item}")
                return UserProfileModel.from_dynamodb(item)
            else:
                self.logger.info(f"No user profile found for {user_id}")
                return None
        except ClientError as e:
            self.logger.error(f"Error fetching user profile for {user_id}: {e}")
            raise
