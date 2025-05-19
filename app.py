from fastapi import FastAPI, Request, Depends
from mangum import Mangum
from aws_lambda_powertools import Logger
from middleware.request_id_middlware import RequestIdMiddleware
from endpoints.get_all_routes import get_all_routes

logger = Logger(service="workout-tracer-api")
app = FastAPI(
    title="WorkoutTracer API",
    description="API for WorkoutTracer application.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(RequestIdMiddleware)
app = get_all_routes(app)

handler = Mangum(app)