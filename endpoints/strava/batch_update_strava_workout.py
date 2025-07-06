from fastapi import APIRouter, Request, Body
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

logger = Logger(service="workout-tracer-api")
router = APIRouter()


class BatchUpdateWorkoutRequest(BaseModel):
    """
    Model for the request body to batch update Strava workouts.

    - Provide a list of activity IDs to update.
    - Optionally, provide a timezone (IANA string, e.g. 'America/Los_Angeles'). Defaults to UTC.
    """

    activity_ids: list[int] = Field(
        ...,
        description="List of Strava activity IDs to update.",
    )


@router.post(
    "/strava/batch_update_workout",
    summary="Update a starva workout",
    response_description="Updated Strava workout info",
)
@exceptions_decorator
def batch_update_workout(
    activity_ids: BatchUpdateWorkoutRequest, request: Request = None
):
    user_id = getattr(request.state, "user_token", None)
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

    logger.info(f"Fetching Strava workouts for user_id: {user_id}")

    strava_workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    strava_client = StravaClient(request_id=request.state.request_id)

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)

    try:
        create_count = 0
        update_count = 0
        error_count = 0

        for activity in activity_ids.activity_ids:
            try:
                logger.info(
                    f"Attempting to update Strava workout with ID {activity} for user {user_id}."
                )
                workout_data = strava_client.get_full_activity_by_id(
                    activity_id=activity,
                    access_token=strava_credentials["access_token"],
                )
                if not workout_data:
                    logger.error(f"Failed to retrieve workout data for ID {activity}.")
                    return JSONResponse(
                        content={"error": "Failed to retrieve workout data."},
                        status_code=404,
                    )
                logger.info(f"Successfully retrieved workout data for ID {activity}.")

                _, action = workout_helper.put_strava_workout(
                    user_id=user_id, workout_data=workout_data
                )
                if action == "create":
                    create_count += 1
                elif action == "update":
                    update_count += 1
            except Exception as e:
                error_count += 1
                logger.error(workout_data)
                logger.error(f"Failed to store activity for user_id {user_id}: {e}")

        # Flush metrics after processing all activities
        strava_client.metrics.flush_metrics()

        return JSONResponse(
            content={
                "created": create_count,
                "updated": update_count,
                "error_count": error_count,
            },
            status_code=200,
        )
    except requests.RequestException as e:
        logger.error(f"Error fetching Strava activities: {e}")
        # Also flush metrics on error
        strava_client.metrics.flush_metrics()
        return JSONResponse(
            content={"error": "Error fetching Strava activities."}, status_code=500
        )
