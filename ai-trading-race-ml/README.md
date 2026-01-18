# AI Trading Race - ML Service

Custom ML model for trading decisions, exposed via FastAPI.

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Run

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

| Method | Path       | Description                    |
| ------ | ---------- | ------------------------------ |
| GET    | `/health`  | Health check with model status |
| POST   | `/predict` | Generate trading decision      |

## Environment Variables

| Variable                    | Description                | Default                    |
| --------------------------- | -------------------------- | -------------------------- |
| `ML_SERVICE_MODEL_PATH`     | Path to trained model      | `models/trading_model.pkl` |
| `ML_SERVICE_MODEL_VERSION`  | Model version string       | `1.0.0`                    |
| `ML_SERVICE_API_KEY`        | API key for authentication | (required)                 |
| `ML_SERVICE_ALLOWED_ORIGIN` | CORS allowed origin        | `*`                        |

## Project Structure

```
ai-trading-race-ml/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── models/schemas.py    # Pydantic models
│   ├── ml/                  # ML predictor & features
│   ├── services/            # Business logic
│   └── middleware/          # Authentication
├── models/                  # Saved ML models
├── data/                    # Training data
├── tests/                   # Unit tests
└── requirements.txt
```
