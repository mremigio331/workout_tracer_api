from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
import base64

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

    # Decode next_token to get offset
    if next_token:
        try:
            # Defensive: decode and strip whitespace, ensure int
            offset = int(base64.urlsafe_b64decode(next_token.encode()).decode().strip())
        except Exception as e:
            logger.warning(
                f"Invalid next_token provided ('{next_token}'): {e}. Defaulting to offset=0"
            )
            offset = 0
    else:
        offset = 0

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    logger.info(f"Fetching all workouts for user_id={user_id}")
    all_workouts = workout_helper.get_all_workouts(user_id=user_id)
    total = len(all_workouts)
    logger.info(f"Total workouts found for user_id={user_id}: {total}")
    paginated = all_workouts[offset : offset + limit]
    logger.info(
        f"Returning workouts {offset} to {offset + len(paginated)} for user_id={user_id}"
    )

    # Prepare next_token if there are more results
    if offset + limit < total:
        new_next_token = base64.urlsafe_b64encode(str(offset + limit).encode()).decode()
        logger.info(f"Next query: /workouts?limit={limit}&next_token={new_next_token}")
    else:
        new_next_token = None
        logger.info("No new token, this is the last page.")

    return JSONResponse(
        content={
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_token": new_next_token,
            "workouts": paginated,
        },
        status_code=200,
    )
