from aws_lambda_powertools import Logger
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.strava_credentials_helper import StravaCredentialsHelper
from clients.strava_client import StravaClient
import os
import json
import boto3
from datetime import datetime
import pytz

logger = Logger(service="workout-tracer-strava-onboarding")


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None)
    logger.append_keys(request_id=request_id)

    user_id = event.get("user_id")
    if not user_id:
        logger.error("Missing user_id in event.")
        return {"error": "user_id is required."}

    sqs_queue_url = os.getenv("SQS_QUEUE_URL")
    if not sqs_queue_url:
        logger.error("SQS_QUEUE_URL environment variable not set.")
        return {"error": "SQS queue URL not configured."}

    # Get valid credentials for fetching activities
    credentials_helper = StravaCredentialsHelper(request_id=request_id)
    strava_credentials = credentials_helper.get_credentials(
        user_id=user_id, force_refresh=True
    )

    if not strava_credentials:
        return {"error": "Strava credentials not found or could not be refreshed."}

    strava_client = StravaClient(request_id=request_id)
    try:
        logger.info(f"Fetching Strava activities for user_id: {user_id}")
        activities = strava_client.get_athlete_activities(
            access_token=strava_credentials.get("access_token")
        )
        logger.info(
            f"Successfully fetched {len(activities)} Strava activities for user_id: {user_id}"
        )
    except Exception as e:
        logger.error(
            f"Error fetching Strava activities for user_id {user_id}: {e}",
            exc_info=True,
        )
        return {"error": f"Error fetching Strava activities: {e}"}

    sqs_client = boto3.client("sqs")
    workout_helper = StravaWorkoutHelper(request_id=request_id)
    request_time = datetime.now(pytz.UTC).isoformat()

    create_count = 0
    update_count = 0
    error_count = 0
    published_count = 0

    for activity in activities:
        # Get valid credentials for each activity (in case of long-running batch)
        if not strava_credentials:
            error_count += 1
            logger.error(
                f"Strava credentials not found or could not be refreshed for user_id: {user_id}"
            )
            continue

        try:
            _, action = workout_helper.put_strava_workout(
                user_id=user_id, workout_data=activity
            )
            if action == "create":
                create_count += 1
            elif action == "update":
                update_count += 1
        except Exception as e:
            error_count += 1
            logger.error(
                f"Failed to store activity for user_id {user_id}: {e}", exc_info=True
            )
            logger.error(activity)
            continue

        workout_id = activity.get("id")
        message = {
            "request_time": request_time,
            "user_id": user_id,
            "workout_id": workout_id,
        }
        try:
            sqs_client.send_message(
                QueueUrl=sqs_queue_url, MessageBody=json.dumps(message)
            )
            published_count += 1
            logger.debug(f"Published workout_id {workout_id} to SQS.")
        except Exception as e:
            error_count += 1
            logger.error(f"Failed to publish workout_id {workout_id} to SQS: {e}")

    logger.info(f"Processed {len(activities)} activities for user_id {user_id}.")
    return {
        "message": "Processed activities for user",
        "user_id": user_id,
        "workouts": {
            "created": create_count,
            "updated": update_count,
            "error_count": error_count,
        },
        "sqs_published": published_count,
    }
