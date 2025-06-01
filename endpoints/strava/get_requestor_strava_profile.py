from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.helpers.audit_actions_helper import AuditActionHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


strava_profile_helper = StravaProfileHelper()


@router.get(
    "/profile",
    summary="Get the requestor's Strava profile",
    response_description="The requestor's Strava profile",
)
@exceptions_decorator
def get_requestor_strava_profile(request: Request):
    """
    Get the Strava profile for the authenticated user.
    """
    user_id = getattr(request.state, "user_token", None)
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )
    
    strava_profile = strava_profile_helper.get_strava_profile(user_id=user_id)

    if not strava_profile:
        logger.warning(f"Strava profile not found for user_id: {user_id}")
        return JSONResponse(
            content={"error": "Strava profile not found."}, status_code=404
        )
    return JSONResponse(
        content={"athlete": strava_profile}, status_code=200
    )
