from fastapi import FastAPI

app = FastAPI(
    title="WorkoutTracer API",
    description="API for WorkoutTracer application.",
    version="1.0.0",
    docs_url="/docs",         # Swagger UI
    redoc_url="/redoc"        # ReDoc UI
)

@app.get("/")
async def root():
    return {"message": "Welcome to the WorkoutTracer API!"}