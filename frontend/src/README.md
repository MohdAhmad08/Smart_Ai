# Manufacturing Dashboard

A modern, real-time manufacturing dashboard built with React, TypeScript, Tailwind CSS, and FastAPI. Monitor machine performance, utilities consumption, OEE metrics, and system alerts in real-time.

![Dashboard](https://img.shields.io/badge/Status-Production%20Ready-success)
![React](https://img.shields.io/badge/React-18.x-blue)
![TypeScript](https://img.shields.io/badge/TypeScript-5.x-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Latest-green)

## ✨ Features

### Real-Time Monitoring
- **Machine Data** - Live speed, temperature, LOT tracking
- **Utilities Consumption** - Steam, Water, Air, Energy, Chemicals
- **OEE Metrics** - Availability, Performance, Quality tracking
- **System Alerts** - Critical, Warning, and Info notifications
- **Advanced Analytics** - Temperature trends, production rates, cost analysis

### User Interface
- 🎨 Modern, clean design with responsive layout
- 📊 Interactive charts and graphs
- 🔄 Auto-refresh every 3-60 seconds (configurable)
- 📱 Mobile-friendly responsive design
- 🖨️ Print functionality for all sections
- 💾 Data export (CSV/Excel)
- 🔍 Search and filter capabilities

### Technical Features
- ⚡ Real-time data updates via REST API
- 🎯 TypeScript for type safety
- 🔌 RESTful API with FastAPI backend
- 📡 Auto-retry and error handling
- 🎭 Loading states and error notifications
- 📚 Interactive API documentation

## 🚀 Quick Start

### Prerequisites
- Node.js 16+ and npm
- Python 3.7+

### Installation & Running

**Option 1: Automated (Recommended)**

Linux/Mac:
```bash
chmod +x start-dev.sh
./start-dev.sh
```

Windows:
```bash
start-dev.bat
```

**Option 2: Manual**

```bash
# Terminal 1 - Backend
pip install fastapi uvicorn pydantic
python3 fastapi_backend_example.py

# Terminal 2 - Frontend
npm install
npm start
```

### Access the Application
- 🖥️ **Dashboard**: http://localhost:3000
- 📡 **API**: http://localhost:8000
- 📖 **API Docs**: http://localhost:8000/docs

## 📱 Views

### 1. Main Dashboard
Real-time machine data, utilities consumption, and OEE performance metrics in a three-column layout.

### 2. Analytics
Machine activity timeline, system alerts, and advanced analytics with production trends.

### 3. Database
Historical records with search, filter, and export capabilities.

## 🔧 Configuration

### Change API URL

Create `.env` file:
```env
REACT_APP_API_URL=http://localhost:8000
```

### Customize Refresh Rates

Edit component intervals in:
- `ProductionFloorView.tsx` - Machine data (default: 3s)
- `AlertsTable.tsx` - Alerts (default: 30s)
- `AdvancedAnalytics.tsx` - Analytics (default: 60s)

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md) | Overview of API integration |
| [SETUP_GUIDE.md](SETUP_GUIDE.md) | Complete setup instructions |
| [API_INTEGRATION_README.md](API_INTEGRATION_README.md) | Integration guide |
| [BACKEND_API_DOCUMENTATION.md](BACKEND_API_DOCUMENTATION.md) | Complete API specs |
| [API_QUICK_REFERENCE.md](API_QUICK_REFERENCE.md) | Quick reference card |

## 🏗️ Architecture

### Frontend Stack
- **React** - UI framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Recharts** - Data visualization
- **shadcn/ui** - UI components
- **Lucide React** - Icons
- **Sonner** - Toast notifications

### Backend Stack
- **FastAPI** - Python web framework
- **Pydantic** - Data validation
- **Uvicorn** - ASGI server

### Project Structure
```
├── components/          # React components
│   ├── ProductionFloorView.tsx
│   ├── DatabaseView.tsx
│   ├── AlertsTable.tsx
│   └── ...
├── services/           # API service layer
│   └── api.ts
├── fastapi_backend_example.py  # Backend server
└── documentation/      # All docs
```

## 🔌 API Endpoints

| Endpoint | Description | Refresh |
|----------|-------------|---------|
| `GET /api/machine-data` | Machine status | 3s |
| `GET /api/utilities` | Utilities data | 3s |
| `GET /api/oee` | OEE metrics | 3s |
| `GET /api/alerts` | System alerts | 30s |
| `GET /api/analytics/*` | Analytics data | 60s |
| `GET /api/database-records` | Historical data | On filter |
| `GET /api/machine-timeline` | Activity timeline | On range |

See [API_QUICK_REFERENCE.md](API_QUICK_REFERENCE.md) for complete details.

## 🧪 Testing

### Test Backend
```bash
# Health check
curl http://localhost:8000/

# Test endpoint
curl http://localhost:8000/api/machine-data

# Interactive docs
open http://localhost:8000/docs
```

### Test Frontend
1. Open http://localhost:3000
2. Navigate through all three views
3. Verify real-time data updates
4. Check browser console for errors

## 🌐 Production Deployment

### Frontend
```bash
# Build optimized bundle
npm run build

# Serve with static server
npx serve -s build
```

### Backend
```bash
# Install gunicorn
pip install gunicorn

# Run with multiple workers
gunicorn fastapi_backend_example:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Environment Variables
```env
# Production settings
REACT_APP_API_URL=https://api.yourdomain.com
REACT_APP_ENV=production
```

## 🔐 Security

For production:
- [ ] Enable HTTPS
- [ ] Implement authentication
- [ ] Add rate limiting
- [ ] Configure CORS properly
- [ ] Use environment variables for secrets
- [ ] Enable logging and monitoring

## 🐛 Troubleshooting

### Common Issues

**Backend not responding:**
```bash
curl http://localhost:8000/
```

**CORS errors:**
Check `allow_origins` in backend CORS middleware

**Data not updating:**
Check browser console and backend logs

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed troubleshooting.

## 📊 Data Flow

```
Frontend Components
    ↓
API Service Layer (/services/api.ts)
    ↓
HTTP Requests
    ↓
FastAPI Backend
    ↓
Your Data Source (Database/PLC/Sensors)
```

## 🛠️ Development

### Add New Feature
1. Create component in `/components`
2. Add API endpoint in backend
3. Add API function in `/services/api.ts`
4. Import and use in component

### Connect Real Database
Edit `fastapi_backend_example.py` to connect to your database:
```python
from sqlalchemy import create_engine
# Your database connection code
```

## 📈 Performance

- **Auto-refresh rates**: Optimized for real-time without overwhelming
- **Loading states**: Prevent UI freezing during data fetch
- **Error handling**: Graceful degradation on API failures
- **Type safety**: TypeScript prevents runtime errors

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Test thoroughly
5. Submit pull request

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Built with [React](https://react.dev/)
- Powered by [FastAPI](https://fastapi.tiangolo.com/)
- UI components from [shadcn/ui](https://ui.shadcn.com/)
- Icons from [Lucide](https://lucide.dev/)

## 📞 Support

- 📖 [Setup Guide](SETUP_GUIDE.md)
- 🔧 [API Documentation](BACKEND_API_DOCUMENTATION.md)
- 💬 [Integration Guide](API_INTEGRATION_README.md)

---

**Made with ❤️ for Manufacturing Excellence**

Get started now:
```bash
./start-dev.sh  # Linux/Mac
start-dev.bat   # Windows
```
