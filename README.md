# Workout Tracer API

Python backend API for the Workout Tracer application. Built with FastAPI and deployed to AWS Lambda via Mangum.

## Tech Stack

- **Framework**: FastAPI + Mangum (AWS Lambda adapter)
- **Database**: DynamoDB
- **Auth**: AWS Cognito (JWT middleware)
- **Logging**: AWS Lambda Powertools

## Project Structure

```
workout_tracer_api/
├── app.py              # FastAPI app entry point
├── clients/            # External service clients
├── constants/          # Application constants
├── decorators/         # Custom decorators
├── dynamodb/           # DynamoDB models and operations
├── endpoints/          # API route handlers
│   ├── health/         # Apple Health workout endpoints
│   ├── public/         # Public profile/workout endpoints
│   ├── strava/         # Strava integration endpoints
│   └── user/           # User profile endpoints
├── exceptions/         # Custom exception classes
├── helpers/            # Utility functions
├── lambdas/            # Lambda function handlers
├── middleware/         # Request/response middleware
└── ops_tools/          # Operational tooling
```

## API Endpoint Groups

| Prefix | Description |
|--------|-------------|
| `/applehealth` | Import and manage Apple Health workouts |
| `/public` | Public workout and profile data |
| `/strava` | Strava OAuth, webhook, and workout sync |
| `/user` | User profile management |

## Getting Started

### Prerequisites

- Python 3.x
- AWS credentials configured

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Locally

```bash
./run_local_api.sh
```

The API will be available at `http://localhost:8000` with interactive docs at `/docs`.

### Create Lambda Layer

```bash
./create_lambda_layer.sh
```

## Environment Variables

- `STAGE` — Deployment stage (`prod`, `staging`, or local). Controls CORS allowed origins.

## API Documentation

When running locally, FastAPI auto-generates interactive docs:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
