from endpoints.workout_tracer import home
from endpoints.user import (
    get_user_profile,
    get_requestors_profile,
    update_user_profile,
    update_strava_callback,
)


def get_all_routes(app):
    """Register all routers to the FastAPI app."""

    # General
    app.include_router(home.router, tags=["General"])

    # User
    app.include_router(get_user_profile.router, prefix="/user", tags=["User"])
    app.include_router(update_user_profile.router, prefix="/user", tags=["User"])
    app.include_router(get_requestors_profile.router, prefix="/user", tags=["User"])
    app.include_router(update_strava_callback.router, prefix="/user", tags=["User"])

    return app
