from fastapi import APIRouter, Request, Body
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.user_strava_helper import UserStravaHelper
from dynamodb.models.user_strava_model import UserStravaModel, UserStravaAthleteModel
from helpers.strava_helper import get_strava_api_configs
from pydantic import BaseModel, Field
import requests
from decimal import Decimal
from datetime import datetime
import os

logger = Logger(service="workout-tracer-api")
router = APIRouter()


class UpdateStravaCallback(BaseModel):
    auth_code: str = Field(..., description="The authorization code from Strava")


@router.put(
    "/profile/strava/callback",
    summary="Update all Strava info for a user",
    response_description="Updated Strava info",
)
@exceptions_decorator
def update_strava_callback(
    update_strava_callback: UpdateStravaCallback,
    request: Request = None,
):
    """
    Update all Strava info for a user. All fields are required.
    """
    strava_keys = get_strava_api_configs()
    auth_code = update_strava_callback.auth_code
    if not auth_code:
        logger.warning("Authorization code not provided in request.")
        return JSONResponse(
            content={"error": "Authorization code is required."}, status_code=400
        )
    logger.info(f"Received auth code")
    user_id = getattr(request.state, "user_token", None)
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": strava_keys["CLIENT_ID"],
            "client_secret": strava_keys["CLIENT_SECRET"],
            "code": auth_code,
            "grant_type": "authorization_code",
        },
    )

    tokens = response.json()
    # Build UserStravaModel from tokens
    athlete_data = tokens.get("athlete", {})
    if not athlete_data or "id" not in athlete_data:
        logger.warning("Strava athlete data missing or incomplete in response.")
        return JSONResponse(
            content={"error": "Strava athlete data missing or incomplete."},
            status_code=400,
        )
    athlete = UserStravaAthleteModel(**athlete_data)
    strava_model = UserStravaModel(
        token_type=tokens.get("token_type"),
        expires_at=tokens.get("expires_at"),
        expires_in=tokens.get("expires_in"),
        refresh_token=tokens.get("refresh_token"),
        access_token=tokens.get("access_token"),
        athlete=athlete,
    )

    # Save to DynamoDB using UserStravaHelper
    athlete_dict = UserStravaHelper.convert_floats_to_decimal(
        strava_model.athlete.dict()
    )

    strava_helper = UserStravaHelper()
    updated = strava_helper.update_user_strava(
        user_id=user_id,
        token_type=strava_model.token_type,
        expires_at=strava_model.expires_at,
        expires_in=strava_model.expires_in,
        refresh_token=strava_model.refresh_token,
        access_token=strava_model.access_token,
        athlete=athlete_dict,
    )

    if not updated:
        return JSONResponse(
            content={"error": "Failed to update Strava info"}, status_code=400
        )

    return JSONResponse(
        content={
            "message": "Strava tokens updated successfully",
            "strava": UserStravaHelper.make_json_serializable(updated.athlete.dict()),
        },
        status_code=200,
    )
