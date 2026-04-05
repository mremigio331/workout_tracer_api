from aws_lambda_powertools import Logger
from dynamodb.helpers.strava_workout_helper import StravaWorkoutHelper
from dynamodb.helpers.user_profile_helper import UserProfileHelper
import os
import json
import boto3

logger = Logger(service="workout-tracer-backfill-location-badges")


def lambda_handler(event, context):
    """
    Backfill location badges for a user's workouts by enqueuing them
    to the enrichment FIFO SQS queue.

    Event schema:
      { "user_id": "abc123" }          # single user
      { "user_id": ["abc123", "xyz"] } # multiple users
      { "all_users": true }            # every user in the table
    """
    request_id = getattr(context, "aws_request_id", None)
    logger.append_keys(request_id=request_id)

    user_id = event.get("user_id")
    all_users = event.get("all_users", False)

    if user_id and all_users:
        return {"error": "Cannot specify both user_id and all_users."}
    if not user_id and not all_users:
        return {"error": "Must specify either user_id or all_users."}

    enrich_sqs_url = os.getenv("ENRICH_SQS_QUEUE_URL")
    if not enrich_sqs_url:
        logger.error("ENRICH_SQS_QUEUE_URL environment variable not set.")
        return {"error": "Enrich SQS queue URL not configured."}

    workout_helper = StravaWorkoutHelper(request_id=request_id)
    sqs = boto3.client("sqs")

    if all_users:
        user_ids = UserProfileHelper(request_id=request_id).get_all_user_ids()
        logger.info(f"all_users=True: found {len(user_ids)} users")
    else:
        user_ids = [user_id] if isinstance(user_id, str) else user_id

    results = []
    for uid in user_ids:
        published, errors, total = _enqueue_workouts(
            workout_helper, sqs, enrich_sqs_url, uid
        )
        logger.info(
            f"Enqueued {published}/{total} workouts for user {uid}, errors={errors}"
        )
        results.append(
            {
                "user_id": uid,
                "total_workouts": total,
                "published": published,
                "errors": errors,
            }
        )

    return {"results": results}


def _enqueue_workouts(workout_helper, sqs, enrich_sqs_url, user_id):
    published = 0
    errors = 0
    total = 0
    next_token = None

    while True:
        result = workout_helper.get_all_workouts(
            user_id,
            next_token=next_token,
            projection_expression="id",
        )
        workouts = result.get("workouts", [])
        logger.info(
            f"Fetched {len(workouts)} workouts for user {user_id} (paginating={next_token is not None})"
        )

        for workout in workouts:
            workout_id = workout.get("id")
            if workout_id is None:
                continue
            workout_id = int(workout_id)
            total += 1
            try:
                sqs.send_message(
                    QueueUrl=enrich_sqs_url,
                    MessageBody=json.dumps(
                        {
                            "user_id": user_id,
                            "workout_id": workout_id,
                        }
                    ),
                    MessageGroupId=str(user_id),
                )
                published += 1
            except Exception as e:
                logger.error(
                    f"Failed to enqueue workout_id {workout_id} for user {user_id}: {e}"
                )
                errors += 1

        next_token = result.get("next_token")
        if not next_token:
            break

    return published, errors, total
