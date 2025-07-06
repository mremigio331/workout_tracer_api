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
from datetime import datetime, timedelta
import os
import decimal
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
import pytz

logger = Logger(service="workout-tracer-api")
router = APIRouter()


class GrabAllWorkouts(BaseModel):
    """
    Model for the request body to grab all Strava workouts.

    - Provide either:
        * start_date and/or end_date (ISO 8601, e.g. '2024-06-01T00:00:00Z')
        * time_since_last_grab (in days, e.g. 7)
        * all=True to fetch all workouts

    - Optionally, provide a timezone (IANA string, e.g. 'America/Los_Angeles'). Defaults to UTC.
    - If no filters are provided, defaults to last 7 days in UTC.
    """

    start_date: str | None = Field(
        None,
        description="(Optional) Start date (ISO 8601, e.g. '2024-06-01T00:00:00Z'). Example: 7 days ago.",
    )
    end_date: str | None = Field(
        None,
        description="(Optional) End date (ISO 8601, e.g. '2024-06-08T23:59:59Z'). Example: today.",
    )
    time_since_last_grab: int | None = Field(
        None,
        description="(Optional) Number of days since last grab to filter workouts. Example: 7",
    )
    all: bool = Field(
        False, description="If true, fetch all workouts regardless of date."
    )
    timezone: str | None = Field(
        None,
        description="(Optional) IANA timezone string (e.g. 'America/Los_Angeles'). Defaults to UTC.",
    )


def parse_and_convert_to_utc(dt_str, tz):
    """Parse ISO string, localize to tz, then convert to UTC and return epoch timestamp (int)."""
    if not dt_str:
        return None
    local_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if local_dt.tzinfo is None:
        local_dt = tz.localize(local_dt)
    else:
        local_dt = local_dt.astimezone(tz)
    utc_dt = local_dt.astimezone(pytz.UTC)
    return int(utc_dt.timestamp())


@router.put(
    "/grab_all_workouts",
    summary="Grab all Strava workouts for a user",
    description="""
Grab all Strava workouts for a user.

Provide either:
- `start_date` and/or `end_date` (ISO 8601, e.g. '2024-06-01T00:00:00Z')
- `time_since_last_grab` (in days, e.g. 7)
- `all=true` to fetch all workouts

Optionally, provide a `timezone` (IANA string, e.g. 'America/Los_Angeles'). Defaults to UTC.
If no filters are provided, defaults to last 7 days in UTC.

**Example (last 7 days, UTC):**
```
{
    "start_date": "2024-06-01T00:00:00Z",
    "end_date": "2024-06-08T23:59:59Z",
    "timezone": "UTC"
}
```
""",
    response_description="List of Strava workouts",
)
@exceptions_decorator
def grab_all_workouts(request: Request, grab_all_workouts: GrabAllWorkouts):
    user_id = getattr(request.state, "user_token", None)
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    # Validation: Only one of (date range), time_since_last_grab, or all can be used
    has_date_range = grab_all_workouts.start_date or grab_all_workouts.end_date
    has_time_since = grab_all_workouts.time_since_last_grab is not None
    has_all = grab_all_workouts.all

    used = sum([bool(has_date_range), has_time_since, has_all])
    if used > 1:
        return JSONResponse(
            content={
                "error": "Provide only one of: (start_date/end_date), time_since_last_grab, or all."
            },
            status_code=400,
        )

    credentials_helper = StravaCredentialsHelper(request_id=request.state.request_id)
    strava_credentials = credentials_helper.get_credentials(user_id=user_id)
    strava_client = StravaClient(request_id=request.state.request_id)
    if not strava_credentials:
        logger.warning(f"Strava credentials not found for user_id: {user_id}")
        return JSONResponse(
            content={"error": "Strava credentials not found."}, status_code=404
        )

    logger.info(f"Fetching Strava workouts for user_id: {user_id}")

    workout_helper = StravaWorkoutHelper(request_id=request.state.request_id)

    # Timezone handling
    tz_str = grab_all_workouts.timezone or "UTC"
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        return JSONResponse(
            content={"error": f"Invalid timezone: {tz_str}"}, status_code=400
        )

    if has_date_range:
        after_utc = parse_and_convert_to_utc(grab_all_workouts.start_date, tz)
        before_utc = parse_and_convert_to_utc(grab_all_workouts.end_date, tz)
        activities = strava_client.get_athlete_activities(
            access_token=strava_credentials["access_token"],
            after=after_utc,
            before=before_utc,
        )
    elif has_time_since:
        before_local = datetime.now(tz)
        after_local = before_local - timedelta(
            days=grab_all_workouts.time_since_last_grab
        )
        after_utc = parse_and_convert_to_utc(after_local.isoformat(), tz)
        before_utc = parse_and_convert_to_utc(before_local.isoformat(), tz)
        activities = strava_client.get_athlete_activities(
            access_token=strava_credentials["access_token"],
            after=after_utc,
            before=before_utc,
        )
    elif has_all:
        activities = strava_client.get_athlete_activities(
            access_token=strava_credentials["access_token"]
        )
    else:
        before_local = datetime.now(tz)
        after_local = before_local - timedelta(
            days=7
        )  # Default to last 7 days if no filters
        after_utc = parse_and_convert_to_utc(after_local.isoformat(), tz)
        before_utc = parse_and_convert_to_utc(before_local.isoformat(), tz)
        activities = strava_client.get_athlete_activities(
            access_token=strava_credentials["access_token"],
            after=after_utc,
            before=before_utc,
        )
    if not activities:
        logger.info(f"No activities found for user_id: {user_id}")
        return JSONResponse(
            content={"message": "No activities found."}, status_code=200
        )
    try:

        logger.info(
            f"Successfully fetched {len(activities)} activities for user_id: {user_id}"
        )

        # Store each activity in DynamoDB and count creates/updates
        create_count = 0
        update_count = 0
        error_count = 0
        for activity in activities:
            try:
                _, action = workout_helper.put_strava_workout(
                    user_id=user_id, workout_data=activity
                )
                if action == "create":
                    create_count += 1
                elif action == "update":
                    update_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"Failed to store activity for user_id {user_id}: {e}")
                logger.error(activity)

        return JSONResponse(
            content={
                "created": create_count,
                "updated": update_count,
                "error_count": error_count,
            },
            status_code=200,
        )
    except requests.RequestException as e:
        logger.error(f"Error fetching Strava activities: {e}")
        return JSONResponse(
            content={"error": "Error fetching Strava activities."}, status_code=500
        )
