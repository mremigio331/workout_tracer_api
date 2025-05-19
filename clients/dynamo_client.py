from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from constants.dynamodb import WORKOUT_TRACER_USER_TABLE

class WorkoutTracerDynamoDBClient:
    """
    A class to interact with DynamoDB for the WorkoutTracer application.
    """

    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb', region_name="us-west-2")
        self.table = self.dynamodb.Table(WORKOUT_TRACER_USER_TABLE)

        self.logger = Logger()

    def get_user_profile(self, user_id: str):
        """
        Fetch a user profile from DynamoDB by user_id.
        Assumes PK is 'USER#{user_id}' and SK is 'PROFILE'.
        """
        try:
            response = self.table.get_item(
                    Key={
                        'PK': '#USER:d8d183a0-5021-70d9-0045-19984f484e3a',
                        'SK': 'PROFILE'
                    }
                )
            self.logger.info(f"Fetched user profile for {user_id}: {response}")
            return response.get('Item')
        except ClientError as e:
            self.logger.error(f"Error fetching user profile for {user_id}: {e}")
            raise