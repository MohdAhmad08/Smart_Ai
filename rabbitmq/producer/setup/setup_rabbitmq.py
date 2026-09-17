#!/usr/bin/env python3
# setup_rabbitmq.py — robust startup/bootstrap for RabbitMQ (fixed global/host bug)
import os
import time
import random
import socket
import sys
from pathlib import Path
from dotenv import load_dotenv

# Single project-wide .env lives at the repo root, regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

def get_env(*names, default=None):
    for n in names:
        v = os.getenv(n)
        if v is not None and v != "":
            return v
    return default

USER = get_env("RABBIT_MQ_USER", "RABBITMQ_USER", "RABBIT_USER", default="guest")
PW   = get_env("RABBIT_MQ_PASSWORD", "RABBITMQ_PASSWORD", "RABBIT_PASS", default="guest")

# Module-level defaults (not mutated)
HOST = get_env("RABBIT_MQ_HOST", "RABBITMQ_HOST", "RABBIT_HOST", "RABBITMQ_SERVICE", default="rabbitmq")
PORT = int(get_env("RABBIT_MQ_PORT", "RABBITMQ_PORT", default=5672))

FALLBACK = get_env("RABBITMQ_FALLBACK", "RABBIT_MQ_FALLBACK", default=None)

EXCHANGE = get_env("RABBIT_MQ_EXCHANGE", "RABBITMQ_EXCHANGE", default="rabbitinflux.exchange")
DATA_QUEUE = get_env("RABBIT_MQ_QUEUE", "RABBITMQ_QUEUE", default="data.queue")
DATA_ROUTING = get_env("RABBIT_MQ_ROUTING_KEY", "RABBITMQ_ROUTING_KEY", default="data.routing")

HEALTH_QUEUE = get_env("RABBIT_MQ_HEALTH_DATA_QUEUE", "RABBITMQ_HEALTH_QUEUE", default="health.queue")
HEALTH_ROUTING = get_env("RABBIT_MQ_HEALTH_DATA_ROUTING_KEY", "RABBITMQ_HEALTH_ROUTING_KEY", default="health.routing")

MAX_ATTEMPTS = int(get_env("RABBIT_SETUP_MAX_ATTEMPTS", default=60))
BASE_DELAY = float(get_env("RABBIT_SETUP_BASE_DELAY", default=1.0))
MAX_DELAY = float(get_env("RABBIT_SETUP_MAX_DELAY", default=30.0))

try:
    import pika
except Exception as e:
    print("Missing dependency 'pika' or failed to import it:", e)
    raise

def try_resolve(hostname, port):
    try:
        socket.getaddrinfo(hostname, port)
        return True
    except socket.gaierror:
        return False

def connect_with_retries():
    """
    Use a local 'host' variable (do not mutate module-level HOST).
    On DNS failure try FALLBACK (if provided). Return open connection.
    """
    creds = pika.PlainCredentials(USER, PW)
    host = HOST  # local copy we may change
    params = pika.ConnectionParameters(host=host, port=PORT, credentials=creds)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Attempt {attempt}/{MAX_ATTEMPTS} — resolving {host}:{PORT} ...")
            if not try_resolve(host, PORT):
                print(f"  DNS lookup failed for {host}.")
                if FALLBACK and host != FALLBACK:
                    print(f"  Trying fallback host: {FALLBACK}")
                    host = FALLBACK
                    params = pika.ConnectionParameters(host=host, port=PORT, credentials=creds)
                else:
                    print("  No fallback or fallback already tried. Will retry DNS after backoff.")
            else:
                print(f"  Hostname {host} resolved — attempting AMQP connect...")
                conn = pika.BlockingConnection(params)
                print(f"Connected to RabbitMQ at {host}:{PORT}")
                return conn

        except pika.exceptions.AMQPConnectionError as e:
            print(f"  AMQP connection error: {e}")
        except Exception as e:
            print(f"  Unexpected error while connecting: {type(e).__name__}: {e}")

        delay = min(MAX_DELAY, BASE_DELAY * (2 ** (attempt - 1)))
        jitter = random.uniform(0, delay * 0.1)
        sleep_time = delay + jitter
        print(f"  Waiting {sleep_time:.1f}s before next attempt...")
        time.sleep(sleep_time)

    raise SystemExit(f"Could not connect to RabbitMQ at {HOST}:{PORT} after {MAX_ATTEMPTS} attempts")

def main():
    print("Starting RabbitMQ setup script with configuration:")
    print(f"  USER={USER}, HOST={HOST}, PORT={PORT}, EXCHANGE={EXCHANGE}")

    print("Waiting 10 seconds for RabbitMQ AMQP to be fully ready...")
    time.sleep(10)

    try:
        conn = connect_with_retries()
    except SystemExit as e:
        print(str(e))
        sys.exit(1)

    try:
        ch = conn.channel()

        ch.exchange_declare(exchange=EXCHANGE, exchange_type='topic', durable=True)
        print(f"✓ Exchange '{EXCHANGE}' declared (type: topic)")

        ch.queue_declare(queue=DATA_QUEUE, durable=True)
        ch.queue_bind(exchange=EXCHANGE, queue=DATA_QUEUE, routing_key=DATA_ROUTING)
        print(f"✓ Queue '{DATA_QUEUE}' declared and bound with routing key '{DATA_ROUTING}'")

        ch.queue_declare(queue=HEALTH_QUEUE, durable=True)
        ch.queue_bind(exchange=EXCHANGE, queue=HEALTH_QUEUE, routing_key=HEALTH_ROUTING)
        print(f"✓ Queue '{HEALTH_QUEUE}' declared and bound with routing key '{HEALTH_ROUTING}'")

    except Exception as e:
        print("Failed during queue/exchange declaration:", type(e).__name__, e)
        try:
            conn.close()
        except Exception:
            pass
        sys.exit(2)

    conn.close()
    print("✓ RabbitMQ setup completed successfully!")
    sys.exit(0)

if __name__ == "__main__":
    main()
