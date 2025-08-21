from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
import base64
import json
import urllib.parse

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/workouts",
    summary="Get all workouts with pagination",
    response_description="Paginated list of Strava workouts",
)
@exceptions_decorator
def get_strava_workouts(
    request: Request,
    limit: int = Query(
        500, ge=1, le=500, description="Number of workouts to return (max 500)"
    ),
    next_token: str = Query(None, description="Token for fetching the next page"),
):
    user_id = getattr(request.state, "user_token", None)
    logger.info(
        f"Received request for workouts: user_id={user_id}, limit={limit}, next_token={next_token}"
    )
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)

    # Use DynamoDB pagination with next_token
    dynamo_next_token = None
    if next_token:
        try:
            # Decode from URL encoding first
            decoded_url_token = urllib.parse.unquote(next_token)
            dynamo_next_token = json.loads(
                base64.urlsafe_b64decode(decoded_url_token.encode()).decode()
            )
        except Exception as e:
            logger.warning(
                f"Invalid next_token provided ('{next_token}'): {e}. Defaulting to None"
            )
            dynamo_next_token = None

    result = workout_helper.get_all_workouts(
        user_id=user_id, limit=limit, next_token=dynamo_next_token
    )
    workouts = result.get("workouts", [])
    returned_next_token = result.get("next_token")

    if returned_next_token:
        new_next_token = base64.urlsafe_b64encode(
            json.dumps(returned_next_token).encode()
        ).decode()
        logger.info(f"Next query: /workouts?limit={limit}&next_token={new_next_token}")
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
