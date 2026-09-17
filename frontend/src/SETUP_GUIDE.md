# Manufacturing Dashboard - Complete Setup Guide

## 📋 Table of Contents
1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Running the Application](#running-the-application)
5. [Configuration](#configuration)
6. [Project Structure](#project-structure)
7. [Troubleshooting](#troubleshooting)

## 🚀 Quick Start

### Automated Setup (Recommended)

**For Linux/Mac:**
```bash
chmod +x start-dev.sh
./start-dev.sh
```

**For Windows:**
```bash
start-dev.bat
```

This will:
- Install required Python dependencies
- Start the FastAPI backend on port 8000
- Start the React frontend on port 3000
- Open your browser automatically

### Manual Setup

1. **Install Python dependencies:**
   ```bash
   pip install -r backend-requirements.txt
   ```

2. **Start the backend:**
   ```bash
   python3 fastapi_backend_example.py
   # Or: uvicorn fastapi_backend_example:app --reload
   ```

3. **In a new terminal, start the frontend:**
   ```bash
   npm start
   ```

4. **Access the application:**
   - Frontend Dashboard: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## 📦 Prerequisites

### Required Software

1. **Node.js** (v16.0.0 or higher)
   - Download: https://nodejs.org/
   - Verify: `node --version`

2. **Python** (3.7 or higher)
   - Download: https://www.python.org/
   - Verify: `python3 --version`

3. **npm** (comes with Node.js)
   - Verify: `npm --version`

4. **pip** (comes with Python)
   - Verify: `pip3 --version`

### Optional Software

- **Git** - For version control
- **VS Code** - Recommended code editor
- **Postman** - For API testing

## 💿 Installation

### Step 1: Install Frontend Dependencies

```bash
# Install Node.js packages
npm install
```

### Step 2: Install Backend Dependencies

```bash
# Install Python packages
pip install fastapi uvicorn pydantic

# Or install all optional dependencies
pip install -r backend-requirements.txt
```

### Step 3: Verify Installation

```bash
# Test Python imports
python3 -c "import fastapi, uvicorn; print('Backend dependencies OK')"

# Test Node packages
npm list react react-dom
```

## 🏃 Running the Application

### Development Mode

#### Option 1: Use Startup Scripts (Easiest)

**Linux/Mac:**
```bash
chmod +x start-dev.sh
./start-dev.sh
```

**Windows:**
```bash
start-dev.bat
```

#### Option 2: Manual Start

**Terminal 1 - Backend:**
```bash
# Method 1: Direct Python
python3 fastapi_backend_example.py

# Method 2: Using Uvicorn
uvicorn fastapi_backend_example:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
npm start
```

### Production Mode

**Backend:**
```bash
# Install gunicorn for production
pip install gunicorn

# Run with multiple workers
gunicorn fastapi_backend_example:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

**Frontend:**
```bash
# Build optimized production bundle
npm run build

# Serve with a static server
npx serve -s build -p 3000
```

## ⚙️ Configuration

### Environment Variables

#### Frontend Configuration

Create a `.env` file in the project root:

```env
# API Configuration
REACT_APP_API_URL=http://localhost:8000

# Other configurations
REACT_APP_ENV=development
```

#### Backend Configuration

Create a `.env` file for the backend:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Database (if using)
DATABASE_URL=postgresql://user:password@localhost/manufacturing_db

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173

# Security (for production)
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### CORS Configuration

In `fastapi_backend_example.py`, update CORS settings:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        # Add your production domain here
        # "https://your-domain.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 📁 Project Structure

```
manufacturing-dashboard/
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/          # React components
│   │   │   ├── ProductionFloorView.tsx
│   │   │   ├── DatabaseView.tsx
│   │   │   ├── AlertsTable.tsx
│   │   │   └── ...
│   │   ├── services/            # API service layer
│   │   │   └── api.ts
│   │   ├── App.tsx              # Main app component
│   │   └── styles/
│   ├── package.json
│   └── .env
│
├── backend/
│   ├── fastapi_backend_example.py    # Example backend
│   ├── backend-requirements.txt      # Python dependencies
│   └── .env
│
├── documentation/
│   ├── API_INTEGRATION_README.md
│   ├── BACKEND_API_DOCUMENTATION.md
│   └── SETUP_GUIDE.md
│
├── start-dev.sh                 # Linux/Mac startup script
└── start-dev.bat                # Windows startup script
```

## 🔧 Troubleshooting

### Common Issues and Solutions

#### Issue: "Module not found" errors

**Frontend:**
```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

**Backend:**
```bash
# Reinstall Python packages
pip uninstall fastapi uvicorn
pip install fastapi uvicorn pydantic
```

#### Issue: Port already in use

**For port 8000 (Backend):**
```bash
# Linux/Mac
lsof -ti:8000 | xargs kill -9

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**For port 3000 (Frontend):**
```bash
# Linux/Mac
lsof -ti:3000 | xargs kill -9

# Windows
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

#### Issue: CORS errors

**Solution:**
1. Verify backend is running: `curl http://localhost:8000/`
2. Check CORS middleware is configured correctly
3. Ensure frontend URL is in `allow_origins` list
4. Clear browser cache and try again

#### Issue: API requests failing

**Check backend is accessible:**
```bash
curl http://localhost:8000/api/machine-data
```

**Check API documentation:**
Visit http://localhost:8000/docs

**Verify API URL in frontend:**
```bash
echo $REACT_APP_API_URL
# Should show: http://localhost:8000
```

#### Issue: Data not updating

**Solution:**
1. Check browser console for errors (F12)
2. Verify backend logs show incoming requests
3. Test API endpoints directly in browser/Postman
4. Check network tab in browser DevTools

#### Issue: Slow performance

**Frontend:**
- Check if React DevTools shows unnecessary re-renders
- Verify production build is used: `npm run build`

**Backend:**
- Use multiple workers: `--workers 4`
- Add caching for frequent requests
- Check database query performance

### Testing the Setup

#### 1. Test Backend API

```bash
# Health check
curl http://localhost:8000/

# Test specific endpoints
curl http://localhost:8000/api/machine-data
curl http://localhost:8000/api/utilities
curl http://localhost:8000/api/oee
```

#### 2. Test Frontend

1. Open http://localhost:3000
2. Check browser console (F12) for errors
3. Verify data loads in all three views:
   - Main Dashboard
   - Analytics
   - Database

#### 3. Test Real-time Updates

1. Open Dashboard view
2. Watch the machine data update every 3 seconds
3. Check network tab to see API calls

### Development Tips

#### Hot Reload

- **Frontend:** Automatically reloads on file changes
- **Backend:** Use `--reload` flag with uvicorn

#### Debugging

**Frontend:**
```bash
# Enable React DevTools
npm install -g react-devtools
react-devtools
```

**Backend:**
```python
# Add debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### API Testing

Use the interactive API docs:
1. Visit http://localhost:8000/docs
2. Try out each endpoint
3. See request/response examples

## 📚 Additional Resources

- [API Documentation](./BACKEND_API_DOCUMENTATION.md)
- [Integration Guide](./API_INTEGRATION_README.md)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)

## 🆘 Getting Help

1. Check the troubleshooting section above
2. Review API documentation
3. Check browser console for errors
4. Check backend logs for errors
5. Test API endpoints directly

## 📝 Next Steps

After successful setup:

1. **Customize the backend:**
   - Connect to your actual database
   - Implement real data sources
   - Add authentication if needed

2. **Customize the frontend:**
   - Adjust refresh rates in components
   - Modify color schemes
   - Add additional charts/metrics

3. **Deploy to production:**
   - Build frontend: `npm run build`
   - Configure production database
   - Set up proper hosting
   - Configure environment variables
   - Enable HTTPS

## ✅ Checklist

Before considering setup complete, verify:

- [ ] Backend starts without errors
- [ ] Frontend starts without errors
- [ ] Can access http://localhost:3000
- [ ] Can access http://localhost:8000/docs
- [ ] Dashboard loads all three views
- [ ] Data updates in real-time
- [ ] No CORS errors in console
- [ ] API calls visible in Network tab
- [ ] All charts render correctly

---

**Setup complete!** You now have a fully functional manufacturing dashboard with real-time data updates from your FastAPI backend.
