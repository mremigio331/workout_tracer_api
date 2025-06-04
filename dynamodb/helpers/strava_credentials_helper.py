from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.helpers.audit_actions_helper import AuditActions, AuditActionHelper
from dynamodb.models.strava_credentials_model import StravaCredentialsModel
from cryptography.fernet import Fernet
import os
from datetime import datetime
import base64


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
        self.sk = "STRAVA_CREDENTIALS"
        self.audit_sk = "STRAVA_CREDENTIALS_AUDIT"
        self.strava_profile_helper = StravaProfileHelper()
        self.audit_action_helper = AuditActionHelper(request_id=request_id)
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
        Store encrypted Strava credentials in DynamoDB and audit the encrypted values.
        """
        encrypted_refresh_token = self.encrypt(refresh_token)
        encrypted_access_token = self.encrypt(access_token)

        now_iso = datetime.utcnow().isoformat()
        item = {
            "PK": f"#USER:{user_id}",
            "SK": self.sk,
            "token_type": token_type,
            "expires_at": expires_at,
            "expires_in": expires_in,
            "refresh_token": encrypted_refresh_token,
            "access_token": encrypted_access_token,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        # No need to convert datetime to string, already str

        try:
            # Fetch current credentials for audit (if any)
            before_item = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk}
            ).get("Item")
            before = StravaCredentialsModel(**before_item) if before_item else None

            self.table.put_item(Item=item)
            self.logger.info(f"Stored encrypted Strava credentials for {user_id}")

            # Ensure after is a model instance
            after = StravaCredentialsModel(
                token_type=token_type,
                expires_at=expires_at,
                expires_in=expires_in,
                refresh_token=encrypted_refresh_token,
                access_token=encrypted_access_token,
            )

            # Audit with model instances for before and after
            self.audit_action_helper.create_audit_record(
                user_id=user_id,
                sk=self.audit_sk,
                action=(
                    AuditActions.CREATE.value
                    if before is None
                    else AuditActions.UPDATE.value
                ),
                before=before,
                after=after,
            )
        except ClientError as e:
            self.logger.error(f"Error storing Strava credentials for {user_id}: {e}")
            raise

    def get_credentials(self, user_id: str) -> dict | None:
        """
        Retrieve and decrypt Strava credentials from DynamoDB.
        """
        try:
            response = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": self.sk}
            )
            item = response.get("Item")
            if not item:
                self.logger.warning(
                    f"No Strava credentials found for user_id: {user_id}"
                )
                return None
            decrypted = {
                "token_type": item["token_type"],
                "expires_at": item["expires_at"],
                "expires_in": item["expires_in"],
                "refresh_token": self.decrypt(item["refresh_token"]),
                "access_token": self.decrypt(item["access_token"]),
            }
            return decrypted
        except ClientError as e:
            self.logger.error(
                f"Error retrieving Strava credentials: {e.response['Error']['Message']}"
            )
            return None
        except Exception as e:
            self.logger.error(f"Error decrypting Strava credentials: {e}")
            return None
