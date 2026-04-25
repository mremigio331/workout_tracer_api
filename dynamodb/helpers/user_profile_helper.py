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

    def get_user_by_display_id(self, display_id: int) -> dict | None:
        """Look up a user profile by user_display_id via GSI. Returns the profile dict or None."""
        try:
            response = self.table.query(
                IndexName="UserDisplayIdIndex",
                KeyConditionExpression=boto3.dynamodb.conditions.Key(
                    "user_display_id"
                ).eq(display_id),
                Limit=1,
            )
            items = response.get("Items", [])
            if items:
                item = items[0]
                pk_value = item.get("PK", "")
                user_id_value = (
                    pk_value.replace("USER#", "")
                    if pk_value.startswith("USER#")
                    else pk_value
                )
                return {
                    "user_id": user_id_value,
                    "name": item.get("name"),
                    "email": item.get("email"),
                    "public_profile": item.get("public_profile"),
                    "user_display_id": item.get("user_display_id"),
                    "distance_unit": item.get("distance_unit", "Imperial"),
                    "created_at": item.get("created_at"),
                }
            return None
        except ClientError as e:
            self.logger.error(f"Error looking up user by display_id {display_id}: {e}")
            return None

    def create_user_profile(
        self, user_id: str, email: str, name: str, provider: str = "Cognito"
    ):
        """
        Create a new user profile in DynamoDB.
        Assumes PK is 'USER#{user_id}' and SK is 'USER_PROFILE'.
        The model auto-generates a 7-digit user_display_id; we retry on collision.
        """
        max_retries = 10
        for attempt in range(max_retries):
            profile = UserProfileModel(
                user_id=user_id,
                email=email,
                name=name,
                provider=provider,
                created_at=datetime.utcnow().isoformat(),
            )
            # Check uniqueness of the auto-generated display_id
            if not self.get_user_by_display_id(profile.user_display_id):
                break
            self.logger.warning(
                f"user_display_id collision ({profile.user_display_id}), retrying ({attempt + 1}/{max_retries})"
            )
        else:
            raise RuntimeError(
                f"Failed to generate unique user_display_id after {max_retries} retries"
            )
        item = profile.dict()
        item["PK"] = f"USER#{user_id}"
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
        Scans all pages if needed (handles LastEvaluatedKey).
        """
        try:
            last_evaluated_key = None
            while True:
                scan_kwargs = {
                    "FilterExpression": "PK = :pk AND SK = :sk",
                    "ExpressionAttributeValues": {
                        ":pk": f"USER#{user_id}",
                        ":sk": self.sk,
                    },
                }
                if last_evaluated_key:
                    scan_kwargs["ExclusiveStartKey"] = last_evaluated_key
                response = self.table.scan(**scan_kwargs)
                items = response.get("Items", [])
                if items:
                    item = items[0]
                    pk_value = item.get("PK", "")
                    user_id_value = (
                        pk_value.replace("USER#", "")
                        if pk_value.startswith("USER#")
                        else pk_value
                    )

                    # Backfill user_display_id if missing
                    display_id = item.get("user_display_id")
                    if display_id is None:
                        # Model validator auto-generates a 7-digit ID
                        display_id = UserProfileModel(
                            user_id=user_id_value,
                            email=item.get("email", "backfill@placeholder.com"),
                            name=item.get("name", "unknown"),
                            created_at=item.get("created_at", ""),
                        ).user_display_id
                        try:
                            self.table.update_item(
                                Key={"PK": item["PK"], "SK": self.sk},
                                UpdateExpression="SET user_display_id = :did",
                                ExpressionAttributeValues={":did": display_id},
                            )
                            self.logger.info(
                                f"Backfilled user_display_id={display_id} for {user_id_value}"
                            )
                        except ClientError as e:
                            self.logger.error(
                                f"Failed to backfill user_display_id for {user_id_value}: {e}"
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
                        "distance_unit": item.get("distance_unit", "Imperial"),
                        "user_display_id": int(display_id),
                    }
                    return result
                last_evaluated_key = response.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    self.logger.info(
                        f"No user profile found for {user_id} after scanning all pages."
                    )
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
        distance_unit: str = None,
        show_workout_source: bool = None,
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
                Key={"PK": f"USER#{user_id}", "SK": self.sk}
            ).get("Item")

            # Backfill user_display_id if missing on the existing item
            if before_item and "user_display_id" not in before_item:
                backfill_model = UserProfileModel(
                    user_id=before_item.get("user_id", user_id),
                    email=before_item.get("email", "backfill@placeholder.com"),
                    name=before_item.get("name", "unknown"),
                    created_at=before_item.get("created_at", ""),
                )
                backfill_id = backfill_model.user_display_id
                self.table.update_item(
                    Key={"PK": f"USER#{user_id}", "SK": self.sk},
                    UpdateExpression="SET user_display_id = :did",
                    ExpressionAttributeValues={":did": backfill_id},
                )
                before_item["user_display_id"] = backfill_id
                self.logger.info(
                    f"Backfilled user_display_id={backfill_id} for {user_id} during update"
                )

            before = UserProfileModel(**before_item) if before_item else None

            response = self.table.update_item(
                Key={"PK": f"USER#{user_id}", "SK": self.sk},
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

    def get_all_user_ids(self) -> list[str]:
        """
        Scan DynamoDB for all unique user IDs that have at least one Strava workout.
        Returns a list of user ID strings (without the USER# prefix).
        """
        user_ids = set()
        scan_kwargs = {
            "FilterExpression": boto3.dynamodb.conditions.Attr("PK").begins_with(
                "USER#"
            )
            & boto3.dynamodb.conditions.Attr("SK").begins_with("STRAVA_WORKOUT#"),
            "ProjectionExpression": "PK",
        }
        try:
            while True:
                response = self.table.scan(**scan_kwargs)
                for item in response.get("Items", []):
                    pk = item.get("PK", "")
                    if pk.startswith("USER#"):
                        user_ids.add(pk[len("USER#") :])
                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                scan_kwargs["ExclusiveStartKey"] = last_key
        except ClientError as e:
            self.logger.error(f"Error scanning for all user IDs: {e}")
            raise
        return list(user_ids)

    def get_public_profiles(self):
        """
        Return all user profiles where public_profile == True.
        """
        try:
            table_name = self.table.name
            client = boto3.client("dynamodb", region_name="us-west-2")
            paginator = client.get_paginator("scan")
            public_profiles = []
            for page in paginator.paginate(
                TableName=table_name,
                FilterExpression="attribute_exists(public_profile) AND public_profile = :val AND SK = :sk",
                ExpressionAttributeValues={
                    ":val": {"BOOL": True},
                    ":sk": {"S": self.sk},
                },
                ProjectionExpression="PK,#n,SK,user_display_id",
                ExpressionAttributeNames={"#n": "name"},
            ):
                items = page.get("Items", [])
                self.logger.info(f"Fetched {len(items)} items from DynamoDB scan")
                for item in items:
                    self.logger.info(f"Processing item: {item}")
                    profile = {
                        "user_id": item["PK"]["S"].replace("USER#", ""),
                        "name": item.get("name", {}).get("S"),
                        "user_display_id": (
                            int(item["user_display_id"]["N"])
                            if "user_display_id" in item
                            else None
                        ),
                    }
                    public_profiles.append(profile)
            self.logger.info(f"Fetched {len(public_profiles)} public profiles")
            return public_profiles
        except ClientError as e:
            self.logger.error(f"Error fetching public profiles: {e}")
            raise
