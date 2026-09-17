FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY machine_data_generator.py .
COPY publisher.py .
COPY backfill.py .

CMD ["python", "publisher.py"]
