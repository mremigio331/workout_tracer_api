from fastapi import FastAPI, Request, Depends
from mangum import Mangum
from aws_lambda_powertools import Logger
from middleware.request_id_middlware import RequestIdMiddleware
from endpoints.get_all_routes import get_all_routes
from fastapi.middleware.cors import CORSMiddleware
from middleware.jtw_middleware import JWTMiddleware
from middleware.dev_token_middleware import DevTokenMiddleware
from starlette.datastructures import MutableHeaders
import os
import configparser

logger = Logger(service="workout-tracer-api")
app = FastAPI(
    title="WorkoutTracer API",
    description="API for WorkoutTracer application.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

def inject_dev_token():
    config = configparser.ConfigParser()
    # Go up one directory to reach workout_tracer_api root
    root_dir = os.path.dirname(__file__)
    cfg_path = os.path.join(root_dir, "dev_creds.cfg")
    abs_cfg_path = os.path.abspath(cfg_path)
    logger.info(f"Injecting dev token: Reading config from {abs_cfg_path}")
    config.read(abs_cfg_path)
    id_token = config.get("default", "id_token", fallback=None)
    if id_token:
        from starlette.requests import Request as StarletteRequest
        orig_init = StarletteRequest.__init__
        def new_init(self, *args, **kwargs):
            scope = args[0]
            headers = list(scope.get("headers", []))
            if not any(k == b"authorization" for k, v in headers):
                headers.append(
                    (b"authorization", f"Bearer {id_token}".encode("latin-1"))
                )
                scope["headers"] = headers
            orig_init(self, *args, **kwargs)
        StarletteRequest.__init__ = new_init
        logger.info("Injecting dev token: Authorization header will be injected into all requests.")
    else:
        logger.warning("Injecting dev token: No id_token found in dev_creds.cfg.")

stage = os.getenv("STAGE", "").lower()
if stage == "prod":
    allowed_origins = ["https://workouttracer.com"]
else:
    allowed_origins = ["*"]

if stage == 'dev':
    logger.info("Running in development mode, allowing all origins for CORS.")
    inject_dev_token()
    logger.info("Dev token injection enabled.")


app.add_middleware(RequestIdMiddleware)
app.add_middleware(JWTMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app = get_all_routes(app)

handler = Mangum(app)
