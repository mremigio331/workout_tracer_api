from fastapi import APIRouter, Request, Body
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
from dynamodb.helpers.strava_credentials_helper import StravaCredentialsHelper
from clients.strava_client import StravaClient, StravaAuthCodeExchangeError
from dynamodb.models.strava_profile_model import StravaAthleteModel
from dynamodb.models.strava_credentials_model import StravaCredentialsModel
from pydantic import BaseModel, Field
import requests
from datetime import datetime
import os
import decimal

logger = Logger(service="workout-tracer-api")
router = APIRouter()


class UpdateStravaCallback(BaseModel):
    auth_code: str = Field(..., description="The authorization code from Strava")


@router.put(
    "/profile/callback",
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
    logger.append_keys(request_id=request.state.request_id)
    logger.info("Received request to update Strava callback.")
    auth_code = update_strava_callback.auth_code
    if not auth_code:
        logger.warning("Authorization code not provided in request.")
        return JSONResponse(
            content={"error": "Authorization code is required."}, status_code=400
        )
    logger.info("Received auth code from client.")
    user_id = getattr(request.state, "user_token", None)
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    logger.info(
        f"Attempting to exchange auth code for Strava tokens for user_id: {user_id}"
    )
    strava_client = StravaClient(request_id=request.state.request_id)
    try:
        tokens, athlete_data = strava_client.get_strava_callback_url(auth_code)
        logger.info("Successfully exchanged auth code for tokens and athlete data.")
    except StravaAuthCodeExchangeError as e:
        logger.error(f"StravaAuthCodeExchangeError: {e}")
        raise

    if not athlete_data or "id" not in athlete_data:
        logger.warning(
            f"Strava athlete data missing or incomplete in response. Response: {athlete_data}"
        )
        return JSONResponse(
            content={"error": "Strava athlete data missing or incomplete."},
            status_code=400,
        )

    logger.info(f"Strava tokens and athlete data received: {athlete_data}")

    athlete_data["strava_id"] = athlete_data.pop("id")
    athlete_data["user_id"] = user_id

    logger.info(
        f"Mapped athlete_data['id'] to 'strava_id' and set 'user_id': {athlete_data}"
    )

    try:
        athlete_profile = StravaAthleteModel(**athlete_data)
        logger.info("Successfully created StravaAthleteModel instance.")
    except Exception as e:
        logger.error(f"Failed to create StravaAthleteModel: {e}")
        return JSONResponse(
            content={"error": f"Failed to create StravaAthleteModel: {e}"},
            status_code=500,
        )

    strava_profile_helper = StravaProfileHelper(request_id=request.state.request_id)
    strava_credentials_helper = StravaCredentialsHelper(
        request_id=request.state.request_id
    )

    # Check if profile exists, then update or create accordingly
    try:
        logger.info(f"Checking for existing Strava profile for user_id: {user_id}")
        existing_profile = strava_profile_helper.get_strava_profile(user_id)
        if existing_profile:
            logger.info(f"Existing profile found for user_id: {user_id}")
        else:
            logger.info(f"No existing profile found for user_id: {user_id}")
    except Exception as e:
        logger.error(f"Error fetching existing Strava profile: {e}")
        return JSONResponse(
            content={"error": f"Error fetching existing Strava profile: {e}"},
            status_code=500,
        )

    if existing_profile:
        logger.info(f"Updating Strava profile for user_id: {user_id}")
        strava_profile_helper.update_strava_profile(**athlete_data)
        logger.info(f"Successfully updated Strava profile for user_id: {user_id}")
    else:
        logger.info(f"Creating new Strava profile for user_id: {user_id}")
        strava_profile_helper.create_strava_profile(**athlete_data)
        logger.info(f"Successfully created Strava profile for user_id: {user_id}")

    try:
        logger.info(f"Storing Strava credentials for user_id: {user_id}")
        strava_credentials_helper.create_or_update_credentials(
            token_type=tokens.get("token_type"),
            expires_at=tokens.get("expires_at"),
            expires_in=tokens.get("expires_in"),
            refresh_token=tokens.get("refresh_token"),
            access_token=tokens.get("access_token"),
            user_id=user_id,
        )
        logger.info("Successfully stored Strava credentials.")
    except Exception as e:
        logger.error(f"Error storing Strava credentials: {e}")
        return JSONResponse(
            content={"error": f"Error storing Strava credentials: {e}"},
            status_code=500,
        )

    logger.info("Returning successful response to client.")

    return JSONResponse(
        content={
            "message": "Strava tokens and profile updated successfully",
            "athlete": athlete_profile.dict(),
        },
        status_code=200,
    )
