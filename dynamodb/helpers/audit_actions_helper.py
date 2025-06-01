from enum import Enum
from datetime import datetime
from typing import Any
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
import boto3
import os


class AuditActions(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class AuditActionHelper:
    """
    Helper class for managing audit actions.
    Provides methods to create audit entries for user profiles and Strava profiles.
    """

    def __init__(self):
        """
        Initializes the helper with a DynamoDB table.
        :param table: The DynamoDB table instance.
        """
        self.dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table_name = os.getenv("TABLE_NAME", "WorkoutTracer-UserTable-Staging")
        self.table = self.dynamodb.Table(table_name)
        self.logger = Logger()

    def create_audit_record(
        self, user_id: str, sk: str, action: str, before: Any, after: Any
    ) -> dict:
        """
        Create or append an audit record for user profile changes.
        Stores a list of audit actions under a single PK/SK.
        Expects 'before' and 'after' to be model instances or None.
        """
        pk = f"#USER:{user_id}"
        timestamp = datetime.utcnow().isoformat()
        audit_entry = {
            "action": action,
            "before": before.dict() if before else None,
            "after": after.dict() if after else None,
            "timestamp": timestamp,
        }

        try:
            # Try to get the existing audit record
            response = self.table.get_item(Key={"PK": pk, "SK": sk})
            item = response.get("Item")

            if item and "records" in item:
                # Append to existing records list
                records = item["records"]
                records.append(audit_entry)
                update_expr = "SET #records = :records"
                expr_attr_names = {"#records": "records"}
                expr_attr_values = {":records": records}
                self.table.update_item(
                    Key={"PK": pk, "SK": sk},
                    UpdateExpression=update_expr,
                    ExpressionAttributeNames=expr_attr_names,
                    ExpressionAttributeValues=expr_attr_values,
                )
                self.logger.info(f"Appended audit record for {user_id}: {audit_entry}")
                return {"PK": pk, "SK": sk, "records": records}
            else:
                # Create new audit record
                audit_item = {
                    "PK": pk,
                    "SK": sk,
                    "records": [audit_entry],
                }
                self.table.put_item(Item=audit_item)
                self.logger.info(
                    f"Created new audit record for {user_id}: {audit_item}"
                )
                return audit_item
        except ClientError as e:
            self.logger.error(f"Error creating audit record for {user_id}: {e}")
            raise
