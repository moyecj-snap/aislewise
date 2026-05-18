# Aislewise API

Render-ready FastAPI service for the Aislewise MVP.

## Local Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Endpoints

- `GET /api/health`
- `POST /api/recommend`

`POST /api/recommend` accepts multipart form fields:

- `budget`
- `food`
- `occasion`
- `photo` optional image upload

The endpoint returns detected wines and the top two recommendations.
