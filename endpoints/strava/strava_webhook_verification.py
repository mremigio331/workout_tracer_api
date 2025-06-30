from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from pydantic import BaseModel
import boto3
import os
import json
from datetime import datetime
import pytz
from clients.strava_client import StravaClient
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/webhook",
    summary="Strava webhook verification handshake",
    response_description="Strava webhook verification",
)
def strava_webhook_verification(request: Request):
    # Print useful request info for debugging
    logger.info(
        f"Strava webhook verification request: method={request.method}, url={request.url}, headers={dict(request.headers)}, query_params={dict(request.query_params)}"
    )

    strava_client = StravaClient(request_id=request.state.request_id)
    # Use STAGE env var for correct verify token
    stage = os.getenv("STAGE", "staging")
    verify_token = strava_client.get_strava_api_configs().get(
        f"{stage.upper()}_VERIFY_TOKEN"
    )
    params = dict(request.query_params)

    # Try/except for param extraction
    try:
        hub_verify_token = params.get("hub.verify_token")
    except Exception as e:
        logger.error(f"Error extracting hub.verify_token: {e}")
        return JSONResponse(
            content={"error": "Invalid request format"},
            status_code=500,
        )

    try:
        hub_challenge = params.get("hub.challenge")
    except Exception as e:
        logger.error(f"Error extracting hub.challenge: {e}")
        return JSONResponse(
            content={"error": "Invalid request format"},
            status_code=500,
        )

    if not hub_verify_token or not hub_challenge:
        logger.warning("Missing hub.verify_token or hub.challenge in request.")
        return JSONResponse(
            content={"error": "Missing hub.verify_token or hub.challenge"},
            status_code=400,
        )

    if hub_verify_token != verify_token:
        logger.warning("Invalid Strava verify_token received.")
        return JSONResponse(content={"error": "Invalid verify_token"}, status_code=403)

    return JSONResponse(
        content={"hub.challenge": hub_challenge},
        status_code=200,
    )
