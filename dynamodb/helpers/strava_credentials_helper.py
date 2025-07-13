from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.models.strava_credentials_model import StravaCredentialsModel
from cryptography.fernet import Fernet
import os
from datetime import datetime
import base64
from clients.strava_client import StravaClient


class StravaCredentialsHelper:
    """
    Helper class to interact with DynamoDB for Strava API credentials.
    Encrypts and decrypts sensitive API info.
    """

    def __init__(self, request_id: str = None):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger()
        if request_id:
            self.logger.append_keys(request_id=request_id)
        self.request_id = request_id
        self.sk = "STRAVA_CREDENTIALS"
        self.audit_sk = "STRAVA_CREDENTIALS_AUDIT"
        self.strava_profile_helper = StravaProfileHelper()
        self.kms_key_arn = os.getenv("KMS_KEY_ARN")
        self.kms_client = boto3.client("kms", region_name="us-west-2")

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        response = self.kms_client.encrypt(
            KeyId=self.kms_key_arn,
            Plaintext=plaintext.encode("utf-8"),
        )
        ciphertext_blob = response["CiphertextBlob"]
        return base64.b64encode(ciphertext_blob).decode("utf-8")

    def decrypt(self, ciphertext_b64: str) -> str:
        if not ciphertext_b64:
            return ""
        ciphertext_blob = base64.b64decode(ciphertext_b64)
        response = self.kms_client.decrypt(
            CiphertextBlob=ciphertext_blob,
            KeyId=self.kms_key_arn,
        )
        return response["Plaintext"].decode("utf-8")

    def create_or_update_credentials(
        self,
        user_id: str,
        token_type: str,
        expires_at: int,
        expires_in: int,
        refresh_token: str,
        access_token: str,
    ):
        """
        Store encrypted Strava credentials in DynamoDB.
        """
        encrypted_refresh_token = self.encrypt(refresh_token)
        encrypted_access_token = self.encrypt(access_token)

        now_iso = datetime.utcnow().isoformat()
        item = {
            "PK": f"USER#{user_id}",
            "SK": self.sk,
            "token_type": token_type,
            "expires_at": expires_at,
            "expires_in": expires_in,
            "refresh_token": encrypted_refresh_token,
            "access_token": encrypted_access_token,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        try:
            # Fetch current credentials for audit (if any)
            before_item = self.table.get_item(
                Key={"PK": f"USER#{user_id}", "SK": self.sk}
            ).get("Item")

            self.table.put_item(Item=item)
            self.logger.info(f"Stored encrypted Strava credentials for {user_id}")
        except ClientError as e:
            self.logger.error(f"Error storing Strava credentials for {user_id}: {e}")
            raise

    def get_credentials(self, user_id: str, force_refresh: bool = False) -> dict | None:
        """
        Retrieve and decrypt Strava credentials from DynamoDB.
        If expired or force_refresh is True, refresh using StravaClient and update DynamoDB.
        Scans all pages if needed (handles LastEvaluatedKey).
        """
        try:
            last_evaluated_key = None
            while True:
                if last_evaluated_key:
                    response = self.table.scan(
                        FilterExpression="PK = :pk AND SK = :sk",
                        ExpressionAttributeValues={
                            ":pk": f"USER#{user_id}",
                            ":sk": self.sk,
                        },
                        ProjectionExpression="token_type,expires_at,expires_in,refresh_token,access_token",
                        ExclusiveStartKey=last_evaluated_key,
                    )
                else:
                    response = self.table.scan(
                        FilterExpression="PK = :pk AND SK = :sk",
                        ExpressionAttributeValues={
                            ":pk": f"USER#{user_id}",
                            ":sk": self.sk,
                        },
                        ProjectionExpression="token_type,expires_at,expires_in,refresh_token,access_token",
                    )
                items = response.get("Items", [])
                if items:
                    item = items[0]
                    break
                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    self.logger.warning(
                        f"No Strava credentials found for user_id: {user_id} after scanning all pages."
                    )
                    return None

            decrypted = {
                "token_type": item["token_type"],
                "expires_at": item["expires_at"],
                "expires_in": item["expires_in"],
                "refresh_token": self.decrypt(item["refresh_token"]),
                "access_token": self.decrypt(item["access_token"]),
            }
            # Check if expired or force_refresh is True, and refresh if needed
            if (
                decrypted["expires_at"] < int(datetime.now().timestamp())
                or force_refresh
            ):
                self.logger.info(
                    f"Strava credentials for user_id {user_id} have expired or force_refresh requested. Refreshing..."
                )
                strava_client = StravaClient(request_id=self.request_id)
                new_creds = strava_client.refresh_access_token(
                    refresh_token=decrypted["refresh_token"]
                )
                if not new_creds:
                    self.logger.error(
                        f"Failed to refresh Strava credentials for user_id: {user_id}"
                    )
                    return None
                try:
                    self.logger.info(
                        f"Storing refreshed Strava credentials for user_id: {user_id}"
                    )
                    self.create_or_update_credentials(
                        token_type=new_creds.get("token_type"),
                        expires_at=new_creds.get("expires_at"),
                        expires_in=new_creds.get("expires_in"),
                        refresh_token=new_creds.get("refresh_token"),
                        access_token=new_creds.get("access_token"),
                        user_id=user_id,
                    )
                    self.logger.info("Successfully updated Strava credentials.")
                    decrypted = new_creds
                except Exception as e:
                    self.logger.error(f"Error updating Strava credentials: {e}")
                    return None
            return decrypted
        except ClientError as e:
            self.logger.error(
                f"Error retrieving Strava credentials: {e.response['Error']['Message']}"
            )
            return None
        except Exception as e:
            self.logger.error(f"Error decrypting Strava credentials: {e}")
            return None
