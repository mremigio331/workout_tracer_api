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
        user_profile_dict = user
        strava_profile = strava_profile_helper.get_strava_profile(
            user_id=user["user_id"]
        )
        if not strava_profile:
            pass
        if strava_profile:
            user_profile_dict["firstname"] = strava_profile.get("firstname", None)
            user_profile_dict["lastname"] = strava_profile.get("lastname", None)
            user_profile_dict["city"] = strava_profile.get("city", None)
            user_profile_dict["profile_medium"] = strava_profile.get(
                "profile_medium", None
            )
            user_profile_dict["profile"] = strava_profile.get("profile", None)
            user_profile_dict["strava_id"] = strava_profile.get("strava_id", None)

        profile_return.append(user_profile_dict)

    return JSONResponse(content={"public_users": public_users}, status_code=200)
