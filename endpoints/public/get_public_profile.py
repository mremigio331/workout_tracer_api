from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.user_profile_helper import UserProfileHelper
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from decimal import Decimal

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/profile/{user_display_id}",
    summary="Get a public user profile by user_display_id",
    response_description="Public user profile",
    tags=["Public"],
)
@exceptions_decorator
def get_public_profile(user_display_id: int, request: Request):
    requestor_id = getattr(request.state, "user_token", None)
    if not requestor_id:
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    user_profile_helper = UserProfileHelper(request_id=request.state.request_id)
    user_profile = user_profile_helper.get_user_by_display_id(user_display_id)

    if not user_profile or not user_profile.get("public_profile", False):
        logger.warning(
            f"User profile with user_display_id {user_display_id} not found or not public."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_id = user_profile.get("user_id")

    # Try to get Strava profile for additional fields
    strava_profile_helper = StravaProfileHelper(request_id=request.state.request_id)
    strava_profile = strava_profile_helper.get_strava_profile(user_id=user_id)

    display_id = user_profile.get("user_display_id")
    strava_id = strava_profile.get("strava_id") if strava_profile else None

    profile = {
        "name": user_profile.get("name"),
        "user_display_id": (
            int(display_id) if isinstance(display_id, Decimal) else display_id
        ),
        "strava_id": int(strava_id) if isinstance(strava_id, Decimal) else strava_id,
        "firstname": strava_profile.get("firstname") if strava_profile else None,
        "lastname": strava_profile.get("lastname") if strava_profile else None,
        "city": strava_profile.get("city") if strava_profile else None,
        "profile_medium": (
            strava_profile.get("profile_medium") if strava_profile else None
        ),
        "profile": strava_profile.get("profile") if strava_profile else None,
    }

    return JSONResponse(content={"profile": profile}, status_code=200)
