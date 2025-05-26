from fastapi import FastAPI, Request, Depends
from mangum import Mangum
from aws_lambda_powertools import Logger
from middleware.request_id_middlware import RequestIdMiddleware
from endpoints.get_all_routes import get_all_routes
from fastapi.middleware.cors import CORSMiddleware
import os


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
    allowed_origins = ["https://workouttracer.com"]
else:
    allowed_origins = ["*"]

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app = get_all_routes(app)

handler = Mangum(app)
