from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.user_profile_helper import UserProfileHelper
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/public_workout_locations/{strava_id}",
    summary="Get a summary of all locations a public user has worked out in",
    response_description="Location summary broken down by sport type",
)
@exceptions_decorator
def get_public_workout_locations(strava_id: str, request: Request):
    requestor_id = getattr(request.state, "user_token", None)
    if not requestor_id:
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    strava_profile_helper = StravaProfileHelper(request_id=request.state.request_id)
    requested_user_profile_id = strava_profile_helper.get_user_id_by_strava_id(
        strava_id
    )

    if not requested_user_profile_id:
        logger.warning(f"User profile with strava_id {strava_id} not found.")
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_profile_helper = UserProfileHelper(request_id=request.state.request_id)
    user_profile = user_profile_helper.get_user_profile(requested_user_profile_id)

    if not user_profile or not user_profile.get("public_profile", False):
        logger.warning(
            f"User profile {requested_user_profile_id} is not public or does not exist."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_id = user_profile.get("user_id")

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    locations = workout_helper.get_all_workout_locations(user_id)

    return JSONResponse(content=locations, status_code=200)
