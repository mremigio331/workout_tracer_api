#!/bin/bash

export STAGE="Dev"
export COGNITO_USER_POOL_ID=$(aws cognito-idp list-user-pools --region us-west-2 --max-results 60 --query "UserPools[?Name=='WorkoutTracer-UserPool-Staging'].Id" --output text)
export COGNITO_CLIENT_ID=$(aws cognito-idp list-user-pools --max-results 60 --region us-west-2 \
--query "UserPools[].Id" --output text | xargs -n1 -I {} aws cognito-idp list-user-pool-clients \
    --user-pool-id {} --region us-west-2 \
    --query "UserPoolClients[?contains(ClientName, 'WorkoutTracerUserPoolClientStaging')].ClientId" \
    --output text
)
export COGNITO_REGION="us-west-2"
export COGNITO_API_REDIRECT_URI="http://localhost:5000/"
export COGNITO_DOMAIN="https://workouttracer-staging.auth.us-west-2.amazoncognito.com"
export KMS_KEY_ARN=$(aws kms describe-key --key-id alias/WorkoutTracer/API/Staging --query "KeyMetadata.Arn"  --region us-west-2 --output text)
export SQS_QUEUE_URL=$(aws sqs get-queue-url --queue-name "WorkoutTracer-RateLimitedBatcherQueue-Staging" --region us-west-2 --query "QueueUrl" --output text)
export API_URL="https://api.staging.workouttracer.com"
export STRAVA_ONBOARDING_LAMBDA_ARN=$(aws lambda get-function --function-name "WorkoutTracer-StravaOnboardingLambda-Staging" --region us-west-2 --query "Configuration.FunctionArn" --output text)

uvicorn app:app --reload --port 5000