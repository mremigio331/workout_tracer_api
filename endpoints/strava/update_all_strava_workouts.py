from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.helpers.strava_credentials_helper import StravaCredentialsHelper
from clients.strava_client import StravaClient, StravaAuthCodeExchangeError
from dynamodb.models.strava_profile_model import StravaAthleteModel
from dynamodb.models.strava_credentials_model import StravaCredentialsModel
from pydantic import BaseModel, Field
import requests
from datetime import datetime, timedelta
import os
import decimal
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
import pytz
import base64
import boto3
import json

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.post(
    "/strava/update_all_workouts",
    summary="Publish all Strava workouts to SQS",
    response_description="Published Strava workout info",
)
@exceptions_decorator
def update_all_strava_workouts(request: Request):
    user_id = getattr(request.state, "user_token", None)
    logger.info(f"Received batch update request: user_id={user_id}")
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    credentials_helper = StravaCredentialsHelper(request_id=request.state.request_id)
    strava_credentials = credentials_helper.get_credentials(user_id=user_id)
    strava_client = StravaClient(request_id=request.state.request_id)
    if not strava_credentials:
        logger.warning(f"Strava credentials not found for user_id: {user_id}")
        return JSONResponse(
            content={"error": "Strava credentials not found."}, status_code=404
        )

    if strava_credentials["expires_at"] < int(datetime.now().timestamp()):
        logger.info(
            f"Strava credentials for user_id {user_id} have expired. Refreshing..."
        )
        new_creds = strava_client.refresh_access_token(
            refresh_token=strava_credentials["refresh_token"]
        )
        if not new_creds:
            logger.error(f"Failed to refresh Strava credentials for user_id: {user_id}")
            return JSONResponse(
                content={"error": "Failed to refresh Strava credentials."},
                status_code=500,
            )
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
            return JSONResponse(
                content={"error": f"Error updating Strava credentials: {e}"},
                status_code=500,
            )

    logger.info(f"Fetching Strava workouts for user_id: {user_id}")

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    workout_ids = workout_helper.get_all_workout_ids(user_id=user_id)
    total = len(workout_ids)
    logger.info(f"Total workouts found for user_id={user_id}: {total}")

    # Publish all workout_ids to SQS
    sqs_queue_url = os.getenv("SQS_QUEUE_URL")
    if not sqs_queue_url:
        logger.error("SQS_QUEUE_URL environment variable not set.")
        return JSONResponse(
            content={"error": "SQS queue URL not configured."}, status_code=500
        )

    sqs_client = boto3.client("sqs")
    published_count = 0
    error_count = 0
    request_time = datetime.now(pytz.UTC).isoformat()

    for workout_id in workout_ids:
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
            logger.info(f"Published workout_id {workout_id} to SQS.")
        except Exception as e:
            error_count += 1
            logger.error(f"Failed to publish workout_id {workout_id} to SQS: {e}")

    response_content = {
        "published": published_count,
        "error_count": error_count,
        "identified_workout_ids": len(workout_ids),
        "total_workouts": total,
    }

    # If you use StravaClient in this endpoint, flush its metrics here.
    # Example:
    # if strava_client:
    #     strava_client.metrics.flush_metrics()

    return JSONResponse(
        content=response_content,
        status_code=200,
    )
