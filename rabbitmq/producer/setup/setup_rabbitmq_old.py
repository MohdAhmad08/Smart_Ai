import pika
import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Single project-wide .env lives at the repo root, regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

user = os.getenv("RABBIT_MQ_USER")
pw = os.getenv("RABBIT_MQ_PASSWORD")
host = os.getenv("RABBIT_MQ_HOST")
port = int(os.getenv("RABBIT_MQ_PORT"))
exchange = os.getenv("RABBIT_MQ_EXCHANGE")

# Queue configurations
data_queue = os.getenv("RABBIT_MQ_QUEUE")
data_routing = os.getenv("RABBIT_MQ_ROUTING_KEY")

health_queue = os.getenv("RABBIT_MQ_HEALTH_DATA_QUEUE")
health_routing = os.getenv("RABBIT_MQ_HEALTH_DATA_ROUTING_KEY")

creds = pika.PlainCredentials(user, pw)

# Retry connection logic
max_retries = 10
retry_delay = 3

for attempt in range(max_retries):
    try:
        print(f"Attempting to connect to RabbitMQ (attempt {attempt + 1}/{max_retries})...")
        conn = pika.BlockingConnection(pika.ConnectionParameters(host=host, port=port, credentials=creds))
        print("Connected successfully!")
        break
    except pika.exceptions.AMQPConnectionError as e:
        if attempt < max_retries - 1:
            print(f"Connection failed. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
        else:
            print("Max retries reached. Exiting.")
            raise

ch = conn.channel()

# Declare the exchange
ch.exchange_declare(exchange=exchange, exchange_type='topic', durable=True)
print(f"✓ Exchange '{exchange}' declared (type: topic)")

# Declare and bind data queue
ch.queue_declare(queue=data_queue, durable=True)
ch.queue_bind(exchange=exchange, queue=data_queue, routing_key=data_routing)
print(f"✓ Queue '{data_queue}' declared and bound with routing key '{data_routing}'")

# Declare and bind health queue
ch.queue_declare(queue=health_queue, durable=True)
ch.queue_bind(exchange=exchange, queue=health_queue, routing_key=health_routing)
print(f"✓ Queue '{health_queue}' declared and bound with routing key '{health_routing}'")

conn.close()
print("\n✓ RabbitMQ setup completed successfully!")