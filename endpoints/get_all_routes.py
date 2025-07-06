from endpoints.workout_tracer import home
from endpoints.user import (
    get_user_profile,
    get_requestors_profile,
    update_user_profile,
    get_public_users,
)
from endpoints.strava import (
    get_requestor_strava_profile,
    get_strava_profile,
    update_strava_callback,
    identify_strava_workouts,
    update_strava_workout,
    get_strava_workouts,
    strava_webhook_verification,
    strava_webhook_event,
    get_public_strava_workouts,
    get_public_strava_profile,
)


def get_all_routes(app):
    """Register all routers to the FastAPI app."""

    # General
    app.include_router(home.router, tags=["General"])

    # User
    app.include_router(get_user_profile.router, prefix="/user", tags=["User"])
    app.include_router(update_user_profile.router, prefix="/user", tags=["User"])
    app.include_router(get_requestors_profile.router, prefix="/user", tags=["User"])
    app.include_router(get_public_users.router, prefix="/user", tags=["User"])

    # Strava
    app.include_router(
        get_requestor_strava_profile.router, prefix="/strava", tags=["Strava"]
    )
    app.include_router(get_strava_profile.router, prefix="/strava", tags=["Strava"])
    app.include_router(
        identify_strava_workouts.router, prefix="/strava", tags=["Strava"]
    )
    app.include_router(update_strava_callback.router, prefix="/strava", tags=["Strava"])
    app.include_router(update_strava_workout.router, prefix="/strava", tags=["Strava"])
    # app.include_router(
    #     batch_update_strava_workout.router, prefix="/strava", tags=["Strava"]
    # )
    app.include_router(get_strava_workouts.router, prefix="/strava", tags=["Strava"])
    # app.include_router(
    #     update_all_strava_workouts.router, prefix="/strava", tags=["Strava"]
    # )
    app.include_router(
        strava_webhook_verification.router, prefix="/strava", tags=["Strava"]
    )
    app.include_router(strava_webhook_event.router, prefix="/strava", tags=["Strava"])
    app.include_router(
        get_public_strava_workouts.router, prefix="/strava", tags=["Strava"]
    )
    app.include_router(
        get_public_strava_profile.router, prefix="/strava", tags=["Strava"]
    )

    return app
