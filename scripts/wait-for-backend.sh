#!/bin/bash

# Wait for backend to be ready on port 10002
MAX_ATTEMPTS=30
ATTEMPT=0
BACKEND_URL="http://localhost:10002/.well-known/agent.json"

echo "Waiting for backend to be ready on port 10002..."

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  if curl -s -f "$BACKEND_URL" > /dev/null 2>&1; then
    echo "✅ Backend is ready!"
    exit 0
  fi
  
  ATTEMPT=$((ATTEMPT + 1))
  echo "  Attempt $ATTEMPT/$MAX_ATTEMPTS: Backend not ready yet, waiting 1 second..."
  sleep 1
done

echo "❌ Backend failed to start after $MAX_ATTEMPTS attempts"
exit 1

