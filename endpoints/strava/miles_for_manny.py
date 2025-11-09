from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.user_profile_helper import UserProfileHelper
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
import base64
import json
import urllib.parse
import os

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/miles4manny",
    summary="Get all Manny's workouts",
    response_description="Paginated list of Strava workouts",
)
@exceptions_decorator
def miles_for_manny(
    request: Request,
    limit: int = Query(
        500, ge=1, le=500, description="Number of workouts to return (max 500)"
    ),
    next_token: str = Query(None, description="Token for fetching the next page"),
):
    stage = os.getenv("STAGE", "dev").lower()

    if stage == "prod":
        strava_id = "82708380"
    elif stage == "staging":
        strava_id = "106347208"
    elif stage == "dev":
        strava_id = "106347208"

    else:
        logger.error(f"Unknown STAGE value: {stage}")
        return JSONResponse(
            content={"error": "Server configuration error."}, status_code=500
        )

    strava_profile_helper = StravaProfileHelper(request_id=request.state.request_id)

    requested_user_profile_id = strava_profile_helper.get_user_id_by_strava_id(
        strava_id
    )

    if not requested_user_profile_id:
        logger.warning(
            f"User profile with strava_id {strava_id} not found for user_id {user_id}."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_profile_helper = UserProfileHelper(request_id=request.state.request_id)
    user_profile = user_profile_helper.get_user_profile(requested_user_profile_id)
    user_id = user_profile.get("user_id")

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    logger.info(f"Fetching workouts for user_id={user_id}")

    dynamo_next_token = None
    if next_token:
        logger.info(f"Raw incoming next_token: {next_token}")
        try:
            # Decode from URL encoding first
            decoded_url_token = urllib.parse.unquote(next_token)
            decoded_token = base64.urlsafe_b64decode(
                decoded_url_token.encode()
            ).decode()
            dynamo_next_token = json.loads(decoded_token)
            logger.info(f"Decoded next_token: {dynamo_next_token}")
        except Exception as e:
            logger.warning(
                f"Invalid next_token provided, defaulting to None. Exception: {e}"
            )
            dynamo_next_token = None

    result = workout_helper.get_all_workouts(
        user_id=user_id, limit=limit, next_token=dynamo_next_token
    )
    workouts = result.get("workouts", [])

    # Only return workout type, distance info, and map data
    scrubbed_workouts = []
    for workout in workouts:
        scrubbed_workout = {
            "type": workout.get("type"),
            "sport_type": workout.get("sport_type"),
            "distance": workout.get("distance"),
            "total_elevation_gain": workout.get("total_elevation_gain"),
            "map": workout.get("map"),
            "moving_time": workout.get("moving_time"),
            "elapsed_time": workout.get("elapsed_time"),
        }
        scrubbed_workouts.append(scrubbed_workout)

    returned_next_token = result.get("next_token")

    # Debug log for returned_next_token
    logger.info(f"Returned next_token from DynamoDB: {returned_next_token}")

    if returned_next_token:
        if isinstance(returned_next_token, dict):
            new_next_token = base64.urlsafe_b64encode(
                json.dumps(returned_next_token).encode()
            ).decode()
        else:
            logger.warning(f"Returned next_token is not a dict: {returned_next_token}")
            new_next_token = None
        if next_token and new_next_token == next_token:
            new_next_token = None
            logger.info("Next token unchanged, stopping pagination.")
        else:
            logger.info(
                f"Next query: /workouts?limit={limit}&next_token={new_next_token}"
            )
    else:
        new_next_token = None
        logger.info("No new token, this is the last page.")

    return JSONResponse(
        content={
            "limit": limit,
            "next_token": new_next_token,
            "workouts": scrubbed_workouts,
        },
        status_code=200,
    )
