# Sharing Weather MCP Server Across Multiple Apps

## Will It Cause Issues?

**Short Answer:** Generally **NO**, but there are some considerations.

## How MCP Servers Work

The weather MCP server uses **stdio transport**, which means:
- ✅ Each application spawns its **own independent process**
- ✅ No port conflicts (stdio doesn't use network ports)
- ✅ Each process has its own memory space
- ✅ Processes are isolated from each other

## Potential Issues & Solutions

### 1. ✅ **File Path Sharing (SAFE)**
If both apps reference the same file path:
```python
weather_script = "/Users/karthike/Desktop/Vibe Coding/A2UI-Weather-App/agent/weather/weather.py"
```

**Status:** ✅ **SAFE** - Multiple processes can read the same file simultaneously. Python files are read-only at runtime.

### 2. ⚠️ **Different UV Environments (POTENTIAL ISSUE)**
If the other app uses a different `uv` environment or different dependency versions:

**Potential Issues:**
- Different versions of `fastmcp`, `httpx`, or `mcp` packages
- Missing dependencies in one environment
- Version conflicts

**Solution:** Ensure both projects have compatible dependencies:
```bash
# In both projects, ensure pyproject.toml has:
dependencies = [
    "mcp>=1.0.0",
    "fastmcp>=0.9.0",
    "httpx>=0.27.0",
]
```

### 3. ✅ **Same UV Environment (SAFE)**
If both apps are in the same project or use the same `uv` workspace:

**Status:** ✅ **SAFE** - They'll share the same dependencies and environment.

### 4. ⚠️ **File Permissions (RARE)**
If there are file permission issues:

**Solution:** Ensure the file is readable:
```bash
chmod 644 agent/weather/weather.py
```

### 5. ✅ **Concurrent Execution (SAFE)**
Multiple apps can run the same MCP server simultaneously:

**Status:** ✅ **SAFE** - Each spawns its own process with stdio transport.

## Best Practices

### Option 1: Share the File (Recommended for Same Project)
```python
# In both apps, reference the same file
weather_script = "/path/to/shared/weather/weather.py"
```

**Pros:**
- Single source of truth
- Easy to maintain
- No duplication

**Cons:**
- Both apps must be compatible with the same version

### Option 2: Copy the File (Recommended for Different Projects)
```bash
# Copy to each project
cp agent/weather/weather.py /other/project/weather/weather.py
```

**Pros:**
- Independent versions
- No cross-project dependencies
- Can customize per project

**Cons:**
- Code duplication
- Need to sync changes manually

### Option 3: Create a Shared Package (Best for Multiple Projects)
Create a reusable Python package:

```bash
# Create a shared package
mkdir -p ~/shared-packages/weather-mcp
cp agent/weather/weather.py ~/shared-packages/weather-mcp/
```

Then in each project's `pyproject.toml`:
```toml
[tool.uv.sources]
weather-mcp = { path = "~/shared-packages/weather-mcp" }
```

## Current Setup Analysis

Looking at your current setup:

```python
# In weather_agent.py
weather_dir = os.path.join(os.path.dirname(__file__), "weather")
weather_script = os.path.join(weather_dir, "weather.py")
```

This uses a **relative path**, so:
- ✅ Each project has its own copy (if copied)
- ✅ No conflicts between projects
- ✅ Each project is independent

## Testing for Conflicts

To verify there are no issues:

1. **Start both apps simultaneously:**
   ```bash
   # Terminal 1
   cd /path/to/app1
   pnpm dev
   
   # Terminal 2
   cd /path/to/app2
   pnpm dev
   ```

2. **Check for errors:**
   - Look for "Permission denied" errors
   - Look for "Module not found" errors
   - Look for "Port already in use" (shouldn't happen with stdio)

3. **Test functionality:**
   - Make weather requests from both apps
   - Verify both work independently

## Recommended Approach

For your use case, I recommend:

### If Both Apps Are Related (Same Project/Workspace):
✅ **Share the file** - Use the same path in both apps

### If Apps Are Separate Projects:
✅ **Copy the file** - Copy `weather.py` to each project's `agent/weather/` directory

### If You Have Many Projects:
✅ **Create a shared package** - Make it a reusable Python package

## Example: Using in Another App

If you want to use it in another app:

```python
# In the other app's agent file
import os
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

# Option 1: Reference shared file
weather_script = "/Users/karthike/Desktop/Vibe Coding/A2UI-Weather-App/agent/weather/weather.py"

# Option 2: Use relative path (if copied)
weather_dir = os.path.join(os.path.dirname(__file__), "weather")
weather_script = os.path.join(weather_dir, "weather.py")

# Setup MCP toolset (same as current app)
weather_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", weather_script],
            env={"UV_NO_CACHE": "1"}
        )
    )
)
```

## Summary

| Scenario | Safe? | Notes |
|----------|-------|-------|
| Same file, same project | ✅ Yes | No issues |
| Same file, different projects | ✅ Yes | Ensure compatible dependencies |
| Different files, same code | ✅ Yes | Best practice for separate projects |
| Different UV environments | ⚠️ Maybe | Check dependency versions |
| Concurrent execution | ✅ Yes | Each spawns own process |

**Conclusion:** You can safely use the same weather MCP server in multiple apps. The stdio transport ensures process isolation, and file sharing is safe for read-only Python files.

