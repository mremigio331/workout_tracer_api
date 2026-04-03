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
    "/miles4manny/stats",
    summary="Get all Manny's workouts",
    response_description="Paginated list of Strava workouts",
)
@exceptions_decorator
def miles_for_manny_stats(
    request: Request,
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

    limit = 1000
    dynamo_next_token = None
    all_workouts = []
    while True:
        result = workout_helper.get_all_workouts(
            user_id=user_id, limit=limit, next_token=dynamo_next_token
        )
        workouts = result.get("workouts", [])
        # Only return workout type, distance info, and map data
        for workout in workouts:
            scrubbed_workout = {
                "type": workout.get("type"),
                "sport_type": workout.get("sport_type"),
                "distance": workout.get("distance"),
                "total_elevation_gain": workout.get("total_elevation_gain"),
                "moving_time": workout.get("moving_time"),
                "elapsed_time": workout.get("elapsed_time"),
            }
            all_workouts.append(scrubbed_workout)
        returned_next_token = result.get("next_token")
        logger.info(f"Returned next_token from DynamoDB: {returned_next_token}")
        if returned_next_token:
            if isinstance(returned_next_token, dict):
                new_next_token = base64.urlsafe_b64encode(
                    json.dumps(returned_next_token).encode()
                ).decode()
                dynamo_next_token = returned_next_token
            else:
                logger.warning(
                    f"Returned next_token is not a dict: {returned_next_token}"
                )
                new_next_token = None
                break
        else:
            new_next_token = None
            logger.info("No new token, this is the last page.")
            break

    # Aggregate stats by unique type
    stats_by_type = {}
    for workout in all_workouts:
        wtype = workout.get("type") or "unknown"
        if wtype not in stats_by_type:
            stats_by_type[wtype] = {
                "type": wtype,
                "total_distance": 0.0,
                "total_elevation_gain": 0.0,
                "total_moving_time": 0,
                "total_elapsed_time": 0,
                "count": 0,
            }
        stats_by_type[wtype]["total_distance"] += workout.get("distance") or 0.0
        stats_by_type[wtype]["total_elevation_gain"] += (
            workout.get("total_elevation_gain") or 0.0
        )
        stats_by_type[wtype]["total_moving_time"] += workout.get("moving_time") or 0
        stats_by_type[wtype]["total_elapsed_time"] += workout.get("elapsed_time") or 0
        stats_by_type[wtype]["count"] += 1

    # Convert to list for response
    stats_list = list(stats_by_type.values())

    return JSONResponse(
        content={
            "stats": stats_list,
            "total_workouts": len(all_workouts),
        },
        status_code=200,
    )
