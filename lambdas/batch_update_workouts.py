from aws_lambda_powertools import Logger
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.helpers.strava_credentials_helper import StravaCredentialsHelper
from clients.strava_client import StravaClient, StravaAuthCodeExchangeError
from dynamodb.models.strava_profile_model import StravaAthleteModel
from dynamodb.models.strava_credentials_model import StravaCredentialsModel
import requests
from datetime import datetime, timedelta
import os
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
import pytz
import base64
import json
import boto3

logger = Logger(service="workout-tracer-strava-batch-update")


def get_valid_strava_credentials(user_id, request_id, logger):
    credentials_helper = StravaCredentialsHelper(request_id=request_id)
    strava_credentials = credentials_helper.get_credentials(user_id=user_id)
    strava_client = StravaClient(request_id=request_id)
    if not strava_credentials:
        logger.warning(f"Strava credentials not found for user_id: {user_id}")
        return None

    if strava_credentials["expires_at"] < int(datetime.now().timestamp()):
        logger.info(
            f"Strava credentials for user_id {user_id} have expired. Refreshing..."
        )
        new_creds = strava_client.refresh_access_token(
            refresh_token=strava_credentials["refresh_token"]
        )
        if not new_creds:
            logger.error(f"Failed to refresh Strava credentials for user_id: {user_id}")
            return None

        strava_credentials = new_creds
        try:
            logger.info(f"Storing Strava credentials for user_id: {user_id}")
            credentials_helper.create_or_update_credentials(
                token_type=strava_credentials.get("token_type"),
                expires_at=strava_credentials.get("expires_at"),
                expires_in=strava_credentials.get("expires_in"),
                refresh_token=strava_credentials.get("refresh_token"),
                access_token=strava_credentials.get("access_token"),
                user_id=user_id,
            )
            logger.info("Successfully updated Strava credentials.")
        except Exception as e:
            logger.error(f"Error updating Strava credentials: {e}")
            return None
    return strava_credentials


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None)
    logger.append_keys(request_id=request_id)

    max_messages = event.get("max_messages", 550) if isinstance(event, dict) else 550

    sqs_queue_url = os.getenv("SQS_QUEUE_URL")
    if not sqs_queue_url:
        logger.error("SQS_QUEUE_URL environment variable not set.")
        return {"error": "SQS queue URL not configured."}

    sqs = boto3.client("sqs")

    messages = []
    while len(messages) < max_messages:
        resp = sqs.receive_message(
            QueueUrl=sqs_queue_url,
            MaxNumberOfMessages=min(10, max_messages - len(messages)),
            WaitTimeSeconds=1,
            VisibilityTimeout=60,
        )
        batch = resp.get("Messages", [])
        if not batch:
            break
        messages.extend(batch)
        if len(batch) < 10:
            break

    logger.info(f"Fetched {len(messages)} messages from SQS.")

    processed = 0
    errors = 0

    for msg in messages:
        strava_client = None
        try:
            body = json.loads(msg["Body"])
            user_id = body.get("user_id")
            workout_id = body.get("workout_id")
            logger.info(f"Processing user_id={user_id}, workout_id={workout_id}")

            # Use the helper to get valid credentials
            strava_credentials = get_valid_strava_credentials(
                user_id, request_id, logger
            )
            if not strava_credentials:
                logger.warning(
                    f"Strava credentials not found or could not be refreshed for user_id: {user_id}"
                )
                errors += 1
                continue

            strava_client = StravaClient(request_id=request_id)
            workout_data = strava_client.get_full_activity_by_id(
                activity_id=workout_id,
                access_token=strava_credentials["access_token"],
            )
            if not workout_data:
                logger.error(f"Failed to retrieve workout data for ID {workout_id}.")
                errors += 1
                continue

            workout_helper = StravaWorkoutHelper(request_id=request_id)
            _, action = workout_helper.put_strava_workout(
                user_id=user_id, workout_data=workout_data
            )
            logger.info(
                f"Workout {workout_id} for user {user_id} stored with action: {action}"
            )

            sqs.delete_message(
                QueueUrl=sqs_queue_url,
                ReceiptHandle=msg["ReceiptHandle"],
            )
            processed += 1

        except Exception as e:
            logger.error(
                f"Error processing message for user_id={body.get('user_id', 'unknown')}, workout_id={body.get('workout_id', 'unknown')}: {e}"
            )
            errors += 1

        finally:
            if strava_client:
                try:
                    strava_client.metrics.flush_metrics()
                except Exception as flush_error:
                    logger.warning(f"Error flushing metrics: {flush_error}")

    logger.info(f"Processed: {processed}, Errors: {errors}")
    return {
        "processed": processed,
        "errors": errors,
        "fetched_messages": len(messages),
    }
