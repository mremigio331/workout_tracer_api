from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.apple_health_workout_helper import AppleHealthWorkoutHelper
from dynamodb.helpers.user_profile_helper import UserProfileHelper
from dynamodb.models.apple_health_workout_model import AppleHealthWorkoutModel
from cryptography.fernet import Fernet
import base64
import boto3
import json
import os
import urllib.parse

logger = Logger(service="workout-tracer-api")
router = APIRouter()

# Cache the Fernet key so we only fetch from Secrets Manager once per Lambda container
_pagination_token_key_cache: str | None = None


def _get_pagination_token_key() -> str | None:
    """Retrieve the Fernet pagination token key from Secrets Manager, cached per container."""
    global _pagination_token_key_cache
    if _pagination_token_key_cache is not None:
        return _pagination_token_key_cache

    secret_name = os.getenv("PAGINATION_TOKEN_SECRET_NAME")
    stage = os.getenv("STAGE", "staging")
    if not secret_name:
        logger.warning("PAGINATION_TOKEN_SECRET_NAME env var not set.")
        return None
    try:
        client = boto3.client("secretsmanager", region_name="us-west-2")
        response = client.get_secret_value(SecretId=secret_name)
        secret_dict = json.loads(response["SecretString"])
        key = secret_dict.get(stage)
        if key:
            _pagination_token_key_cache = key
        else:
            logger.warning(
                f"No key found for stage '{stage}' in secret '{secret_name}'."
            )
        return key
    except Exception as e:
        logger.error(
            f"Failed to retrieve pagination token key from Secrets Manager: {e}"
        )
        return None


# Strava workout projection fields
STRAVA_PROJECTION = (
    "id, #n, #t, sport_type, start_date, start_date_local, "
    "distance, total_elevation_gain, moving_time, elapsed_time, "
    "kilojoules, #m, locations, #s"
)
STRAVA_EXPR_NAMES = {"#n": "name", "#t": "type", "#m": "map", "#s": "source"}

# Apple Health workout projection fields
AH_PROJECTION = (
    "workout_uuid, #n, workout_activity_type, start_date, "
    "total_distance, #d, total_energy_burned, elevation_ascended, "
    "summary_polyline, average_speed, average_heartrate, max_heartrate, "
    "locations, #s"
)
AH_EXPR_NAMES = {"#n": "name", "#s": "source", "#d": "duration"}


def _encode_next_token(token_dict: dict, encrypt: bool) -> str | None:
    """Encode a dual-cursor pagination token as base64 or Fernet-encrypted string."""
    if not token_dict.get("strava_next") and not token_dict.get("apple_health_next"):
        return None
    payload = json.dumps(token_dict)
    if encrypt:
        key = _get_pagination_token_key()
        if key:
            f = Fernet(key.encode() if isinstance(key, str) else key)
            return f.encrypt(payload.encode()).decode()
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_next_token(token: str, decrypt: bool) -> dict:
    """Decode a dual-cursor pagination token."""
    try:
        if decrypt:
            key = _get_pagination_token_key()
            if key:
                f = Fernet(key.encode() if isinstance(key, str) else key)
                try:
                    payload = f.decrypt(token.encode()).decode()
                    return json.loads(payload)
                except Exception:
                    pass
        decoded = urllib.parse.unquote(token)
        return json.loads(base64.urlsafe_b64decode(decoded.encode()).decode())
    except Exception as e:
        logger.warning(f"Failed to decode next_token: {e}. Starting from beginning.")
        return {}


@router.get(
    "/workouts/{user_display_id}",
    summary="Get public workouts for a user by user_display_id",
    response_description="Paginated list of public workouts from all sources",
    tags=["Public"],
)
@exceptions_decorator
def get_public_workouts(
    user_display_id: int,
    request: Request,
    limit: int = Query(
        500, ge=1, le=500, description="Number of workouts to return (max 500)"
    ),
    next_token: str = Query(None, description="Token for fetching the next page"),
):
    requestor_id = getattr(request.state, "user_token", None)
    if not requestor_id:
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    user_profile_helper = UserProfileHelper(request_id=request.state.request_id)
    user_profile = user_profile_helper.get_user_by_display_id(user_display_id)

    if not user_profile:
        logger.warning(
            f"User profile with user_display_id {user_display_id} not found."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    if not user_profile.get("public_profile", False):
        logger.warning(
            f"User profile with user_display_id {user_display_id} is not public."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_id = user_profile.get("user_id")
    show_source = user_profile.get("show_workout_source", False)
    encrypt_token = not show_source

    # Decode dual-cursor token
    cursors = {}
    if next_token:
        cursors = _decode_next_token(next_token, decrypt=encrypt_token)

    strava_next = cursors.get("strava_next")
    ah_next = cursors.get("apple_health_next")

    # Split limit roughly evenly between sources
    half_limit = max(limit // 2, 1)

    # Fetch Strava workouts
    strava_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    strava_result = strava_helper.get_all_workouts(
        user_id=user_id,
        limit=half_limit,
        next_token=strava_next,
        projection_expression=STRAVA_PROJECTION,
        expression_attribute_names=STRAVA_EXPR_NAMES,
    )
    strava_workouts = strava_result.get("workouts", [])
    strava_returned_next = strava_result.get("next_token")

    # Tag Strava workouts with source if not already present
    for w in strava_workouts:
        if "source" not in w:
            w["source"] = "strava"

    # Fetch Apple Health workouts
    ah_helper = AppleHealthWorkoutHelper(request_id=request.state.request_id)
    ah_result = ah_helper.get_all_workouts(
        user_id=user_id,
        limit=half_limit,
        next_token=ah_next,
        projection_expression=AH_PROJECTION,
        expression_attribute_names=AH_EXPR_NAMES,
    )
    ah_workouts_raw = ah_result.get("workouts", [])
    ah_returned_next = ah_result.get("next_token")

    # Normalize Apple Health workouts to Strava format
    ah_workouts = []
    for raw in ah_workouts_raw:
        model = AppleHealthWorkoutModel(**raw)
        ah_workouts.append(model.to_strava_format())

    # Merge both lists
    all_workouts = strava_workouts + ah_workouts

    # Strip source field if user doesn't want it shown
    if not show_source:
        for w in all_workouts:
            w.pop("source", None)

    # Build dual-cursor next_token
    new_token_dict = {
        "strava_next": strava_returned_next,
        "apple_health_next": ah_returned_next,
    }
    encoded_next_token = _encode_next_token(new_token_dict, encrypt=encrypt_token)

    return JSONResponse(
        content={
            "limit": limit,
            "next_token": encoded_next_token,
            "workouts": all_workouts,
        },
        status_code=200,
    )
