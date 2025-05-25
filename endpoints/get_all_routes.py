from endpoints.workout_tracer import home
from endpoints.user import get_user_profile


def get_all_routes(app):
    """Register all routers to the FastAPI app."""

    # General
    app.include_router(home.router, tags=["General"])

    # User
    app.include_router(get_user_profile.router, prefix="/user", tags=["User"])

    return app
