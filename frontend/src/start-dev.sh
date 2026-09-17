#!/bin/bash

# Manufacturing Dashboard - Development Startup Script
# This script starts both the backend and frontend servers

echo "======================================================"
echo "   Manufacturing Dashboard - Development Mode"
echo "======================================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js."
    exit 1
fi

echo "✓ Python3 found: $(python3 --version)"
echo "✓ Node.js found: $(node --version)"
echo ""

# Check if FastAPI is installed
if ! python3 -c "import fastapi" 2> /dev/null; then
    echo "📦 Installing FastAPI dependencies..."
    pip3 install fastapi uvicorn pydantic
    echo ""
fi

echo "Starting services..."
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}

trap cleanup EXIT INT TERM

# Start the backend
echo "🚀 Starting FastAPI backend on http://localhost:8000"
python3 fastapi_backend_example.py &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Start the frontend (assuming you're using npm start)
echo "🚀 Starting React frontend on http://localhost:3000"
npm start &
FRONTEND_PID=$!

echo ""
echo "======================================================"
echo "   Services Running"
echo "======================================================"
echo "Backend API:  http://localhost:8000"
echo "API Docs:     http://localhost:8000/docs"
echo "Frontend:     http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"
echo "======================================================"
echo ""

# Wait for both processes
wait
