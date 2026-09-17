"""
Manufacturing Dashboard - FastAPI Backend Example
This is a complete working example of the backend API
Save this file and run it with: uvicorn fastapi_backend_example:app --reload
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal, Optional
from datetime import datetime, timedelta
import random

# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Manufacturing Dashboard API",
    version="1.0.0",
    description="Backend API for Manufacturing Dashboard"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Pydantic Models
# ============================================================================

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

class UtilityData(BaseModel):
    name: str
    totalUsage: float
    perLotUsage: float
    unit: str
    maxValue: int
    color: str
    iconName: Literal["Flame", "Droplets", "Wind", "Zap", "Beaker"]

class OEEData(BaseModel):
    availability: float
    performance: float
    quality: float

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

class TimelineData(BaseModel):
    time: str
    running: int
    stopped: int

class Alert(BaseModel):
    id: str
    timestamp: str
    type: str
    message: str
    severity: Literal["critical", "warning", "info"]
    iconName: Literal["Activity", "ThermometerSun", "AlertTriangle", "Clock"]

class TemperatureAnalytics(BaseModel):
    lot: str
    temperature: int
    length: int

class ProductionAnalytics(BaseModel):
    hour: str
    rate: int
    target: int

class UtilitiesAnalytics(BaseModel):
    utility: str
    usage: int
    cost: int

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Manufacturing Dashboard API",
        "version": "1.0.0",
        "endpoints": {
            "machine_data": "/api/machine-data",
            "utilities": "/api/utilities",
            "oee": "/api/oee",
            "database_records": "/api/database-records",
            "machine_timeline": "/api/machine-timeline",
            "alerts": "/api/alerts",
            "analytics": {
                "temperature": "/api/analytics/temperature",
                "production": "/api/analytics/production",
                "utilities": "/api/analytics/utilities"
            }
        }
    }

@app.get("/api/machine-data", response_model=MachineData)
async def get_machine_data():
    """Get current machine operational data"""
    # In production, fetch from your database or real-time system
    return {
        "lot1": "LOT-2025-001",
        "lot2": "LOT-2025-002",
        "articleNumber": "ART-5847",
        "totalLength": f"{random.randint(1200, 1300):,} m",
        "lotTime": "3h 24m",
        "machineRunningTime": "7h 15m",
        "isRunning": random.random() > 0.1,  # 90% running
        "speed": random.randint(1400, 1600),
        "maxSpeed": 2000,
        "temperature": random.randint(175, 195),
        "maxTemperature": 250
    }

@app.get("/api/utilities", response_model=List[UtilityData])
async def get_utilities():
    """Get current utilities consumption data"""
    base_utilities = [
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
        },
        {
            "name": "Air",
            "totalUsage": 3456.2,
            "perLotUsage": 1728.1,
            "unit": "m³",
            "maxValue": 5000,
            "color": "bg-cyan-500",
            "iconName": "Wind"
        },
        {
            "name": "Energy",
            "totalUsage": 567.9,
            "perLotUsage": 283.9,
            "unit": "kWh",
            "maxValue": 800,
            "color": "bg-yellow-500",
            "iconName": "Zap"
        },
        {
            "name": "Chemical",
            "totalUsage": 42.5,
            "perLotUsage": 21.3,
            "unit": "L",
            "maxValue": 100,
            "color": "bg-purple-500",
            "iconName": "Beaker"
        }
    ]
    
    # Add some variance to simulate real-time updates
    for utility in base_utilities:
        utility["totalUsage"] += random.uniform(0, 2)
        utility["perLotUsage"] += random.uniform(0, 1)
    
    return base_utilities

@app.get("/api/oee", response_model=OEEData)
async def get_oee():
    """Get Overall Equipment Effectiveness metrics"""
    return {
        "availability": round(random.uniform(88, 95), 1),
        "performance": round(random.uniform(85, 92), 1),
        "quality": round(random.uniform(93, 98), 1)
    }

@app.get("/api/database-records", response_model=List[DataRecord])
async def get_database_records(
    search: Optional[str] = Query(None, description="Search term for filtering"),
    status: Optional[str] = Query(None, description="Filter by status")
):
    """Get database records with optional filtering"""
    records = []
    
    # Generate sample records
    for i in range(50):
        timestamp = datetime.now() - timedelta(hours=i)
        record_status = "Running" if random.random() > 0.2 else "Stopped"
        
        record = {
            "id": f"REC-{str(i + 1).zfill(4)}",
            "timestamp": timestamp.strftime("%m/%d/%Y, %I:%M:%S %p"),
            "machineId": f"M-{(i // 10) + 1}",
            "lot": f"LOT-2025-{str((i % 20) + 1).zfill(3)}",
            "speed": random.randint(1400, 1600),
            "temperature": random.randint(170, 200),
            "steamUsage": random.randint(800, 900),
            "waterUsage": random.randint(1200, 1400),
            "energyUsage": random.randint(500, 600),
            "efficiency": random.randint(75, 95),
            "status": record_status
        }
        
        # Apply filters
        if status and status.lower() != "all":
            if record["status"].lower() != status.lower():
                continue
        
        if search:
            search_lower = search.lower()
            if not (search_lower in record["id"].lower() or 
                   search_lower in record["lot"].lower() or 
                   search_lower in record["machineId"].lower()):
                continue
        
        records.append(record)
    
    return records

@app.get("/api/machine-timeline", response_model=List[TimelineData])
async def get_machine_timeline(
    range: Literal["shift", "day", "week", "month"] = Query("day", description="Time range")
):
    """Get machine status timeline data"""
    data = []
    
    if range == "shift":
        # 8 hours
        for i in range(8):
            running = random.randint(55, 60) if random.random() > 0.2 else 0
            data.append({
                "time": f"{i}:00",
                "running": running,
                "stopped": 60 - running
            })
    elif range == "day":
        # 24 hours
        for i in range(24):
            running = random.randint(55, 60) if random.random() > 0.15 else 0
            data.append({
                "time": f"{i}:00",
                "running": running,
                "stopped": 60 - running
            })
    elif range == "week":
        # 7 days
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for day in days:
            running = random.randint(16, 24)
            data.append({
                "time": day,
                "running": running,
                "stopped": 24 - running
            })
    else:  # month
        # 30 days
        for i in range(1, 31):
            running = random.randint(16, 24)
            data.append({
                "time": f"Day {i}",
                "running": running,
                "stopped": 24 - running
            })
    
    return data

@app.get("/api/alerts", response_model=List[Alert])
async def get_alerts():
    """Get system alerts and notifications"""
    alerts = [
        {
            "id": "1",
            "timestamp": (datetime.now() - timedelta(hours=1)).strftime("%m/%d/%Y, %I:%M:%S %p"),
            "type": "Speed Exceeded",
            "message": "Machine speed exceeded safe limit",
            "severity": "warning",
            "iconName": "Activity"
        },
        {
            "id": "2",
            "timestamp": (datetime.now() - timedelta(hours=2)).strftime("%m/%d/%Y, %I:%M:%S %p"),
            "type": "Temperature High",
            "message": "SV temperature reached 95% of maximum",
            "severity": "critical",
            "iconName": "ThermometerSun"
        },
        {
            "id": "3",
            "timestamp": (datetime.now() - timedelta(hours=3)).strftime("%m/%d/%Y, %I:%M:%S %p"),
            "type": "Downtime",
            "message": "Machine stopped unexpectedly",
            "severity": "critical",
            "iconName": "AlertTriangle"
        },
        {
            "id": "4",
            "timestamp": (datetime.now() - timedelta(hours=4)).strftime("%m/%d/%Y, %I:%M:%S %p"),
            "type": "Maintenance Due",
            "message": "Scheduled maintenance approaching",
            "severity": "info",
            "iconName": "Clock"
        },
        {
            "id": "5",
            "timestamp": (datetime.now() - timedelta(hours=5)).strftime("%m/%d/%Y, %I:%M:%S %p"),
            "type": "Low Efficiency",
            "message": "Production efficiency below target",
            "severity": "warning",
            "iconName": "Activity"
        }
    ]
    
    return alerts

@app.get("/api/analytics/temperature", response_model=List[TemperatureAnalytics])
async def get_temperature_analytics():
    """Get temperature vs LOT length analytics"""
    data = []
    for i in range(1, 11):
        data.append({
            "lot": f"LOT-{i}",
            "temperature": random.randint(170, 200),
            "length": random.randint(1000, 1500)
        })
    return data

@app.get("/api/analytics/production", response_model=List[ProductionAnalytics])
async def get_production_analytics():
    """Get production rate analytics"""
    data = []
    for i in range(8, 20):  # 8 AM to 8 PM
        data.append({
            "hour": f"{i}:00",
            "rate": random.randint(300, 350),
            "target": 330
        })
    return data

@app.get("/api/analytics/utilities", response_model=List[UtilitiesAnalytics])
async def get_utilities_analytics():
    """Get utilities consumption and cost analytics"""
    return [
        {"utility": "Steam", "usage": 845, "cost": 1200},
        {"utility": "Water", "usage": 1254, "cost": 800},
        {"utility": "Air", "usage": 3456, "cost": 600},
        {"utility": "Energy", "usage": 567, "cost": 2000},
        {"utility": "Chemical", "usage": 42, "cost": 1500}
    ]

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
