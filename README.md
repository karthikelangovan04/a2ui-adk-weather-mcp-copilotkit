# Weather App with A2UI, A2A, and CopilotKit

This is a weather application that uses [A2UI](https://a2ui.org), [A2A](https://docs.copilotkit.ai/a2a), and [CopilotKit](https://copilotkit.ai) to provide weather forecasts and alerts. It features:

- **MCP Tools**: Uses Model Context Protocol (MCP) for weather data via the National Weather Service API
- **Google ADK**: Powered by Google's Agent Development Kit
- **Human-in-the-Loop**: Users can select which weather information they want (forecast, alerts, or both)
- **A2UI Components**: Beautiful, declarative UI components for displaying weather information
- **CopilotKit Integration**: Seamless chat interface with AI-powered weather assistance

## Prerequisites

- Gemeni API Key (for the ADK/A2A agent)
- Python 3.12+
- uv
- Node.js 20+
- Any of the following package managers:
  - pnpm (recommended)
  - npm
  - yarn
  - bun

> **Note:** This repository ignores lock files (package-lock.json, yarn.lock, pnpm-lock.yaml, bun.lockb) to avoid conflicts between different package managers. Each developer should generate their own lock file using their preferred package manager. After that, make sure to delete it from the .gitignore.

## Getting Started

1. Install dependencies using your preferred package manager:
```bash
# Using pnpm (recommended)
pnpm install

# Using npm
npm install

# Using yarn
yarn install

# Using bun
bun install
```

> **Note:** This will automatically setup the Python environment as well.
>
> If you have manual isseus, you can run:
>
> ```sh
> npm run install:agent
> ```


3. Set up your Gemeni API key:

Create a `.env` file inside the `agent` folder with the following content:

```
GEMENI_API_KEY=sk-...your-openai-key-here...
```


4. Start the development server:
```bash
# Using pnpm
pnpm dev

# Using npm
npm run dev

# Using yarn
yarn dev

# Using bun
bun run dev
```

This will start both the UI and agent servers concurrently.

## Available Scripts
The following scripts can also be run using your preferred package manager:
- `dev` - Starts both UI and agent servers in development mode
- `dev:debug` - Starts development servers with debug logging enabled
- `dev:ui` - Starts only the Next.js UI server
- `dev:agent` - Starts only the PydanticAI agent server
- `build` - Builds the Next.js application for production
- `start` - Starts the production server
- `lint` - Runs ESLint for code linting
- `install:agent` - Installs Python dependencies for the agent

## Documentation

The main UI component is in `app/page.tsx`, but most of the UI comes from the agent in the form of A2UI declarative components. To see and edit the components it can generate, look in `agent/prompt_builder.py`.

### How It Works

1. **User asks about weather**: "What's the weather in San Francisco?"
2. **Agent geocodes location**: Uses MCP `geocode_location` tool to get coordinates
3. **Human-in-the-loop confirmation**: Agent generates A2UI confirmation UI with checkboxes for forecast and alerts
4. **User selects options**: User checks which information they want
5. **Agent fetches data**: Based on selection, calls `get_forecast` and/or `get_alerts` MCP tools
6. **Beautiful UI display**: Weather data is rendered using A2UI components

### MCP Tools

The weather agent uses three MCP tools:
- `geocode_location(location: str)` - Converts location names to coordinates
- `get_forecast(latitude: float, longitude: float)` - Gets detailed weather forecast
- `get_alerts(state: str)` - Gets weather alerts for US states

To generate new components, try the [A2UI Composer](https://a2ui-editor.ag-ui.com)

## 📚 Documentation
- [A2UI + CopilotKit Documentation](https://docs.copilotkit.ai/a2a) - Learn more about how to use A2UI with CopilotKit
- [A2UI Documentation](https://a2ui.org) - Learn more about A2UI and its capabilities
- [CopilotKit Documentation](https://docs.copilotkit.ai) - Explore CopilotKit's capabilities
- [Next.js Documentation](https://nextjs.org/docs) - Learn about Next.js features and API

## Contributing

Feel free to submit issues and enhancement requests! This starter is designed to be easily extensible.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Troubleshooting

### Agent Connection Issues
If you see "I'm having trouble connecting to my tools", make sure:
1. The A2A agent is running on port 10002
2. The Next.js frontend is running on port 3001 (changed from default 3000)
3. Your Gemini API key is set correctly in `agent/.env` as `GEMINI_API_KEY`
4. Both servers started successfully
5. The MCP weather server can be started (requires `uv` and Python dependencies)

### Port Configuration
- **Frontend (Next.js)**: Port 3001 (configurable via `package.json`)
- **A2A Agent Server**: Port 10002 (configurable via `--port` flag)

### Python Dependencies
If you encounter Python import errors:
```bash
cd agent
uv sync
uv run .
```

### MCP Weather Server
The weather MCP server is located in `agent/weather/weather.py`. It uses:
- National Weather Service API for forecasts and alerts
- OpenStreetMap Nominatim API for geocoding

Make sure you have `httpx` and `fastmcp` installed (they should be in `pyproject.toml`).
