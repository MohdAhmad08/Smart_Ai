# consumer.py
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pika
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Single project-wide .env lives at the repo root, regardless of cwd.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("consumer")

# ===== MySQL Config =====
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/machine_telemetry?charset=utf8mb4",
)

_engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=_engine)


def _create_tables() -> None:
    with _engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS machine_readings (
                id               BIGINT       PRIMARY KEY AUTO_INCREMENT,
                session_id       VARCHAR(36)  NOT NULL,
                seq              INT          NOT NULL,
                machine_name     VARCHAR(64)  NOT NULL,
                state            VARCHAR(16)  NOT NULL,
                ts               DATETIME(3)  NOT NULL,
                lot_1            INT,
                lot_2            INT,
                article          VARCHAR(32),
                speed            FLOAT,
                length           FLOAT,
                lot_time_s       INT,
                machine_time_s   INT,
                steam_consumed_lot  FLOAT,
                water_consumed_lot  FLOAT,
                power_consumed_lot  FLOAT,
                air_consumed_lot    FLOAT,
                sf_flow          FLOAT,
                sf_tot           FLOAT,
                wat_flow         FLOAT,
                wat_tot          FLOAT,
                em_power         FLOAT,
                em_energy        FLOAT,
                vibration_rms    FLOAT,
                motor_current    FLOAT,
                bearing_temp     FLOAT,
                winding_temp     FLOAT,
                air_pressure     FLOAT,
                good_count       INT,
                reject_count     INT,
                truth_json       JSON,
                UNIQUE KEY uq_reading_session_seq (session_id, seq),
                KEY idx_reading_ts (ts),
                KEY idx_reading_machine (machine_name),
                KEY idx_reading_lot (lot_1)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS machine_runs (
                id                     BIGINT      PRIMARY KEY AUTO_INCREMENT,
                session_id             VARCHAR(36) NOT NULL,
                machine_name           VARCHAR(64) NOT NULL,
                component              VARCHAR(32),
                severity               VARCHAR(16),
                run_start_ts           DATETIME(3),
                failure_ts             DATETIME(3),
                repair_ts              DATETIME(3),
                run_hours_to_failure   FLOAT,
                seq_at_failure         INT,
                KEY idx_run_session  (session_id),
                KEY idx_run_machine  (machine_name),
                KEY idx_run_failure  (failure_ts),
                KEY idx_run_component(component)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
    logger.info("Tables ensured.")


# ===== Parsing helpers =====

def _hms_to_seconds(value) -> int:
    """Convert 'H:M:S' string to seconds."""
    if not value:
        return 0
    try:
        parts = [int(p) for p in str(value).split(":")]
    except ValueError:
        return 0
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _to_f(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_ts(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


# ===== Flatten JSON → flat row dict =====

_INSERT_READING = text("""
    INSERT IGNORE INTO machine_readings
        (session_id, seq, machine_name, state, ts,
         lot_1, lot_2, article, speed, length, lot_time_s, machine_time_s,
         steam_consumed_lot, water_consumed_lot, power_consumed_lot, air_consumed_lot,
         sf_flow, sf_tot, wat_flow, wat_tot, em_power, em_energy,
         vibration_rms, motor_current, bearing_temp, winding_temp, air_pressure,
         good_count, reject_count, truth_json)
    VALUES
        (:session_id, :seq, :machine_name, :state, :ts,
         :lot_1, :lot_2, :article, :speed, :length, :lot_time_s, :machine_time_s,
         :steam_consumed_lot, :water_consumed_lot, :power_consumed_lot, :air_consumed_lot,
         :sf_flow, :sf_tot, :wat_flow, :wat_tot, :em_power, :em_energy,
         :vibration_rms, :motor_current, :bearing_temp, :winding_temp, :air_pressure,
         :good_count, :reject_count, :truth_json)
""")

_INSERT_RUN = text("""
    INSERT INTO machine_runs
        (session_id, machine_name, component, severity,
         run_start_ts, failure_ts, repair_ts,
         run_hours_to_failure, seq_at_failure)
    VALUES
        (:session_id, :machine_name, :component, :severity,
         :run_start_ts, :failure_ts, :repair_ts,
         :run_hours_to_failure, :seq_at_failure)
""")


def _flatten_reading(data: dict) -> dict:
    plc     = data.get("plc", {}) or {}
    util    = data.get("utility", {}) or {}
    health  = data.get("health", {}) or {}
    quality = data.get("quality", {}) or {}
    truth   = data.get("_truth")

    return {
        "session_id":  data.get("session_id"),
        "seq":         data.get("seq"),
        "machine_name": data.get("machine_name"),
        "state":       data.get("state", "idle"),
        "ts":          _parse_ts(data.get("timestamp")),
        # PLC
        "lot_1":   plc.get("lot_1"),
        "lot_2":   plc.get("lot_2"),
        "article": plc.get("article"),
        "speed":   _to_f(plc.get("speed")),
        "length":  _to_f(plc.get("length")),
        "lot_time_s":     _hms_to_seconds(plc.get("lot_time")),
        "machine_time_s": _hms_to_seconds(plc.get("machine_time")),
        "steam_consumed_lot": _to_f(plc.get("steam_consumed_lot")),
        "water_consumed_lot": _to_f(plc.get("water_consumed_lot")),
        "power_consumed_lot": _to_f(plc.get("power_consumed_lot")),
        "air_consumed_lot":   _to_f(plc.get("air_consumed_lot")),
        # Utility
        "sf_flow":  _to_f(util.get("SF_Flow")),
        "sf_tot":   _to_f(util.get("SF_Tot")),
        "wat_flow": _to_f(util.get("Wat_Flow")),
        "wat_tot":  _to_f(util.get("Wat_Tot")),
        "em_power": _to_f(util.get("EM_Power")),
        "em_energy": _to_f(util.get("EM_Energy")),
        # Sensor readings (from "health" sub-dict)
        "vibration_rms": _to_f(health.get("vibration_rms")),
        "motor_current": _to_f(health.get("motor_current")),
        "bearing_temp":  _to_f(health.get("bearing_temp")),
        "winding_temp":  _to_f(health.get("winding_temp")),
        "air_pressure":  _to_f(health.get("air_pressure")),
        # Quality
        "good_count":   quality.get("good_count"),
        "reject_count": quality.get("reject_count"),
        # Truth blob
        "truth_json": json.dumps(truth) if truth is not None else None,
    }


def _flatten_event(data: dict) -> dict:
    return {
        "session_id":   data.get("session_id"),
        "machine_name": data.get("machine_name"),
        "component":    data.get("component"),
        "severity":     data.get("severity"),
        "run_start_ts": _parse_ts(data.get("run_start_ts")),
        "failure_ts":   _parse_ts(data.get("failure_ts")),
        "repair_ts":    _parse_ts(data.get("repair_ts")),
        "run_hours_to_failure": data.get("run_hours_to_failure"),
        "seq_at_failure":       data.get("seq_at_failure"),
    }


# ===== Write helpers =====

def write_reading(data: dict) -> None:
    row = _flatten_reading(data)
    try:
        with _engine.begin() as conn:
            conn.execute(_INSERT_READING, row)
        logger.info(
            "reading → session=%s  machine=%s  seq=%s  state=%s",
            str(row.get("session_id", "?"))[:8],
            row.get("machine_name", "?"),
            row.get("seq", "?"),
            row.get("state", "?"),
        )
    except Exception as e:
        logger.error("ERROR writing reading: %s", e)


def write_event(data: dict) -> None:
    row = _flatten_event(data)
    try:
        with _engine.begin() as conn:
            conn.execute(_INSERT_RUN, row)
        logger.info(
            "event   → machine=%s  component=%s  severity=%s",
            row.get("machine_name", "?"),
            row.get("component", "?"),
            row.get("severity", "?"),
        )
    except Exception as e:
        logger.error("ERROR writing event: %s", e)


# ===== RabbitMQ Config =====
RABBIT_USER    = os.getenv("RABBIT_MQ_USER")
RABBIT_PASS    = os.getenv("RABBIT_MQ_PASSWORD")
RABBIT_HOST    = os.getenv("RABBIT_MQ_HOST")
RABBIT_PORT    = int(os.getenv("RABBIT_MQ_PORT", "5672"))

EXCHANGE       = os.getenv("RABBIT_MQ_EXCHANGE",          "scada_data")
QUEUE          = os.getenv("RABBIT_MQ_QUEUE",             "scada_data_queue")
ROUTING        = os.getenv("RABBIT_MQ_ROUTING_KEY",       "scada.tag.data")
EVENT_QUEUE    = os.getenv("RABBIT_MQ_EVENT_QUEUE",       "machine_event_queue")
EVENT_ROUTING  = os.getenv("RABBIT_MQ_EVENT_ROUTING_KEY", "scada.machine.event")
HEALTH_QUEUE   = os.getenv("RABBIT_MQ_HEALTH_DATA_QUEUE",          "sensor_health_data_queue")
HEALTH_ROUTING = os.getenv("RABBIT_MQ_HEALTH_DATA_ROUTING_KEY",    "scada.sensor.health")


# ===== Message handlers =====

def on_message(ch, method, props, body):
    try:
        write_reading(json.loads(body))
    except Exception as e:
        logger.error("Error processing reading message: %s", e)
    ch.basic_ack(method.delivery_tag)


def on_event_message(ch, method, props, body):
    try:
        write_event(json.loads(body))
    except Exception as e:
        logger.error("Error processing event message: %s", e)
    ch.basic_ack(method.delivery_tag)


def on_health_message(ch, method, props, body):
    try:
        logger.info("Health message received: %s", json.loads(body))
    except Exception as e:
        logger.error("Error processing health message: %s", e)
    ch.basic_ack(method.delivery_tag)


def connect_and_consume():
    _create_tables()
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)

    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBIT_HOST,
                    port=RABBIT_PORT,
                    credentials=creds,
                    heartbeat=600,
                    blocked_connection_timeout=300,
                )
            )
            logger.info("Connected to RabbitMQ")
            ch = connection.channel()
            ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)

            ch.queue_declare(queue=QUEUE, durable=True)
            ch.queue_bind(exchange=EXCHANGE, queue=QUEUE, routing_key=ROUTING)
            ch.basic_consume(queue=QUEUE, on_message_callback=on_message)
            logger.info("Listening: '%s' (%s)", QUEUE, ROUTING)

            ch.queue_declare(queue=EVENT_QUEUE, durable=True)
            ch.queue_bind(exchange=EXCHANGE, queue=EVENT_QUEUE, routing_key=EVENT_ROUTING)
            ch.basic_consume(queue=EVENT_QUEUE, on_message_callback=on_event_message)
            logger.info("Listening: '%s' (%s)", EVENT_QUEUE, EVENT_ROUTING)

            ch.queue_declare(queue=HEALTH_QUEUE, durable=True)
            ch.queue_bind(exchange=EXCHANGE, queue=HEALTH_QUEUE, routing_key=HEALTH_ROUTING)
            ch.basic_consume(queue=HEALTH_QUEUE, on_message_callback=on_health_message)
            logger.info("Listening: '%s' (%s)", HEALTH_QUEUE, HEALTH_ROUTING)

            logger.info("Waiting for messages...")
            ch.start_consuming()

        except Exception as e:
            logger.warning("RabbitMQ not available, retrying in 5s: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    connect_and_consume()
