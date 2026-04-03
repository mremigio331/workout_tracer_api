import json
from aws_lambda_powertools import Logger
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from constants.general import KML_LOCATION_FILES, ALLOWLISTED_LOCATIONS

logger = Logger(service="workout-tracer-enrich-workout-locations")


def _enrich_workout(user_id, workout_id, request_id):
    workout_helper = StravaWorkoutHelper(request_id=request_id)

    workout = workout_helper.get_strava_workout(user_id, workout_id)
    if not workout:
        logger.error(f"Workout {workout_id} not found for user {user_id}.")
        raise ValueError(f"Workout {workout_id} not found.")

    polyline_str = (workout.get("map") or {}).get("summary_polyline")
    if not polyline_str:
        logger.info(f"No polyline for workout {workout_id}, skipping enrichment.")
        return {"message": "No polyline, skipped."}

    location_data = {}
    matched = []
    for location_type in ALLOWLISTED_LOCATIONS:
        kml_file = KML_LOCATION_FILES[location_type]
        logger.info(
            f"Starting KML lookup: location_type={location_type}, kml_file={kml_file}"
        )
        locaton_dict = workout_helper.get_location_badges(polyline_str, kml_file)
        workout_helper._kml_cache.pop(kml_file, None)
        logger.info(
            f"Finished KML lookup: location_type={location_type}, kml_file={kml_file}"
        )
        location_data[location_type] = locaton_dict
        matched.extend(name for name, hit in locaton_dict.items() if hit)

    workout_helper.update_workout_locations(user_id, workout_id, location_data)

    logger.info(f"Enriched workout {workout_id} for user {user_id}: matched={matched}")
    return {
        "user_id": user_id,
        "workout_id": workout_id,
        "matched_locations": matched,
    }


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None)
    logger.append_keys(request_id=request_id)

    records = event.get("Records", [])
    if records:
        batch_item_failures = []
        for record in records:
            body = json.loads(record["body"])
            user_id = body.get("user_id")
            workout_id = body.get("workout_id")
            if not user_id or not workout_id:
                logger.error(
                    f"Missing user_id or workout_id in SQS record: {record['messageId']}"
                )
                batch_item_failures.append({"itemIdentifier": record["messageId"]})
                continue
            logger.info(
                f"Processing enrichment for user_id={user_id}, workout_id={workout_id}"
            )
            try:
                _enrich_workout(user_id, workout_id, request_id)
            except Exception as e:
                logger.error(
                    f"Failed to enrich workout {workout_id} for user {user_id}: {e}"
                )
                batch_item_failures.append({"itemIdentifier": record["messageId"]})
        return {"batchItemFailures": batch_item_failures}

    # Direct invocation (backward compat)
    user_id = event.get("user_id")
    workout_id = event.get("workout_id")
    if not user_id or not workout_id:
        logger.error("Missing user_id or workout_id in event.")
        return {"error": "user_id and workout_id are required."}

    logger.info(f"Starting enrichment for user_id={user_id}, workout_id={workout_id}")
    return _enrich_workout(user_id, workout_id, request_id)
