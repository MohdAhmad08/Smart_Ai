# Getting Started - Manufacturing Dashboard with FastAPI Backend

## 🎯 Goal
Connect your Manufacturing Dashboard to a FastAPI backend to receive real-time data instead of using dummy data.

## ⚡ Quick Start (5 Minutes)

### Step 1: Install Python Dependencies
```bash
pip install fastapi uvicorn pydantic
```

### Step 2: Start the Backend
```bash
python3 fastapi_backend_example.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### Step 3: Start the Frontend (New Terminal)
```bash
npm start
```

### Step 4: Open Your Browser
Visit http://localhost:3000

**That's it!** Your dashboard is now connected to the FastAPI backend.

## ✅ Verify Everything Works

### 1. Check Backend is Running
Open http://localhost:8000 in your browser

You should see:
```json
{
  "message": "Manufacturing Dashboard API",
  "version": "1.0.0"
}
```

### 2. Check API Documentation
Open http://localhost:8000/docs

You'll see an interactive API documentation page where you can test all endpoints.

### 3. Check Dashboard Data
1. Open http://localhost:3000
2. You should see:
   - ✅ Loading spinner briefly
   - ✅ Machine data appearing
   - ✅ Utilities cards showing data
   - ✅ OEE chart rendering
3. Watch the data update every 3 seconds

### 4. Test All Views

**Main Dashboard:**
- Machine data in column 1
- Utilities in column 2
- OEE chart in column 3

**Analytics:**
- Machine timeline chart
- System alerts
- Advanced analytics graphs

**Database:**
- Table with 50+ records
- Search functionality
- Export buttons

## 🔍 Troubleshooting

### Problem: Backend won't start

**Solution 1:** Check if port 8000 is in use
```bash
# Linux/Mac
lsof -i :8000

# Windows
netstat -ano | findstr :8000
```

**Solution 2:** Install dependencies
```bash
pip install --upgrade fastapi uvicorn pydantic
```

### Problem: Frontend shows "Loading..." forever

**Cause:** Backend not running or not accessible

**Solution:**
1. Check backend is running: `curl http://localhost:8000/`
2. Check browser console (F12) for errors
3. Verify `REACT_APP_API_URL` in `.env` (should be `http://localhost:8000`)

### Problem: CORS errors in browser

**Solution:**
The example backend has CORS configured for `http://localhost:3000`. If your frontend runs on a different port, update `fastapi_backend_example.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:YOUR_PORT"],  # Change this
    ...
)
```

### Problem: "Module not found" errors

**Frontend:**
```bash
rm -rf node_modules package-lock.json
npm install
```

**Backend:**
```bash
pip install --force-reinstall fastapi uvicorn pydantic
```

## 📱 Using the Startup Scripts

### Linux/Mac
```bash
# Make executable (first time only)
chmod +x start-dev.sh

# Run
./start-dev.sh
```

This will:
- Install Python dependencies
- Start backend on port 8000
- Start frontend on port 3000
- Show status of both services

Press `Ctrl+C` to stop both services.

### Windows
```bash
start-dev.bat
```

This will:
- Check dependencies
- Open two command windows (backend and frontend)
- Start both services

Close both windows to stop services.

## 🔧 Configuration

### Change Backend Port

Edit `fastapi_backend_example.py`:
```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)  # Change port
```

Then update frontend `.env`:
```env
REACT_APP_API_URL=http://localhost:8080
```

### Change Refresh Rates

Edit the component files:

**Machine Data (3 seconds):**
`/components/ProductionFloorView.tsx` - line ~50

**Alerts (30 seconds):**
`/components/AlertsTable.tsx` - line ~35

**Analytics (60 seconds):**
`/components/AdvancedAnalytics.tsx` - line ~55

## 📚 Next Steps

### Understand the Code

1. **API Service:** `/services/api.ts`
   - All API calls are here
   - TypeScript interfaces for data types
   - Error handling

2. **Backend:** `fastapi_backend_example.py`
   - All 9 API endpoints
   - Dummy data generation
   - CORS configuration

3. **Components:** `/components/`
   - Each view fetches its own data
   - Loading and error states
   - Auto-refresh logic

### Connect to Real Data

Edit `fastapi_backend_example.py` to connect to your data source:

```python
@app.get("/api/machine-data", response_model=MachineData)
async def get_machine_data():
    # Instead of dummy data:
    # 1. Query your database
    # 2. Read from PLC/SCADA
    # 3. Call external API
    # 4. Read from sensors
    
    # Example with database:
    from your_database import get_current_machine_status
    data = get_current_machine_status()
    return data
```

### Add Authentication

```bash
pip install python-jose passlib
```

```python
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.get("/api/machine-data", dependencies=[Depends(security)])
async def get_machine_data():
    # Now requires authentication
    ...
```

### Deploy to Production

1. **Build Frontend:**
   ```bash
   npm run build
   ```

2. **Run Backend with Gunicorn:**
   ```bash
   pip install gunicorn
   gunicorn fastapi_backend_example:app \
     --workers 4 \
     --worker-class uvicorn.workers.UvicornWorker
   ```

3. **Use Environment Variables:**
   ```bash
   export REACT_APP_API_URL=https://api.yourdomain.com
   ```

## 📖 Documentation Guide

| Document | When to Use |
|----------|-------------|
| **GETTING_STARTED.md** (this file) | Starting out, first setup |
| **README.md** | Project overview, features |
| **SETUP_GUIDE.md** | Detailed installation steps |
| **API_INTEGRATION_README.md** | Understanding the integration |
| **BACKEND_API_DOCUMENTATION.md** | API specifications, schemas |
| **API_QUICK_REFERENCE.md** | Quick endpoint lookup |
| **INTEGRATION_SUMMARY.md** | What changed, overview |

## 🎓 Learning Path

1. ✅ **Get it running** (You're here!)
2. 📖 Read `INTEGRATION_SUMMARY.md` to understand what changed
3. 🔧 Review `API_QUICK_REFERENCE.md` for endpoint details
4. 💻 Explore the code in `/services/api.ts` and components
5. 🗄️ Connect to your real data source
6. 🚀 Deploy to production

## 💡 Tips

### Development
- Keep backend terminal open to see request logs
- Use browser DevTools (F12) Network tab to see API calls
- Check `/docs` endpoint for interactive API testing

### Testing
```bash
# Test individual endpoints
curl http://localhost:8000/api/machine-data
curl http://localhost:8000/api/utilities
curl http://localhost:8000/api/oee

# Pretty print JSON
curl -s http://localhost:8000/api/machine-data | python -m json.tool
```

### Debugging
- Backend logs show all incoming requests
- Frontend console shows any errors
- Check Network tab for failed API calls
- Verify data format matches TypeScript interfaces

## 🎯 Success Checklist

- [ ] Backend starts without errors
- [ ] Can access http://localhost:8000
- [ ] Can access http://localhost:8000/docs
- [ ] Frontend starts without errors
- [ ] Can access http://localhost:3000
- [ ] Dashboard loads all three views
- [ ] Data updates every 3 seconds in Main Dashboard
- [ ] No errors in browser console
- [ ] Can see API requests in Network tab
- [ ] All charts render correctly
- [ ] Search and filters work in Database view
- [ ] Timeline changes when selecting different ranges

## 🆘 Need Help?

1. **Check common issues above**
2. **Review error messages** in browser console and backend logs
3. **Test API directly** using curl or http://localhost:8000/docs
4. **Verify configuration** in .env file
5. **Check documentation** for detailed explanations

## 🎉 You're Ready!

You now have a fully functional manufacturing dashboard connected to a FastAPI backend!

**Start the application:**
```bash
# Easy way
./start-dev.sh  # Linux/Mac
start-dev.bat   # Windows

# Manual way
python3 fastapi_backend_example.py  # Terminal 1
npm start                            # Terminal 2
```

**Access:**
- Dashboard: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

**Enjoy your real-time manufacturing dashboard! 🚀**
