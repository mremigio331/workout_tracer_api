from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.user_strava_helper import UserStravaHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/profile/public",
    summary="Get a user's Strava profile",
    response_description="The user's Strava profile",
)
@exceptions_decorator
def get_strava_profile(user_id: str, request: Request):
    """
    Get the Strava profile for a given user_id.
    """
    if not user_id:
        logger.warning("User ID not provided in request.")
        return JSONResponse(content={"error": "User ID is required."}, status_code=400)
    strava_helper = UserStravaHelper()
    strava_profile = strava_helper.get_user_strava(user_id=user_id)
    if not strava_profile:
        logger.warning(f"Strava profile not found for user_id: {user_id}")
        return JSONResponse(
            content={"error": "Strava profile not found."}, status_code=404
        )
    return JSONResponse(
        content={
            "strava_profile": UserStravaHelper.make_json_serializable(
                strava_profile.dict()
            )
        },
        status_code=200,
    )
