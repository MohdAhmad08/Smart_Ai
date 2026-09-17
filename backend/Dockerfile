# Backend API image — serves the dashboard API + loads the Production model.
# Build from the REPO ROOT so ml/ is in the context:
#   docker build -f backend/Dockerfile -t taha-backend .
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements-backend.txt
RUN pip install --no-cache-dir -r requirements-backend.txt

# Shared ML package (feature engineering, registry loader) + the API app
COPY ml/ ./ml/
COPY backend/app/ ./app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
