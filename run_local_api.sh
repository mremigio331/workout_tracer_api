#!/bin/bash

export STAGE="Dev"
export COGNITO_USER_POOL_ID=$(aws cognito-idp list-user-pools --region us-west-2 --max-results 60 --query "UserPools[?Name=='WorkoutTracer-UserPool-Staging'].Id" --output text)

uvicorn app:app --reload