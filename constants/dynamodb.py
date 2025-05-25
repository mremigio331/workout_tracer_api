import os

stage = os.getenv("STAGE", "dev")
WORKOUT_TRACER_USER_TABLE = f"WorkoutTracer-UserTable-{stage}"
