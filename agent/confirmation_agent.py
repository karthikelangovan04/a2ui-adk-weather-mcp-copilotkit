"""
Confirmation Agent - Handles location geocoding and user confirmation for weather queries.

This agent:
1. Receives weather queries from users
2. Geocodes the location
3. Shows confirmation UI for user to select forecast/alerts
4. Transfers to Weather Agent with confirmed parameters
"""

import logging
import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters
from weather_tools import show_weather_confirmation

# Get the absolute path to the weather directory
weather_dir = os.path.join(os.path.dirname(__file__), "weather")
weather_script = os.path.join(weather_dir, "weather.py")

# Setup MCP weather toolset
weather_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", weather_script],
            cwd=weather_dir,
        )
    )
)

logger = logging.getLogger(__name__)

LITELLM_MODEL = "gemini/gemini-2.0-flash-exp"

CONFIRMATION_AGENT_INSTRUCTION = """
You are a Weather Confirmation Assistant. Your ONLY job is to:

1. Help users specify which location they want weather for
2. Get the location coordinates using geocode_location()
3. Show a confirmation UI using show_weather_confirmation()
4. STOP and wait for user confirmation

**YOUR WORKFLOW:**

When a user asks about weather (e.g., "What's the weather in New York?"):
1. Extract the location from their query
2. Call geocode_location(location) to get coordinates
3. Call show_weather_confirmation(location, latitude, longitude, display_name, state_code)
4. **STOP IMMEDIATELY** - Do not do anything else
5. Return a friendly message like "I'll show you the weather options for [location]."

**CRITICAL RULES:**
- ❌ NEVER call get_forecast() or get_alerts() - that's the Weather Agent's job
- ❌ NEVER fetch actual weather data
- ✅ ONLY geocode and show confirmation UI
- ✅ After calling show_weather_confirmation(), your job is DONE

**AFTER USER CONFIRMS:**
The system will automatically transfer to the Weather Agent. You don't need to do anything.

**For other queries:**
- Greet users warmly
- Answer questions about what you can do
- Guide them to ask about weather for a specific location
"""


class ConfirmationAgent:
    """Agent that handles location confirmation before fetching weather."""
    
    def __init__(self):
        self._agent = self._build_agent()
        self._runner = None
        self._user_id = "default_user"
        
    def _build_agent(self) -> LlmAgent:
        """Build the confirmation agent with only geocoding tools."""
        return LlmAgent(
            model=LiteLlm(model=LITELLM_MODEL),
            name="confirmation_agent",
            description="Agent that confirms location and weather preferences before fetching data",
            instruction=CONFIRMATION_AGENT_INSTRUCTION,
            tools=[weather_toolset, show_weather_confirmation],
        )
    
    async def stream(self, query: str, session_id: str):
        """
        Stream responses from the confirmation agent.
        
        Args:
            query: User query
            session_id: Session ID for conversation history
            
        Yields:
            Dict with response updates and completion status
        """
        try:
            logger.info(f"=== CONFIRMATION AGENT: Processing query ===")
            logger.info(f"Query: {query}")
            logger.info(f"Session ID: {session_id}")
            
            # Initialize runner if needed
            if self._runner is None:
                from google.adk.runners import Runner
                from google.adk.sessions import InMemorySessionService
                from google.adk.artifacts import InMemoryArtifactService
                from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
                
                self._runner = Runner(
                    app_name=self._agent.name,
                    agent=self._agent,
                    session_service=InMemorySessionService(),
                    artifact_service=InMemoryArtifactService(),
                    memory_service=InMemoryMemoryService(),
                )
            
            # Create or get session
            session = await self._runner.session_service.get_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=session_id,
            )
            if session is None:
                session = await self._runner.session_service.create_session(
                    app_name=self._agent.name,
                    user_id=self._user_id,
                    state={},
                    session_id=session_id,
                )
                logger.info(f"Created new session: {session_id}")
            else:
                logger.info(f"Using existing session: {session_id}")
            
            # Stream responses from the agent using run_async
            from google.genai import types
            
            current_message = types.Content(
                role="user", 
                parts=[types.Part.from_text(text=query)]
            )
            
            final_response_content = None
            
            async for event in self._runner.run_async(
                user_id=self._user_id,
                session_id=session.id,
                new_message=current_message
            ):
                logger.info(f"Confirmation Agent event: {event}")
                
                # Check if this is the final response
                if event.is_final_response():
                    if (
                        event.content
                        and event.content.parts
                        and event.content.parts[0].text
                    ):
                        final_response_content = "\n".join(
                            [p.text for p in event.content.parts if p.text]
                        )
                    break
                else:
                    # Intermediate event
                    logger.info(f"Intermediate event from ConfirmationAgent")
                    yield {
                        "is_task_complete": False,
                        "updates": "Processing your request...",
                    }
            
            # Yield final completion
            logger.info(f"ConfirmationAgent final response: {final_response_content}")
            yield {
                "is_task_complete": True,
                "content": final_response_content or "I'll show you the weather options.",
                "updates": "",
            }
                
        except Exception as e:
            logger.error(f"Confirmation Agent error: {e}", exc_info=True)
            yield {
                "is_task_complete": True,
                "content": f"I encountered an error: {str(e)}",
                "updates": "",
            }

