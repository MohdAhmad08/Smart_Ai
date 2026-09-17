# API Quick Reference Card

## Base URL
```
http://localhost:8000
```

## Endpoints Overview

### 🏭 Machine & Production

| Endpoint | Method | Description | Update Frequency |
|----------|--------|-------------|------------------|
| `/api/machine-data` | GET | Current machine status & metrics | 3 seconds |
| `/api/utilities` | GET | Utilities consumption data | 3 seconds |
| `/api/oee` | GET | OEE performance metrics | 3 seconds |

### 📊 Analytics

| Endpoint | Method | Description | Update Frequency |
|----------|--------|-------------|------------------|
| `/api/analytics/temperature` | GET | Temperature vs LOT length | 60 seconds |
| `/api/analytics/production` | GET | Production rate over time | 60 seconds |
| `/api/analytics/utilities` | GET | Utilities consumption & cost | 60 seconds |

### 📈 Timeline & History

| Endpoint | Method | Description | Update Frequency |
|----------|--------|-------------|------------------|
| `/api/machine-timeline?range=day` | GET | Machine activity timeline | On range change |
| `/api/database-records` | GET | Historical data records | On filter change |

### 🚨 Alerts

| Endpoint | Method | Description | Update Frequency |
|----------|--------|-------------|------------------|
| `/api/alerts` | GET | System alerts & notifications | 30 seconds |

---

## Request Examples

### Machine Data
```bash
curl http://localhost:8000/api/machine-data
```

### Utilities
```bash
curl http://localhost:8000/api/utilities
```

### OEE Metrics
```bash
curl http://localhost:8000/api/oee
```

### Database Records (with filters)
```bash
# All records
curl http://localhost:8000/api/database-records

# Search by term
curl http://localhost:8000/api/database-records?search=LOT-001

# Filter by status
curl http://localhost:8000/api/database-records?status=running

# Combined filters
curl http://localhost:8000/api/database-records?search=M-1&status=running
```

### Machine Timeline
```bash
# Day view
curl http://localhost:8000/api/machine-timeline?range=day

# Week view
curl http://localhost:8000/api/machine-timeline?range=week

# Month view
curl http://localhost:8000/api/machine-timeline?range=month

# Shift view
curl http://localhost:8000/api/machine-timeline?range=shift
```

### Alerts
```bash
curl http://localhost:8000/api/alerts
```

### Analytics
```bash
# Temperature analytics
curl http://localhost:8000/api/analytics/temperature

# Production analytics
curl http://localhost:8000/api/analytics/production

# Utilities analytics
curl http://localhost:8000/api/analytics/utilities
```

---

## Response Schemas

### Machine Data
```json
{
  "lot1": "string",
  "lot2": "string",
  "articleNumber": "string",
  "totalLength": "string",
  "lotTime": "string",
  "machineRunningTime": "string",
  "isRunning": boolean,
  "speed": number,
  "maxSpeed": number,
  "temperature": number,
  "maxTemperature": number
}
```

### Utility Data
```json
[{
  "name": "string",
  "totalUsage": number,
  "perLotUsage": number,
  "unit": "string",
  "maxValue": number,
  "color": "string",
  "iconName": "Flame" | "Droplets" | "Wind" | "Zap" | "Beaker"
}]
```

### OEE Data
```json
{
  "availability": number,
  "performance": number,
  "quality": number
}
```

### Alert
```json
{
  "id": "string",
  "timestamp": "string",
  "type": "string",
  "message": "string",
  "severity": "critical" | "warning" | "info",
  "iconName": "Activity" | "ThermometerSun" | "AlertTriangle" | "Clock"
}
```

---

## Testing Tools

### Browser
Visit the interactive API documentation:
```
http://localhost:8000/docs
```

### cURL
```bash
# Basic GET request
curl http://localhost:8000/api/machine-data

# Pretty print JSON
curl -s http://localhost:8000/api/machine-data | python -m json.tool

# Include headers
curl -i http://localhost:8000/api/machine-data
```

### HTTPie (if installed)
```bash
# Install: pip install httpie
http GET http://localhost:8000/api/machine-data
```

### Postman
1. Import collection from http://localhost:8000/openapi.json
2. Set base URL to `http://localhost:8000`
3. Test all endpoints

### JavaScript (Browser Console)
```javascript
// Fetch machine data
fetch('http://localhost:8000/api/machine-data')
  .then(r => r.json())
  .then(data => console.log(data));

// Fetch with error handling
async function testAPI() {
  try {
    const response = await fetch('http://localhost:8000/api/machine-data');
    const data = await response.json();
    console.log('Machine Data:', data);
  } catch (error) {
    console.error('Error:', error);
  }
}
testAPI();
```

---

## Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid parameters |
| 404 | Not Found | Endpoint not found |
| 422 | Validation Error | Invalid data format |
| 500 | Server Error | Backend error |

---

## Common Query Parameters

### Database Records
- `search` (string, optional) - Search term for filtering
- `status` (string, optional) - Filter by status ("running" or "stopped")

### Machine Timeline
- `range` (enum, required) - Time range: "shift" | "day" | "week" | "month"

---

## Frontend API Service

The frontend uses a centralized API service at `/services/api.ts`:

```typescript
import { getMachineData, getUtilities, getOEEData } from '../services/api';

// Fetch data
const data = await getMachineData();
const utilities = await getUtilities();
const oee = await getOEEData();
```

---

## Configuration

### Change API URL

**Method 1: Environment Variable**
```bash
# In .env file
REACT_APP_API_URL=http://your-backend-url:8000
```

**Method 2: Direct Edit**
Edit `/services/api.ts`:
```typescript
const API_BASE_URL = 'http://your-backend-url:8000';
```

---

## Troubleshooting

### Backend not responding
```bash
# Check if backend is running
curl http://localhost:8000/

# Expected response:
{
  "message": "Manufacturing Dashboard API",
  "version": "1.0.0"
}
```

### CORS issues
Check browser console for errors and verify CORS middleware in backend.

### Wrong data format
Compare API response with schema in documentation.

---

## Performance Notes

- **Caching**: Consider implementing Redis for frequently accessed data
- **Rate Limiting**: Add rate limiting for production environments
- **Compression**: Enable gzip compression for large responses
- **Pagination**: Implement pagination for database records endpoint

---

## Security Checklist

For production deployments:

- [ ] Enable HTTPS
- [ ] Implement authentication
- [ ] Add rate limiting
- [ ] Validate all inputs
- [ ] Use environment variables for secrets
- [ ] Configure CORS properly
- [ ] Add request logging
- [ ] Implement API versioning
- [ ] Add health check endpoint
- [ ] Monitor API usage

---

**Need more details?** See the full [API Documentation](./BACKEND_API_DOCUMENTATION.md)
