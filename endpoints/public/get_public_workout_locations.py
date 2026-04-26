from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.apple_health_workout_helper import AppleHealthWorkoutHelper
from dynamodb.helpers.user_profile_helper import UserProfileHelper
from typing import Dict

logger = Logger(service="workout-tracer-api")
router = APIRouter()


def _merge_location_summaries(
    base: Dict[str, Dict[str, Dict[str, int]]],
    addition: Dict[str, Dict[str, Dict[str, int]]],
) -> None:
    """Merge location summary dicts in-place into base."""
    for location_type in ("states", "countries"):
        for name, sport_counts in (addition.get(location_type) or {}).items():
            entry = base[location_type].setdefault(name, {"total": 0})
            for sport, count in sport_counts.items():
                entry[sport] = entry.get(sport, 0) + count


def _get_apple_health_locations(
    ah_helper: AppleHealthWorkoutHelper, user_id: str
) -> dict:
    """Aggregate locations from Apple Health workouts, mirroring Strava pattern."""
    summary: Dict[str, Dict[str, Dict[str, int]]] = {
        "countries": {},
        "states": {},
    }
    next_token = None
    while True:
        result = ah_helper.get_all_workouts(
            user_id,
            next_token=next_token,
            projection_expression="#loc, workout_activity_type",
            expression_attribute_names={"#loc": "locations"},
        )
        for workout in result.get("workouts", []):
            sport_type = workout.get("workout_activity_type") or "Unknown"
            locations = workout.get("locations") or {}
            for location_type in ("states", "countries"):
                for name, visited in (locations.get(location_type) or {}).items():
                    if not visited:
                        continue
                    entry = summary[location_type].setdefault(name, {"total": 0})
                    entry[sport_type] = entry.get(sport_type, 0) + 1
                    entry["total"] += 1
        next_token = result.get("next_token")
        if not next_token:
            break
    return {"locations": summary}


@router.get(
    "/workout_locations/{user_display_id}",
    summary="Get combined workout locations for a public user",
    response_description="Location summary broken down by sport type from all sources",
    tags=["Public"],
)
@exceptions_decorator
def get_public_workout_locations(user_display_id: int, request: Request):
    requestor_id = getattr(request.state, "user_token", None)
    if not requestor_id:
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    user_profile_helper = UserProfileHelper(request_id=request.state.request_id)
    user_profile = user_profile_helper.get_user_by_display_id(user_display_id)

    if not user_profile or not user_profile.get("public_profile", False):
        logger.warning(
            f"User profile with user_display_id {user_display_id} not found or not public."
        )
        return JSONResponse(
            content={"error": "User profile not found."}, status_code=404
        )

    user_id = user_profile.get("user_id")

    # Get Strava workout locations
    strava_helper = StravaWorkoutHelper(request_id=request.state.request_id)
    strava_locations = strava_helper.get_all_workout_locations(user_id)

    # Get Apple Health workout locations
    ah_helper = AppleHealthWorkoutHelper(request_id=request.state.request_id)
    ah_locations = _get_apple_health_locations(ah_helper, user_id)

    # Merge both summaries
    combined = strava_locations.get("locations", {"countries": {}, "states": {}})
    _merge_location_summaries(combined, ah_locations.get("locations", {}))

    return JSONResponse(content={"locations": combined}, status_code=200)
