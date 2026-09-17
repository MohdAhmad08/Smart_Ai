# Manufacturing Dashboard - FastAPI Backend Documentation

This document provides complete specifications for implementing the FastAPI backend to power the Manufacturing Dashboard.

## Backend Setup

### 1. Installation

```bash
pip install fastapi uvicorn python-dotenv pydantic sqlalchemy
```

### 2. Project Structure

```
backend/
├── main.py                 # FastAPI application entry point
├── models.py              # Pydantic models for request/response
├── database.py            # Database configuration
├── routers/
│   ├── machine.py         # Machine data endpoints
│   ├── utilities.py       # Utilities endpoints
│   ├── analytics.py       # Analytics endpoints
│   └── alerts.py          # Alerts endpoints
└── requirements.txt
```

## API Configuration

### CORS Setup

The frontend expects the API to be available at `http://localhost:8000` by default. You can configure this via environment variable `REACT_APP_API_URL`.

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Manufacturing Dashboard API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## API Endpoints

### 1. Machine Data

**Endpoint:** `GET /api/machine-data`

**Description:** Returns current machine operational data

**Response Schema:**
```json
{
  "lot1": "LOT-2025-001",
  "lot2": "LOT-2025-002",
  "articleNumber": "ART-5847",
  "totalLength": "1,245 m",
  "lotTime": "3h 24m",
  "machineRunningTime": "7h 15m",
  "isRunning": true,
  "speed": 1450,
  "maxSpeed": 2000,
  "temperature": 185,
  "maxTemperature": 250
}
```

**FastAPI Implementation:**
```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class MachineData(BaseModel):
    lot1: str
    lot2: str
    articleNumber: str
    totalLength: str
    lotTime: str
    machineRunningTime: str
    isRunning: bool
    speed: int
    maxSpeed: int
    temperature: int
    maxTemperature: int

@router.get("/api/machine-data", response_model=MachineData)
async def get_machine_data():
    # Fetch from your database or real-time system
    return {
        "lot1": "LOT-2025-001",
        "lot2": "LOT-2025-002",
        "articleNumber": "ART-5847",
        "totalLength": "1,245 m",
        "lotTime": "3h 24m",
        "machineRunningTime": "7h 15m",
        "isRunning": True,
        "speed": 1450,
        "maxSpeed": 2000,
        "temperature": 185,
        "maxTemperature": 250
    }
```

### 2. Utilities Data

**Endpoint:** `GET /api/utilities`

**Description:** Returns current utilities consumption data

**Response Schema:**
```json
[
  {
    "name": "Steam",
    "totalUsage": 845.3,
    "perLotUsage": 422.7,
    "unit": "kg",
    "maxValue": 1200,
    "color": "bg-red-500",
    "iconName": "Flame"
  },
  {
    "name": "Water",
    "totalUsage": 1254.8,
    "perLotUsage": 627.4,
    "unit": "L",
    "maxValue": 2000,
    "color": "bg-blue-500",
    "iconName": "Droplets"
  }
]
```

**Valid iconName values:** `"Flame"`, `"Droplets"`, `"Wind"`, `"Zap"`, `"Beaker"`

**FastAPI Implementation:**
```python
from typing import List, Literal

class UtilityData(BaseModel):
    name: str
    totalUsage: float
    perLotUsage: float
    unit: str
    maxValue: int
    color: str
    iconName: Literal["Flame", "Droplets", "Wind", "Zap", "Beaker"]

@router.get("/api/utilities", response_model=List[UtilityData])
async def get_utilities():
    return [
        {
            "name": "Steam",
            "totalUsage": 845.3,
            "perLotUsage": 422.7,
            "unit": "kg",
            "maxValue": 1200,
            "color": "bg-red-500",
            "iconName": "Flame"
        },
        # ... other utilities
    ]
```

### 3. OEE Data

**Endpoint:** `GET /api/oee`

**Description:** Returns Overall Equipment Effectiveness metrics

**Response Schema:**
```json
{
  "availability": 92.3,
  "performance": 88.7,
  "quality": 95.2
}
```

**FastAPI Implementation:**
```python
class OEEData(BaseModel):
    availability: float
    performance: float
    quality: float

@router.get("/api/oee", response_model=OEEData)
async def get_oee():
    return {
        "availability": 92.3,
        "performance": 88.7,
        "quality": 95.2
    }
```

### 4. Database Records

**Endpoint:** `GET /api/database-records`

**Query Parameters:**
- `search` (optional): Filter by ID, LOT, or Machine ID
- `status` (optional): Filter by status ("running" or "stopped")

**Response Schema:**
```json
[
  {
    "id": "REC-0001",
    "timestamp": "2/21/2026, 10:30:00 AM",
    "machineId": "M-1",
    "lot": "LOT-2025-001",
    "speed": 1450,
    "temperature": 185,
    "steamUsage": 845,
    "waterUsage": 1254,
    "energyUsage": 567,
    "efficiency": 92,
    "status": "Running"
  }
]
```

**FastAPI Implementation:**
```python
from typing import Optional

class DataRecord(BaseModel):
    id: str
    timestamp: str
    machineId: str
    lot: str
    speed: int
    temperature: int
    steamUsage: int
    waterUsage: int
    energyUsage: int
    efficiency: int
    status: str

@router.get("/api/database-records", response_model=List[DataRecord])
async def get_database_records(
    search: Optional[str] = None,
    status: Optional[str] = None
):
    # Query your database with filters
    # Return filtered results
    pass
```

### 5. Machine Timeline

**Endpoint:** `GET /api/machine-timeline`

**Query Parameters:**
- `range`: Time range ("shift", "day", "week", "month")

**Response Schema:**
```json
[
  {
    "time": "0:00",
    "running": 60,
    "stopped": 0
  },
  {
    "time": "1:00",
    "running": 60,
    "stopped": 0
  }
]
```

**FastAPI Implementation:**
```python
class TimelineData(BaseModel):
    time: str
    running: int
    stopped: int

@router.get("/api/machine-timeline", response_model=List[TimelineData])
async def get_machine_timeline(range: Literal["shift", "day", "week", "month"]):
    # Generate timeline data based on range
    # For day: 24 hourly entries
    # For week: 7 daily entries
    # For month: 30 daily entries
    pass
```

### 6. Alerts

**Endpoint:** `GET /api/alerts`

**Description:** Returns system alerts and notifications

**Response Schema:**
```json
[
  {
    "id": "1",
    "timestamp": "2/21/2026, 9:30:00 AM",
    "type": "Speed Exceeded",
    "message": "Machine speed exceeded safe limit",
    "severity": "warning",
    "iconName": "Activity"
  }
]
```

**Valid severity values:** `"critical"`, `"warning"`, `"info"`  
**Valid iconName values:** `"Activity"`, `"ThermometerSun"`, `"AlertTriangle"`, `"Clock"`

**FastAPI Implementation:**
```python
class Alert(BaseModel):
    id: str
    timestamp: str
    type: str
    message: str
    severity: Literal["critical", "warning", "info"]
    iconName: Literal["Activity", "ThermometerSun", "AlertTriangle", "Clock"]

@router.get("/api/alerts", response_model=List[Alert])
async def get_alerts():
    return [
        {
            "id": "1",
            "timestamp": "2/21/2026, 9:30:00 AM",
            "type": "Speed Exceeded",
            "message": "Machine speed exceeded safe limit",
            "severity": "warning",
            "iconName": "Activity"
        }
    ]
```

### 7. Temperature Analytics

**Endpoint:** `GET /api/analytics/temperature`

**Description:** Returns temperature vs LOT length data

**Response Schema:**
```json
[
  {
    "lot": "LOT-1",
    "temperature": 185,
    "length": 1245
  }
]
```

**FastAPI Implementation:**
```python
class TemperatureAnalytics(BaseModel):
    lot: str
    temperature: int
    length: int

@router.get("/api/analytics/temperature", response_model=List[TemperatureAnalytics])
async def get_temperature_analytics():
    # Return last 10-20 lots with temperature and length data
    pass
```

### 8. Production Analytics

**Endpoint:** `GET /api/analytics/production`

**Description:** Returns production rate over time

**Response Schema:**
```json
[
  {
    "hour": "8:00",
    "rate": 325,
    "target": 330
  }
]
```

**FastAPI Implementation:**
```python
class ProductionAnalytics(BaseModel):
    hour: str
    rate: int
    target: int

@router.get("/api/analytics/production", response_model=List[ProductionAnalytics])
async def get_production_analytics():
    # Return hourly production data for current shift/day
    pass
```

### 9. Utilities Analytics

**Endpoint:** `GET /api/analytics/utilities`

**Description:** Returns utilities consumption and cost data

**Response Schema:**
```json
[
  {
    "utility": "Steam",
    "usage": 845,
    "cost": 1200
  }
]
```

**FastAPI Implementation:**
```python
class UtilitiesAnalytics(BaseModel):
    utility: str
    usage: int
    cost: int

@router.get("/api/analytics/utilities", response_model=List[UtilitiesAnalytics])
async def get_utilities_analytics():
    return [
        {"utility": "Steam", "usage": 845, "cost": 1200},
        {"utility": "Water", "usage": 1254, "cost": 800},
        {"utility": "Air", "usage": 3456, "cost": 600},
        {"utility": "Energy", "usage": 567, "cost": 2000},
        {"utility": "Chemical", "usage": 42, "cost": 1500}
    ]
```

## Complete main.py Example

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(
    title="Manufacturing Dashboard API",
    version="1.0.0",
    description="Backend API for Manufacturing Dashboard"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from routers import machine, utilities, analytics, alerts

app.include_router(machine.router)
app.include_router(utilities.router)
app.include_router(analytics.router)
app.include_router(alerts.router)

@app.get("/")
async def root():
    return {"message": "Manufacturing Dashboard API", "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Running the Backend

```bash
# Development
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Environment Variables

Create a `.env` file in your backend directory:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Database
DATABASE_URL=postgresql://user:password@localhost/manufacturing_db

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

## Frontend Configuration

To connect the frontend to your backend, set the environment variable:

```bash
# In your frontend .env file
REACT_APP_API_URL=http://localhost:8000
```

If not set, it defaults to `http://localhost:8000`.

## Data Refresh Rates

The frontend automatically refreshes data at these intervals:
- **Machine Data, Utilities, OEE**: Every 3 seconds
- **Alerts**: Every 30 seconds
- **Analytics**: Every 60 seconds
- **Database Records**: On filter change
- **Machine Timeline**: On time range change

## Testing

You can test the API endpoints using:

```bash
# Using curl
curl http://localhost:8000/api/machine-data

# Using httpie
http GET http://localhost:8000/api/machine-data

# View API documentation
# Navigate to: http://localhost:8000/docs
```

## Error Handling

The frontend handles API errors gracefully and displays toast notifications to users. Ensure your API returns proper HTTP status codes:

- `200 OK` - Successful request
- `400 Bad Request` - Invalid parameters
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

## Notes

1. All timestamps should be in local time format matching the frontend's locale
2. Numeric values should be returned as numbers, not strings (except for formatted display values like "1,245 m")
3. The frontend expects real-time or near real-time data, so implement appropriate caching strategies
4. Consider implementing WebSocket connections for truly real-time updates in future versions

## Support

For issues or questions about the API integration, refer to:
- FastAPI documentation: https://fastapi.tiangolo.com/
- Frontend API service: `/services/api.ts`
