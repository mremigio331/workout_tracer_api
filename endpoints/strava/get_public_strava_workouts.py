from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.user_profile_helper import UserProfileHelper
from dynamodb.helpers.strava_profile_helper import StravaProfileHelper
import base64
import json
import urllib.parse

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/public_workouts/{strava_id}",
    summary="Get all workouts with pagination",
    response_description="Paginated list of Strava workouts",
)
@exceptions_decorator
def get_public_strava_workouts(
    strava_id: str,
    request: Request,
    limit: int = Query(
        500, ge=1, le=500, description="Number of workouts to return (max 500)"
    ),
    next_token: str = Query(None, description="Token for fetching the next page"),
):
    user_id = getattr(request.state, "user_token", None)
    logger.info(
        f"Received request for public workouts: requested_user_id={user_id}, requested_strava_account= {strava_id}, limit={limit}, next_token={next_token}"
    )
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    strava_profile_helper = StravaProfileHelper(request_id=request.state.request_id)

    requested_user_profile_id = strava_profile_helper.get_user_id_by_strava_id(
        strava_id
    )

    if not requested_user_profile_id:
        logger.warning(
            f"User profile with strava_id {strava_id} not found for user_id {user_id}."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_profile_helper = UserProfileHelper(request_id=request.state.request_id)

    user_profile = user_profile_helper.get_user_profile(requested_user_profile_id)

    if not user_profile or not user_profile.get("public_profile", False):
        logger.warning(
            f"User profile with user_id {requested_user_profile_id} is not public or does not exist."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_id = user_profile.get("user_id")

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    logger.info(f"Fetching workouts for user_id={user_id}")

    dynamo_next_token = None
    if next_token:
        logger.info(f"Raw incoming next_token: {next_token}")
        try:
            # Decode from URL encoding first
            decoded_url_token = urllib.parse.unquote(next_token)
            decoded_token = base64.urlsafe_b64decode(
                decoded_url_token.encode()
            ).decode()
            dynamo_next_token = json.loads(decoded_token)
            logger.info(f"Decoded next_token: {dynamo_next_token}")
        except Exception as e:
            logger.warning(
                f"Invalid next_token provided, defaulting to None. Exception: {e}"
            )
            dynamo_next_token = None

    result = workout_helper.get_all_workouts(
        user_id=user_id, limit=limit, next_token=dynamo_next_token
    )
    workouts = result.get("workouts", [])
    returned_next_token = result.get("next_token")

    # Debug log for returned_next_token
    logger.info(f"Returned next_token from DynamoDB: {returned_next_token}")

    if returned_next_token:
        if isinstance(returned_next_token, dict):
            new_next_token = base64.urlsafe_b64encode(
                json.dumps(returned_next_token).encode()
            ).decode()
        else:
            logger.warning(f"Returned next_token is not a dict: {returned_next_token}")
            new_next_token = None
        if next_token and new_next_token == next_token:
            new_next_token = None
            logger.info("Next token unchanged, stopping pagination.")
        else:
            logger.info(
                f"Next query: /workouts?limit={limit}&next_token={new_next_token}"
            )
    else:
        new_next_token = None
        logger.info("No new token, this is the last page.")

    return JSONResponse(
        content={
            "limit": limit,
            "next_token": new_next_token,
            "workouts": workouts,
        },
        status_code=200,
    )
