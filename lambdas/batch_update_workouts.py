from aws_lambda_powertools import Logger
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.helpers.strava_credentials_helper import StravaCredentialsHelper
from clients.strava_client import StravaClient, StravaAuthCodeExchangeError
from dynamodb.models.strava_profile_model import StravaAthleteModel
from dynamodb.models.strava_credentials_model import StravaCredentialsModel
from aws_lambda_powertools.metrics import Metrics, MetricUnit
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

    return strava_credentials


def user_exists_in_cognito(user_id):
    client = boto3.client("cognito-idp")
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    if not user_pool_id:
        return False
    try:
        response = client.admin_get_user(UserPoolId=user_pool_id, Username=user_id)
        return True
    except client.exceptions.UserNotFoundException:
        return False
    except Exception as e:
        logger.error(f"Error checking Cognito user existence: {e}")
        return False


def lambda_handler(event, context):
    stage = os.getenv("STAGE")
    request_id = getattr(context, "aws_request_id", None)
    logger.append_keys(request_id=request_id)

    metrics = Metrics(
        namespace=f"WorkoutTracer-{stage}", service="workout_tracer_batch_update"
    )

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
    deleted_user_not_exist = 0

    for msg in messages:
        strava_client = None
        try:
            body = json.loads(msg["Body"])
            user_id = body.get("user_id")
            workout_id = body.get("workout_id")
            logger.info(f"Processing user_id={user_id}, workout_id={workout_id}")

            # Check if user exists in Cognito
            if not user_exists_in_cognito(user_id):
                logger.warning(
                    f"User {user_id} does not exist in Cognito. Deleting message from SQS."
                )
                sqs.delete_message(
                    QueueUrl=sqs_queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
                deleted_user_not_exist += 1
                metrics.add_metric(
                    name="UserNotExistDelete", unit=MetricUnit.Count, value=1
                )
                metrics.flush_metrics()
                continue

            # Use the helper to get valid credentials
            credentials_helper = StravaCredentialsHelper(request_id=request_id)
            strava_credentials = credentials_helper.get_credentials(
                user_id=user_id, force_refresh=True
            )

            if not strava_credentials:
                logger.warning(
                    f"Strava credentials not found or could not be refreshed for user_id: {user_id}"
                )
                errors += 1
                metrics.add_metric(
                    name="PutWorkoutError", unit=MetricUnit.Count, value=1
                )
                metrics.flush_metrics()
                continue

            strava_client = StravaClient(request_id=request_id)
            workout_data = strava_client.get_full_activity_by_id(
                activity_id=workout_id,
                access_token=strava_credentials["access_token"],
            )
            if not workout_data:
                logger.error(f"Failed to retrieve workout data for ID {workout_id}.")
                errors += 1
                metrics.add_metric(
                    name="PutWorkoutError", unit=MetricUnit.Count, value=1
                )
                metrics.flush_metrics()
                continue

            workout_helper = StravaWorkoutHelper(request_id=request_id)
            _, action = workout_helper.put_strava_workout(
                user_id=user_id, workout_data=workout_data
            )
            logger.info(
                f"Workout {workout_id} for user {user_id} stored with action: {action}"
            )
            metrics.add_metric(name="PutWorkoutSuccess", unit=MetricUnit.Count, value=1)
            metrics.flush_metrics()

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
            metrics.add_metric(name="PutWorkoutError", unit=MetricUnit.Count, value=1)
            metrics.flush_metrics()

    logger.info(
        f"Processed: {processed}, Errors: {errors}, DeletedUserNotExist: {deleted_user_not_exist}"
    )
    return {
        "processed": processed,
        "errors": errors,
        "deleted_user_not_exist": deleted_user_not_exist,
        "fetched_messages": len(messages),
    }
