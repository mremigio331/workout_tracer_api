from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from exceptions.user_exceptions import (
    InvalidUserIdException,
    UserNotFound,
    ProfileNotPublicOrDoesNotExist,
)
from decorators.exceptions_decorator import exceptions_decorator
from helpers.jwt import decode_jwt
from dynamodb.helpers.user_profile_helper import UserProfileHelper
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/public_users",
    summary="Get all public users",
    response_description="List of public users",
)
@exceptions_decorator
def get_public_users(request: Request):
    """
    Get User Profile Endpoint
    Returns:
        A JSON response containing the user's profile information.
    """
    logger.append_keys(request_id=request.state.request_id)
    logger.info("Getting request for user profile.")

    token_user_id = getattr(request.state, "user_token", None)

    if not token_user_id:
        logger.warning("Token User ID could not be extracted from JWT.")
        raise InvalidUserIdException("Token User ID is required.")

    user_helper = UserProfileHelper(request_id=request.state.request_id)
    strava_profile_helper = StravaProfileHelper(request_id=request.state.request_id)
    public_users = user_helper.get_public_profiles()

    profile_return = []

    for user in public_users:
        # Backfill user_display_id if missing
        display_id = user.get("user_display_id")
        if display_id is None:
            profile = user_helper.get_user_profile(user_id=user["user_id"])
            display_id = profile.get("user_display_id") if profile else None

        strava_profile = strava_profile_helper.get_strava_profile(
            user_id=user["user_id"]
        )

        public_user = {
            "name": user.get("name"),
            "user_display_id": int(display_id) if display_id is not None else None,
            "strava_id": (
                int(strava_profile.get("strava_id"))
                if strava_profile and strava_profile.get("strava_id")
                else None
            ),
            "firstname": strava_profile.get("firstname") if strava_profile else None,
            "lastname": strava_profile.get("lastname") if strava_profile else None,
            "city": strava_profile.get("city") if strava_profile else None,
            "profile_medium": (
                strava_profile.get("profile_medium") if strava_profile else None
            ),
            "profile": strava_profile.get("profile") if strava_profile else None,
        }

        profile_return.append(public_user)

    return JSONResponse(content={"public_users": profile_return}, status_code=200)
