from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError
from dynamodb.models.user_strava_model import UserStravaModel
import os
import base64
from decimal import Decimal
from datetime import datetime


class UserStravaHelper:
    """
    Helper class to interact with DynamoDB for Strava token/athlete info.
    """

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.kms_key_arn = os.getenv("KMS_KEY_ARN")
        self.kms_client = boto3.client("kms", region_name="us-west-2")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger()

    def _encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        response = self.kms_client.encrypt(
            KeyId=self.kms_key_arn,
            Plaintext=plaintext.encode("utf-8"),
        )
        ciphertext_blob = response["CiphertextBlob"]
        return base64.b64encode(ciphertext_blob).decode("utf-8")

    def _decrypt(self, ciphertext_b64: str) -> str:
        if not ciphertext_b64:
            return ""
        ciphertext_blob = base64.b64decode(ciphertext_b64)
        response = self.kms_client.decrypt(
            CiphertextBlob=ciphertext_blob,
            KeyId=self.kms_key_arn,
        )
        return response["Plaintext"].decode("utf-8")

    @staticmethod
    def convert_floats_to_decimal(obj):
        if isinstance(obj, dict):
            return {
                k: UserStravaHelper.convert_floats_to_decimal(v) for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [UserStravaHelper.convert_floats_to_decimal(v) for v in obj]
        elif isinstance(obj, float):
            return Decimal(str(obj))
        else:
            return obj

    @staticmethod
    def make_json_serializable(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {
                k: UserStravaHelper.make_json_serializable(v) for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [UserStravaHelper.make_json_serializable(v) for v in obj]
        return obj

    def get_user_strava(self, user_id: str) -> UserStravaModel | None:
        """
        Fetch Strava info for a user from DynamoDB.
        """
        try:
            response = self.table.get_item(
                Key={"PK": f"#USER:{user_id}", "SK": "STRAVA"}
            )
            item = response.get("Item")
            if item:
                self.logger.info(f"Fetched Strava info for {user_id}: {item}")
                # Decrypt sensitive fields
                token_type = (
                    self._decrypt(item.get("strava_token_type", ""))
                    if item.get("strava_token_type")
                    else None
                )
                refresh_token = (
                    self._decrypt(item.get("strava_refresh_token", ""))
                    if item.get("strava_refresh_token")
                    else None
                )
                access_token = (
                    self._decrypt(item.get("strava_access_token", ""))
                    if item.get("strava_access_token")
                    else None
                )
                tokens = {
                    "token_type": token_type,
                    "expires_at": item.get("strava_token_expires_at"),
                    "expires_in": item.get("strava_token_expires_in"),
                    "refresh_token": refresh_token,
                    "access_token": access_token,
                }
                athlete = item.get("strava_athlete")
                tokens["athlete"] = athlete if athlete else None
                return UserStravaModel(**tokens)
            else:
                self.logger.info(f"No Strava info found for {user_id}")
                return None
        except ClientError as e:
            self.logger.error(f"Error fetching Strava info for {user_id}: {e}")
            raise

    def _serialize_datetimes(self, obj):
        if isinstance(obj, dict):
            return {k: self._serialize_datetimes(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_datetimes(v) for v in obj]
        elif hasattr(obj, "isoformat"):
            return obj.isoformat()
        else:
            return obj

    def update_user_strava(
        self,
        user_id: str,
        token_type: str,
        expires_at: int,
        expires_in: int,
        refresh_token: str,
        access_token: str,
        athlete: dict,
    ):
        """
        Update all Strava token and athlete fields for a user. All fields required.
        Encrypt token_type, refresh_token, and access_token.
        """
        self.logger.info(f"Updating Strava info for user_id: {user_id}")

        athlete_serialized = self._serialize_datetimes(athlete)

        # Encrypt sensitive fields
        token_type_enc = self._encrypt(token_type)
        refresh_token_enc = self._encrypt(refresh_token)
        access_token_enc = self._encrypt(access_token)

        self.logger.info("Sensitive Strava tokens encrypted for storage.")

        update_expression = (
            "SET strava_token_type = :tt, strava_token_expires_at = :ea, "
            "strava_token_expires_in = :ei, strava_refresh_token = :rt, "
            "strava_access_token = :at, strava_athlete = :ath"
        )
        expr_attr_values = {
            ":tt": token_type_enc,
            ":ea": expires_at,
            ":ei": expires_in,
            ":rt": refresh_token_enc,
            ":at": access_token_enc,
            ":ath": athlete_serialized,
        }
        try:
            response = self.table.update_item(
                Key={"PK": f"#USER:{user_id}", "SK": "STRAVA"},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expr_attr_values,
                ReturnValues="ALL_NEW",
            )
            self.logger.info(f"Strava info updated in DynamoDB for user_id: {user_id}")
            if "Attributes" in response:
                attrs = response["Attributes"]
                # Decrypt for return
                tokens = {
                    "token_type": (
                        self._decrypt(attrs.get("strava_token_type", ""))
                        if attrs.get("strava_token_type")
                        else None
                    ),
                    "expires_at": attrs.get("strava_token_expires_at"),
                    "expires_in": attrs.get("strava_token_expires_in"),
                    "refresh_token": (
                        self._decrypt(attrs.get("strava_refresh_token", ""))
                        if attrs.get("strava_refresh_token")
                        else None
                    ),
                    "access_token": (
                        self._decrypt(attrs.get("strava_access_token", ""))
                        if attrs.get("strava_access_token")
                        else None
                    ),
                    "athlete": attrs.get("strava_athlete"),
                }
                self.logger.info(
                    f"Returning updated Strava info for user_id: {user_id}"
                )
                return UserStravaModel(**tokens)
            else:
                self.logger.warning(
                    f"No attributes returned after updating Strava info for user_id: {user_id}"
                )
                return None
        except ClientError as e:
            self.logger.error(f"Error updating Strava info for {user_id}: {e}")
            raise
