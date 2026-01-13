# Step-by-Step Guide to Start Frontend and Backend

## Prerequisites Check

Before starting, ensure you have the following installed:

```bash
# Check Node.js (should be 20+)
node --version

# Check Python (should be 3.12+)
python3 --version

# Check uv (Python package manager)
uv --version

# Check package manager (pnpm, npm, yarn, or bun)
pnpm --version  # or npm --version
```

## Step 1: Navigate to Project Directory

```bash
cd /Users/karthike/Desktop/Vibe\ Coding/A2UI-Weather-App
```

## Step 2: Verify Environment File

Check that the `.env` file exists in the `agent` folder with your Gemini API key:

```bash
cat agent/.env
```

Expected output should show:
```
GEMINI_API_KEY=your-api-key-here
```

If the file doesn't exist or is missing the key, create it:
```bash
echo "GEMINI_API_KEY=your-api-key-here" > agent/.env
```

## Step 3: Install Frontend Dependencies

Install Node.js dependencies (this will also automatically install Python dependencies):

```bash
# Using pnpm (recommended)
pnpm install

# OR using npm
npm install

# OR using yarn
yarn install

# OR using bun
bun install
```

> **Note:** The `postinstall` script will automatically run `install:agent` to set up Python dependencies.

## Step 4: Verify Python Dependencies (Optional)

If you want to manually verify Python dependencies are installed:

```bash
cd agent
uv sync
cd ..
```

## Step 5: Start Both Servers

### Option A: Start Both Together (Recommended)

This starts both frontend and backend concurrently:

```bash
# Using pnpm
pnpm dev

# OR using npm
npm run dev

# OR using yarn
yarn dev

# OR using bun
bun run dev
```

This will start:
- **Backend (A2A Agent)**: http://localhost:10002
- **Frontend (Next.js)**: http://localhost:3001

### Option B: Start Separately (For Debugging)

If you prefer to start them in separate terminals:

**Terminal 1 - Backend:**
```bash
# Start the A2A agent server
npm run dev:agent
# OR
./scripts/run-agent.sh
```

**Terminal 2 - Frontend:**
```bash
# Start the Next.js frontend
npm run dev:ui
# OR
pnpm dev:ui
```

## Step 6: Access the Application

Once both servers are running, open your browser and navigate to:

**Frontend URL:** http://localhost:3001

The frontend will automatically connect to the backend agent running on port 10002.

## Verification Checklist

✅ **Backend is running** if you see:
```
INFO:     Uvicorn running on http://localhost:10002
```

✅ **Frontend is running** if you see:
```
▲ Next.js 16.0.10
- Local:        http://localhost:3001
```

✅ **Both are connected** if:
- The chat interface loads in the browser
- You can ask weather questions
- The agent responds with weather information

## Troubleshooting

### Backend Won't Start

1. **Check API Key:**
   ```bash
   cat agent/.env | grep GEMINI_API_KEY
   ```

2. **Check Python Dependencies:**
   ```bash
   cd agent
   uv sync
   ```

3. **Check Port 10002 is Available:**
   ```bash
   lsof -i :10002
   ```
   If something is using it, kill the process or change the port in `agent/__main__.py`

### Frontend Won't Start

1. **Check Node Dependencies:**
   ```bash
   rm -rf node_modules
   pnpm install
   ```

2. **Check Port 3001 is Available:**
   ```bash
   lsof -i :3001
   ```
   If something is using it, change the port in `package.json` under `dev:ui`

3. **Clear Next.js Cache:**
   ```bash
   rm -rf .next
   pnpm dev:ui
   ```

### Connection Issues

1. **Verify Backend is Running:**
   ```bash
   curl http://localhost:10002/health
   ```
   Should return: `{"status":"healthy"}`

2. **Check CORS Settings:**
   - Verify `agent/__main__.py` has `http://localhost:3001` in allowed origins

3. **Check API Route:**
   - Verify `app/api/copilotkit/[[...slug]]/route.tsx` points to `http://localhost:10002`

## Quick Start (All-in-One)

If everything is set up, you can start both servers with a single command:

```bash
cd /Users/karthike/Desktop/Vibe\ Coding/A2UI-Weather-App
pnpm dev
```

Then open http://localhost:3001 in your browser!

## Stopping the Servers

- **If started together:** Press `Ctrl+C` in the terminal
- **If started separately:** Press `Ctrl+C` in each terminal

## Development Commands Reference

```bash
# Start both servers
pnpm dev

# Start only frontend
pnpm dev:ui

# Start only backend
pnpm dev:agent

# Start with debug logging
pnpm dev:debug

# Install Python dependencies manually
pnpm install:agent

# Build for production
pnpm build

# Start production server
pnpm start
```

