from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.user_profile_helper import UserProfileHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/workout_locations/{user_id}",
    summary="Get a summary of all locations a user has worked out in",
    response_description="Location summary broken down by sport type",
)
@exceptions_decorator
def get_workout_locations(user_id: str, request: Request):
    requestor_id = getattr(request.state, "user_token", None)
    if not requestor_id:
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    user_profile_helper = UserProfileHelper(request_id=request.state.request_id)
    user_profile = user_profile_helper.get_user_profile(user_id)

    if not user_profile:
        return JSONResponse(content={"error": "User not found."}, status_code=404)

    is_public = user_profile.get("public_profile", False)
    is_own_account = requestor_id == user_id

    if not is_public and not is_own_account:
        logger.warning(
            f"Requestor {requestor_id} attempted to access workout locations for private user {user_id}."
        )
        return JSONResponse(content={"error": "Access denied."}, status_code=403)

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    locations = workout_helper.get_all_workout_locations(user_id)

    return JSONResponse(content=locations, status_code=200)
