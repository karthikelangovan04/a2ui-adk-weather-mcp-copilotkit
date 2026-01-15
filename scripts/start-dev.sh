#!/bin/bash

# Start backend and frontend in the correct order
# This ensures backend is ready before frontend tries to connect

echo "🚀 Starting development servers..."
echo ""

# Start backend in background
echo "📡 Starting backend agent server..."
cd "$(dirname "$0")/../agent" || exit 1
uv run . &
BACKEND_PID=$!
cd - > /dev/null

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready on port 10002..."
MAX_ATTEMPTS=30
ATTEMPT=0
BACKEND_URL="http://localhost:10002/.well-known/agent.json"

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  if curl -s -f "$BACKEND_URL" > /dev/null 2>&1; then
    echo "✅ Backend is ready!"
    break
  fi
  
  ATTEMPT=$((ATTEMPT + 1))
  if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
    sleep 1
  fi
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
  echo "❌ Backend failed to start after $MAX_ATTEMPTS seconds"
  kill $BACKEND_PID 2>/dev/null
  exit 1
fi

# Start frontend
echo "🎨 Starting frontend server..."
npm run dev:ui &
FRONTEND_PID=$!

# Function to cleanup on exit
cleanup() {
  echo ""
  echo "🛑 Shutting down servers..."
  kill $BACKEND_PID 2>/dev/null
  kill $FRONTEND_PID 2>/dev/null
  exit 0
}

trap cleanup SIGINT SIGTERM

echo ""
echo "✨ Both servers are running!"
echo "   Backend:  http://localhost:10002"
echo "   Frontend: http://localhost:3001"
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for both processes
wait

