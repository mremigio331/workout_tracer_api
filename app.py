from fastapi import FastAPI
from mangum import Mangum
from aws_lambda_powertools import Logger

# Set up structured logger
logger = Logger(service="workout-tracer-api")
app = FastAPI(
    title="WorkoutTracer API",
    description="API for WorkoutTracer application.",
    version="1.0.0",
    docs_url="/docs",         # Swagger UI
    redoc_url="/redoc"        # ReDoc UI
)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Welcome to the WorkoutTracer API!"}

# 👇 This makes FastAPI work with AWS Lambda
handler = Mangum(app)