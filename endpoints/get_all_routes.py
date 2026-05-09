from endpoints.workout_tracer import home
from endpoints.user import (
    get_user_profile,
    get_requestors_profile,
    update_user_profile,
    get_public_users,
)
from endpoints.health import (
    import_health_workouts,
    get_health_workouts,
    get_health_workout_ids,
    delete_health_workout,
)
from endpoints.public import (
    get_public_workouts,
    get_public_profile,
    get_public_workout_locations as public_workout_locations,
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
    miles_for_manny,
    miles_for_manny_stats,
    get_workout_locations,
)


def get_all_routes(app):
    """Register all routers to the FastAPI app."""

    # General
    app.include_router(home.router, tags=["General"])

    # Apple Health
    app.include_router(
        import_health_workouts.router, prefix="/applehealth", tags=["AppleHealth"]
    )
    app.include_router(
        get_health_workouts.router, prefix="/applehealth", tags=["AppleHealth"]
    )
    app.include_router(
        get_health_workout_ids.router, prefix="/applehealth", tags=["AppleHealth"]
    )
    app.include_router(
        delete_health_workout.router, prefix="/applehealth", tags=["AppleHealth"]
    )

    # Public
    app.include_router(get_public_workouts.router, prefix="/public", tags=["Public"])
    app.include_router(get_public_profile.router, prefix="/public", tags=["Public"])
    app.include_router(
        public_workout_locations.router, prefix="/public", tags=["Public"]
    )

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
    app.include_router(miles_for_manny.router, prefix="/strava", tags=["Strava"])
    app.include_router(miles_for_manny_stats.router, prefix="/strava", tags=["Strava"])
    app.include_router(get_workout_locations.router, prefix="/strava", tags=["Strava"])

    # User
    app.include_router(get_user_profile.router, prefix="/user", tags=["User"])
    app.include_router(update_user_profile.router, prefix="/user", tags=["User"])
    app.include_router(get_requestors_profile.router, prefix="/user", tags=["User"])
    app.include_router(get_public_users.router, prefix="/user", tags=["User"])

    return app
