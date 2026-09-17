# Lifecycle worker image — APScheduler driving seal/retrain/drift/feedback.
# Build from the REPO ROOT:
#   docker build -f ml/Dockerfile -t taha-ml-scheduler .
FROM python:3.11-slim

WORKDIR /app

COPY ml/requirements.txt ./requirements-ml.txt
RUN pip install --no-cache-dir -r requirements-ml.txt

COPY ml/ ./ml/

ENV PYTHONUTF8=1
CMD ["python", "-m", "ml.schedule"]
