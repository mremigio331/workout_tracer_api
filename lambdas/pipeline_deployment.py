import os
import boto3
import json
from aws_lambda_powertools import Logger
import hashlib
import time

logger = Logger(service="WorkoutTracer-Pipeline-Deployment")
client = boto3.client("codepipeline")


@logger.inject_lambda_context
def handler(event: dict, context) -> dict:
    logger.debug(f"Received event: {event}")

    pipeline = os.getenv("PIPELINE")
    if not pipeline:
        logger.error("Pipeline name is not set in environment variables.")
        raise ValueError("PIPELINE environment variable is required.")

    # Handle body decoding
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode()

    payload = json.loads(body)

    # Extract GitHub push event fields
    commit_id = payload.get("after")
    commit_message = payload.get("head_commit", {}).get("message", "unknown")
    repo = payload.get("repository", {}).get("full_name", "unknown")

    logger.info(f"Push to {repo} - Commit: {commit_id}, Message: {commit_message}")

    # Unique token for idempotency
    token_source = f"{repo}:{commit_id}:{time.time()}"
    client_request_token = hashlib.sha256(token_source.encode()).hexdigest()

    try:
        response = client.start_pipeline_execution(
            name=pipeline, clientRequestToken=client_request_token
        )
    except Exception as e:
        logger.exception(f"Failed to start pipeline execution: {e}")
        raise

    logger.append_keys(pipeline=pipeline)
    logger.info(
        f"Pipeline execution started with ID {response['pipelineExecutionId']}, "
        f"Repo: {repo}, Commit: {commit_id}, Message: {commit_message}"
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Pipeline execution started",
                "pipelineExecutionId": response["pipelineExecutionId"],
                "repo": repo,
                "commit_id": commit_id,
                "commit_message": commit_message,
            }
        ),
    }
