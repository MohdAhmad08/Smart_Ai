# API Integration Guide

## Overview

The Manufacturing Dashboard has been updated to fetch real-time data from a FastAPI backend instead of using dummy data. All components now make API calls to retrieve live data from your backend server.

## What Has Changed

### Frontend Changes

All components now use the centralized API service (`/services/api.ts`) to fetch data:

1. **ProductionFloorView** - Fetches machine data, utilities, and OEE metrics every 3 seconds
2. **DatabaseView** - Fetches database records with search and filter support
3. **MachineTimelineChart** - Fetches timeline data based on selected time range
4. **AlertsTable** - Fetches system alerts every 30 seconds
5. **AdvancedAnalytics** - Fetches temperature, production, and utilities analytics every 60 seconds

### Loading States

All views now include:
- Loading spinners while fetching data
- Error handling with toast notifications
- Graceful fallback when backend is unavailable

### API Configuration

The API base URL can be configured via environment variable:
- Default: `http://localhost:8000`
- Custom: Set `REACT_APP_API_URL` environment variable

## Quick Start

### Option 1: Use the Example Backend (Recommended for Testing)

We've included a complete working FastAPI backend example that you can run immediately.

1. **Install FastAPI and dependencies:**
   ```bash
   pip install fastapi uvicorn pydantic
   ```

2. **Run the example backend:**
   ```bash
   # The backend example file is included in your project root
   uvicorn fastapi_backend_example:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Start your frontend:**
   ```bash
   npm start
   ```

4. **Access the dashboard:**
   - Frontend: http://localhost:3000
   - API Docs: http://localhost:8000/docs

The example backend generates realistic dummy data with random variations to simulate a real manufacturing environment.

### Option 2: Connect to Your Real Backend

If you have an existing backend or want to implement your own:

1. **Review the API documentation:**
   See `BACKEND_API_DOCUMENTATION.md` for complete endpoint specifications

2. **Implement the required endpoints:**
   - GET /api/machine-data
   - GET /api/utilities
   - GET /api/oee
   - GET /api/database-records
   - GET /api/machine-timeline
   - GET /api/alerts
   - GET /api/analytics/temperature
   - GET /api/analytics/production
   - GET /api/analytics/utilities

3. **Configure CORS:**
   Make sure your backend allows requests from your frontend origin

4. **Set the API URL:**
   ```bash
   # In your frontend project, create/edit .env file
   REACT_APP_API_URL=http://your-backend-url:port
   ```

## API Endpoints Summary

| Endpoint | Method | Description | Refresh Rate |
|----------|--------|-------------|--------------|
| `/api/machine-data` | GET | Current machine operational data | 3 seconds |
| `/api/utilities` | GET | Current utilities consumption | 3 seconds |
| `/api/oee` | GET | OEE metrics | 3 seconds |
| `/api/database-records` | GET | Historical records | On filter change |
| `/api/machine-timeline` | GET | Machine status timeline | On range change |
| `/api/alerts` | GET | System alerts | 30 seconds |
| `/api/analytics/temperature` | GET | Temperature analytics | 60 seconds |
| `/api/analytics/production` | GET | Production rate analytics | 60 seconds |
| `/api/analytics/utilities` | GET | Utilities cost analytics | 60 seconds |

## Testing the Integration

### 1. Test with Example Backend

```bash
# Terminal 1: Start the backend
uvicorn fastapi_backend_example:app --reload

# Terminal 2: Start the frontend
npm start

# Open browser to http://localhost:3000
```

### 2. Test API Endpoints Directly

```bash
# Test machine data endpoint
curl http://localhost:8000/api/machine-data

# View interactive API documentation
# Open: http://localhost:8000/docs
```

### 3. Monitor Network Requests

Open browser DevTools (F12) → Network tab to see API requests in real-time.

## Troubleshooting

### Frontend shows "Loading dashboard data..." forever

**Cause:** Backend is not running or not accessible

**Solution:**
1. Check if backend is running: `curl http://localhost:8000/`
2. Check CORS settings in your backend
3. Verify `REACT_APP_API_URL` is correct

### "Failed to fetch data from server" error

**Cause:** Backend returned an error or wrong data format

**Solution:**
1. Check backend logs for errors
2. Verify API responses match the expected schema (see documentation)
3. Test endpoints directly using browser or curl

### CORS errors in browser console

**Cause:** Backend not configured to accept requests from frontend

**Solution:**
```python
# In your FastAPI app
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Data not updating in real-time

**Cause:** Backend not returning different data on subsequent requests

**Solution:**
- Ensure your backend is reading from a live data source
- The example backend includes random variations to simulate updates
- Check that your database/data source is being updated

## Files Modified

- `/services/api.ts` - New API service layer
- `/components/ProductionFloorView.tsx` - Updated to use API
- `/components/DatabaseView.tsx` - Updated to use API
- `/components/MachineTimelineChart.tsx` - Updated to use API
- `/components/AlertsTable.tsx` - Updated to use API
- `/components/AdvancedAnalytics.tsx` - Updated to use API

## Files Added

- `/services/api.ts` - API service with TypeScript interfaces
- `/BACKEND_API_DOCUMENTATION.md` - Complete API specification
- `/fastapi_backend_example.py` - Working backend example
- `/API_INTEGRATION_README.md` - This file

## Next Steps

1. **For Development:**
   - Use the included example backend
   - Modify it to read from your actual data sources
   - Add authentication if needed

2. **For Production:**
   - Implement proper database connections
   - Add authentication and authorization
   - Set up proper error logging
   - Configure production CORS settings
   - Use environment variables for configuration
   - Deploy backend to production server
   - Update `REACT_APP_API_URL` to production URL

3. **Optional Enhancements:**
   - Implement WebSocket connections for true real-time updates
   - Add request caching to reduce server load
   - Implement retry logic for failed requests
   - Add request debouncing for search/filter inputs

## Support

For detailed API specifications, see: `BACKEND_API_DOCUMENTATION.md`

For backend code example, see: `fastapi_backend_example.py`

For frontend API service code, see: `/services/api.ts`
