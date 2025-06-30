from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from pydantic import BaseModel
import boto3
import os
import json
from datetime import datetime
import pytz
from clients.strava_client import StravaClient
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.strava_credentials_helper import StravaCredentialsHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


class StravaWebhookEvent(BaseModel):
    aspect_type: str
    event_time: int
    object_id: int
    object_type: str
    owner_id: int
    subscription_id: int
    updates: dict = {}


@router.post(
    "/webhook",
    summary="Receive Strava webhook event and publish user_id/workout_id to SQS",
    response_description="Published Strava webhook info",
)
@exceptions_decorator
def strava_webhook_event(payload: StravaWebhookEvent, request: Request):
    strava_client = StravaClient(request_id=request.state.request_id)

    logger.info(
        f"Strava webhook verification request: method={request.method}, url={request.url}, headers={dict(request.headers)}, query_params={dict(request.query_params)}"
    )
    logger.info(f"Received Strava webhook event: {payload.dict()}")

    # Handle athlete events (no action, just return 200)
    if payload.object_type == "athlete":
        logger.info(
            "Strava webhook event is for athlete. Returning 200 OK (no action taken)."
        )
        return JSONResponse(
            content={"message": "Athlete event received. No action taken."},
            status_code=200,
        )

    # Handle activity events
    if payload.object_type == "activity":
        strava_profile_helper = StravaProfileHelper(request_id=request.state.request_id)
        workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)
        user_id = strava_profile_helper.get_user_id_by_strava_id(payload.owner_id)
        workout_id = payload.object_id

        if payload.aspect_type == "delete":
            deleted = workout_helper.delete_strava_workout(user_id, workout_id)
            if deleted:
                logger.info(
                    f"Deleted Strava workout {workout_id} for user_id {user_id}"
                )
                return JSONResponse(
                    content={
                        "message": f"Workout {workout_id} deleted for user {user_id}."
                    },
                    status_code=200,
                )
            else:
                logger.warning(f"Workout {workout_id} not found for user {user_id}.")
                return JSONResponse(
                    content={
                        "message": f"Workout {workout_id} not found for user {user_id}."
                    },
                    status_code=404,
                )
        elif payload.aspect_type in ("create", "update"):
            # Use get_full_activity_by_id to fetch the full activity from Strava
            logger.info(
                f"Received {payload.aspect_type} for workout {workout_id} for user_id {user_id}: {payload.updates}"
            )
            try:
                # Get user's Strava access token

                credentials_helper = StravaCredentialsHelper(
                    request_id=request.state.request_id
                )
                strava_credentials = credentials_helper.get_credentials(user_id=user_id)
                if not strava_credentials or "access_token" not in strava_credentials:
                    logger.error(f"Strava credentials not found for user_id: {user_id}")
                    return JSONResponse(
                        content={
                            "message": f"Strava credentials not found for user {user_id}."
                        },
                        status_code=404,
                    )
                access_token = strava_credentials["access_token"]
                # Fetch full activity from Strava
                activity = strava_client.get_full_activity_by_id(
                    access_token, workout_id
                )
                if not activity:
                    logger.error(
                        f"Activity {workout_id} not found on Strava for user {user_id}"
                    )
                    return JSONResponse(
                        content={
                            "message": f"Activity {workout_id} not found on Strava for user {user_id}."
                        },
                        status_code=404,
                    )
            except Exception as e:
                logger.error(
                    f"Failed to fetch activity {workout_id} for user {user_id}: {e}"
                )
                return JSONResponse(
                    content={
                        "message": f"Failed to fetch activity {workout_id} for user {user_id}: {e}"
                    },
                    status_code=500,
                )
            try:
                activity["id"] = workout_id
                workout, action = workout_helper.put_strava_workout(user_id, activity)
                logger.info(
                    f"{action.capitalize()}d Strava workout {workout_id} for user_id {user_id}"
                )
                response_data = {
                    "message": f"Workout {workout_id} {action}d for user {user_id}.",
                    "workout": StravaWorkoutHelper.serialize_model(workout),
                    "action": action,
                }
                return JSONResponse(
                    content=response_data,
                    status_code=200,
                )
            except Exception as e:
                logger.error(
                    f"Failed to {payload.aspect_type} workout {workout_id} for user {user_id}: {e}"
                )
                return JSONResponse(
                    content={
                        "message": f"Failed to {payload.aspect_type} workout {workout_id} for user {user_id}: {e}"
                    },
                    status_code=500,
                )
        else:
            # Handle other aspect_types if needed
            logger.info(f"Unhandled aspect_type: {payload.aspect_type}")
            return JSONResponse(
                content={"message": f"Unhandled aspect_type: {payload.aspect_type}"},
                status_code=200,
            )

    # If object_type is neither activity nor athlete, just return 200
    logger.info(
        f"Unknown object_type '{payload.object_type}'. Returning 200 OK (no action taken)."
    )
    return JSONResponse(
        content={
            "message": f"Unknown object_type '{payload.object_type}'. No action taken."
        },
        status_code=200,
    )
