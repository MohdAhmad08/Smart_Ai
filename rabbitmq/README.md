# RabbitMQ Producer-Consumer Setup Guide

This guide explains how to set up and run the RabbitMQ producer and consumer system, both locally and across different machines.

## Project Structure

```
rabbitinflux/
├── producer/
│   ├── setup/
│   │   ├── docker-compose.yml
│   │   ├── Dockerfile
│   │   ├── setup_rabbitmq.py
│   │   └── requirements.txt
│   ├── publisher/
│   │   ├── docker-compose.yml
│   │   ├── Dockerfile
│   │   ├── publisher.py
│   │   └── requirements.txt
│   └── .env
└── consumer/
    ├── docker-compose.yml
    ├── Dockerfile
    ├── consumer.py
    └── requirements.txt
```

---

## Setup Instructions

### **1. Running RabbitMQ Broker & Queue (Machine A)**

To run the **publisher**, you must navigate into the project directory and then into:

```bash
cd rabbitinflux
cd producer
cd publisher
```

### **Publisher Environment File (Required)**

Inside the `publisher/` directory, create or edit a file named:

```bash
.env
```

Example `producer/publisher/.env`:

```env
# RabbitMQ Connection
RABBIT_MQ_USER=guest
RABBIT_MQ_PASSWORD=guest
RABBIT_MQ_HOST=<Provided>
RABBIT_MQ_PORT=5672

# RabbitMQ Topology
RABBIT_MQ_EXCHANGE=scada_data
RABBIT_MQ_ROUTING_KEY=scada.tag.data
RABBIT_MQ_HEALTH_DATA_ROUTING_KEY=scada.sensor.health
```

### **Build & Run Publisher (Required Commands)**

Run the following commands **from inside the ****\*\*******\*\*******\*\*******producer/publisher****\*\*\*\*****\*\*\*\*****\*\*\*\***** directory\*\*:

```bash
docker compose build --no-cache
docker compose up
```

**What this does:**

- Builds the publisher image from scratch (no cache)
- Starts the publisher container
- Connects to RabbitMQ using the provided static IP
- Publishes SCADA + health data continuously

### **Verify Publisher Output**

```bash
docker logs -f scada-publisher
```

You should see output similar to:

```
[0] Sent: {'sensor_id': 'sensor-0', 'value': 20, 'unit': 'C'}
```

---

# Access management UI

# http://localhost:15672

## ⚠️ Notes

- Ensure RabbitMQ is already running before starting the publisher
- Ensure port `5672` is open on the RabbitMQ host machine
- The publisher `.env` file is **separate** from `producer/.env`
- Do NOT run the publisher from the project root

---

### **Remote Setup (Producer on Machine A, Consumer on Machine B):**

**Machine A (Producer):**

````bash
# Terminal 1 - Start RabbitMQ & Setup
cd rabbitinflux/producer/setup
docker compose up -d --build



## Stopping Services

```bash

# Stop publisher
cd producer/publisher
docker compose down

# Stop RabbitMQ
cd ../setup
docker compose down

# Remove volumes (clean slate)
docker compose down -v
````

---

## Troubleshooting

### **Messages not being consumed**

1. **Check consumer is registered:**

   ```bash
   # On Machine A (where RabbitMQ is running)
   docker exec -it rabbitmq rabbitmqctl list_consumers
   ```

2. **Check messages in queue:**

   ```bash
   docker exec -it rabbitmq rabbitmqctl list_queues name messages
   ```

3. **Check exchange bindings:**
   ```bash
   docker exec -it rabbitmq rabbitmqadmin list bindings
   ```

### **Consumer can't connect to RabbitMQ**

1. **Verify RabbitMQ is running:**

   ```bash
   docker ps | grep rabbitmq
   ```

2. **Test connection from consumer machine:**

   ```bash
   # Replace with Machine A's IP
   telnet 192.168.1.100 5672

   # Or use Python
   python3 -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('192.168.1.100', 5672)); print('Connected!'); s.close()"
   ```

3. **Check firewall:**
   ```bash
   # Windows - Allow port 5672
   netsh advfirewall firewall add rule name="RabbitMQ" dir=in action=allow protocol=TCP localport=5672
   ```

### **InfluxDB connection errors**

1. **Check InfluxDB is running:**

   ```bash
   docker ps | grep influxdb
   ```

2. **Verify InfluxDB health:**
   ```bash
   curl http://localhost:8086/health
   ```

---

## Port Reference

| Service             | Port  | Purpose                         |
| ------------------- | ----- | ------------------------------- |
| RabbitMQ AMQP       | 5672  | Message broker protocol         |
| RabbitMQ Management | 15672 | Web UI (http://localhost:15672) |
| InfluxDB            | 8086  | Time-series database            |

---

## Architecture Diagram

### Remote Setup:

```
┌─────────────────────┐         ┌─────────────────────┐
│  Machine A          │         │  Machine B          │
│                     │         │                     │
│  ┌──────────┐      │         │  ┌──────────┐      │
│  │ RabbitMQ │◄─────┼─────────┼──│Consumer  │      │
│  └────┬─────┘      │         │  └────┬─────┘      │
│       ▲             │         │       │             │
│  ┌────┴─────┐      │         │  ┌────▼─────┐      │
│  │Publisher │      │         │  │ InfluxDB │      │
│  └──────────┘      │         │  └──────────┘      │
└─────────────────────┘         └─────────────────────┘
          ▲                               │
          │      Internet/VPN/LAN         │
          └───────────────────────────────┘
```

---

## Summary of Changes Needed

| Scenario                        | Files to Change               | What to Change                                                          |
| ------------------------------- | ----------------------------- | ----------------------------------------------------------------------- |
| **Local (same machine)**        | None                          | Use defaults, everything works                                          |
| **Remote (different machines)** | `consumer/docker-compose.yml` | Change `RABBIT_MQ_HOST` to Machine A's IP address                       |
| **Using ngrok**                 | `consumer/docker-compose.yml` | Change `RABBIT_MQ_HOST` to ngrok URL and `RABBIT_MQ_PORT` to ngrok port |
| **Custom credentials**          | `producer/.env`               | Change `RABBIT_MQ_USER` and `RABBIT_MQ_PASSWORD`                        |

---

## Best Practices

1. **Security:** Change default credentials (`guest/guest`) in production
2. **Monitoring:** Use RabbitMQ Management UI to monitor queues and consumers
3. **Scaling:** Run multiple consumer instances for load distribution
4. **Persistence:** Messages are durable (survive RabbitMQ restarts)
5. **Error Handling:** Failed messages are logged but not requeued

---

## Need Help?

- RabbitMQ Management UI: `http://localhost:15672` (guest/guest)
- Check logs: `docker logs -f <container-name>`
- List running containers: `docker ps`
- Restart a service: `docker compose restart <service-name>`
