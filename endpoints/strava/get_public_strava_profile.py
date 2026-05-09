from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.helpers.user_profile_helper import UserProfileHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/public_profile/{strava_id}",
    summary="Get a user's Strava profile",
    response_description="The user's Strava profile",
)
@exceptions_decorator
def get_public_strava_profile(strava_id: int, request: Request):
    """
    Get the public Strava profile for a given strava_id, only if the user profile is public.
    """
    logger.append_keys(request_id=request.state.request_id)
    logger.info("Received request to get public Strava profile.")

    # Find user_id by strava_id
    strava_profile_helper = StravaProfileHelper(request_id=request.state.request_id)
    requested_user_profile_id = strava_profile_helper.get_user_id_by_strava_id(
        strava_id
    )

    if not requested_user_profile_id:
        logger.warning(f"User profile with strava_id {strava_id} not found.")
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    # Check if user profile is public
    user_profile_helper = UserProfileHelper(request_id=request.state.request_id)
    user_profile = user_profile_helper.get_user_profile(requested_user_profile_id)

    if not user_profile or not user_profile.get("public_profile", False):
        logger.warning(
            f"User profile with user_id {requested_user_profile_id} is not public or does not exist."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_id = user_profile.get("user_id")
    logger.info(f"Fetching Strava profile for user_id: {user_id}")

    athlete = strava_profile_helper.get_strava_profile(user_id=user_id)
    if not athlete:
        logger.warning(f"Strava profile not found for user_id: {user_id}")
        return JSONResponse(
            content={"error": "Strava profile not found."}, status_code=404
        )
    logger.info(f"Successfully retrieved Strava profile for user_id: {user_id}")
    return JSONResponse(
        content={"athlete": athlete},
        status_code=200,
    )
