from fastapi import FastAPI, Request, Depends
from mangum import Mangum
from aws_lambda_powertools import Logger
from middleware.request_id_middlware import RequestIdMiddleware
from middleware.memory_cleanup_middleware import MemoryCleanupMiddleware
from endpoints.get_all_routes import get_all_routes
from fastapi.middleware.cors import CORSMiddleware
from middleware.jtw_middleware import JWTMiddleware
from helpers.jwt import inject_user_token
from middleware.cognito_auth_middleware import CognitoAuthMiddleware
import os
import configparser
from starlette.middleware.base import BaseHTTPMiddleware

logger = Logger(service="workout-tracer-api")
app = FastAPI(
    title="WorkoutTracer API",
    description="API for WorkoutTracer application.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


stage = os.getenv("STAGE", "").lower()
if stage == "prod":
    allowed_origins = [
        "https://workouttracer.com",
        "https://miles4manny.com",
        "https://www.miles4manny.com",
    ]
elif stage == "staging":
    allowed_origins = [
        "https://staging.workouttracer.com",
        "https://staging.miles4manny.com",
        "http://localhost:3000",
        "http://localhost:8080",
    ]
else:
    allowed_origins = ["http://localhost:3000", "http://localhost:8080"]

app.add_middleware(CognitoAuthMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(JWTMiddleware)
app.add_middleware(MemoryCleanupMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

inject_user_token()

app = get_all_routes(app)

handler = Mangum(app)
