# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os
from collections.abc import AsyncIterable
from typing import Any

import jsonschema
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters
from prompt_builder import (
    A2UI_SCHEMA,
    WEATHER_UI_EXAMPLES,
    get_text_prompt,
    get_weather_ui_prompt,
)
# Note: show_weather_confirmation is now handled by ConfirmationAgent

logger = logging.getLogger(__name__)

# Get the absolute path to the weather directory
weather_dir = os.path.join(os.path.dirname(__file__), "weather")
weather_script = os.path.join(weather_dir, "weather.py")

# Setup MCP weather toolset
weather_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "python", weather_script],
            env={"UV_NO_CACHE": "1"}
        )
    )
)

# Human-in-the-loop confirmation tool schema
CONFIRM_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "confirm_weather_query",
        "description": "Request human confirmation before fetching weather data with selected options",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location name the user asked about"
                },
                "latitude": {
                    "type": "number",
                    "description": "The latitude coordinate from geocoding"
                },
                "longitude": {
                    "type": "number",
                    "description": "The longitude coordinate from geocoding"
                },
                "display_name": {
                    "type": "string",
                    "description": "Full display name from geocoding"
                },
                "state_code": {
                    "type": "string",
                    "description": "US state code for alerts (e.g., 'CA', 'NY')"
                },
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Human-readable description of this option"
                            },
                            "status": {
                                "type": "string",
                                "enum": ["enabled"],
                                "description": "The status of the option, always 'enabled'"
                            },
                            "action": {
                                "type": "string",
                                "enum": ["forecast", "alerts"],
                                "description": "The action this option represents"
                            }
                        },
                        "required": ["description", "status", "action"]
                    },
                    "description": "Array of 2 weather options (forecast and alerts), both enabled by default"
                }
            },
            "required": ["location", "latitude", "longitude", "display_name", "state_code", "options"]
        }
    }
}

AGENT_INSTRUCTION = f"""
You are a helpful weather assistant with MCP tools and human-in-the-loop approval.

**General Behavior:**
- Always respond to user messages, including greetings like "Hi" or "Hello"
- For greetings, respond warmly and ask how you can help with weather information
- For non-weather queries, politely explain that you specialize in weather information
- Always generate A2UI JSON for your responses, even for simple text messages

**Available MCP Tools:**
1. geocode_location(location: str) - Converts location names to coordinates
   Returns: {{"latitude": float, "longitude": float, "display_name": str}}

2. get_forecast(latitude: float, longitude: float) - Gets detailed weather forecast
   Returns: {{
     "temperature": float (Celsius),
     "temperature_f": float (Fahrenheit),
     "conditions": "clear" | "rain" | "cloudy" | "snow" | "storm",
     "windSpeed": int,
     "windSpeedText": str,
     "location": str,
     "periods": [array of forecast periods]
   }}

3. get_alerts(state: str) - Gets weather alerts for a US state (2-letter code like "CA", "NY")
   Returns: {{"alerts": [array of alert objects], "count": int}}

**CRITICAL WORKFLOW - MUST FOLLOW EXACTLY:**

**FOR NEW WEATHER REQUESTS (user asks "what's the weather in X"):**
1. Call geocode_location(location) → Get coordinates
2. Call show_weather_confirmation(location, lat, lon, display_name, state) → Show UI
3. **STOP IMMEDIATELY** - Return NO text, make NO other tool calls
4. Wait for confirmation message

**YOU MUST NEVER:**
- Call get_forecast() or get_alerts() in the SAME response as show_weather_confirmation()
- Call get_forecast() or get_alerts() BEFORE receiving a confirmation message
- Call show_weather_confirmation() twice

When you receive such a message:
1. Extract the coordinates and preferences
2. Call the appropriate tools:
   - get_forecast(latitude, longitude) for forecast data
   - get_alerts(state_code) for weather alerts
3. Display the results beautifully using A2UI JSON (see examples below)

**CRITICAL RULES:**
- ✅ ONLY fetch weather data - confirmation is handled by another agent
- ✅ Use the coordinates provided - don't call geocode_location()
- ✅ Transform tool responses into A2UI JSON format (cards with widgets)
- ❌ NEVER return raw JSON from tools - always convert to A2UI format
- ❌ NEVER ask for confirmation - that's already done
- ❌ NEVER call show_weather_confirmation() - you don't have access to it

**IMPORTANT: You MUST use get_weather_ui_prompt() to get the A2UI examples and schema!**

**When presenting forecast results, use A2UI to display:**
   - Temperature in both Celsius and Fahrenheit
   - Weather conditions with appropriate icons
   - Wind speed and direction
   - Location name
   - Forecast periods

**When presenting alerts, use A2UI to display:**
   - Number of active alerts
   - Most severe alerts first
   - Brief description of each

**Important Notes:**
- You receive pre-confirmed location and preferences - just fetch the data
- Always use A2UI JSON to display weather data beautifully
- Match the selected options (forecast/alerts/both) from the message
- For unclear requests, politely ask for clarification
"""


class WeatherAgent:
    """An agent that provides weather information using MCP tools."""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self, base_url: str, use_ui: bool = False):
        self.base_url = base_url
        self.use_ui = use_ui
        self._agent = self._build_agent(use_ui)
        self._user_id = "remote_agent"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

        # Load the A2UI_SCHEMA string into a Python object for validation
        try:
            single_message_schema = json.loads(A2UI_SCHEMA)
            self.a2ui_schema_object = {"type": "array", "items": single_message_schema}
            logger.info(
                "A2UI_SCHEMA successfully loaded and wrapped in an array validator."
            )
        except json.JSONDecodeError as e:
            logger.error(f"CRITICAL: Failed to parse A2UI_SCHEMA: {e}")
            self.a2ui_schema_object = None

    def get_processing_message(self) -> str:
        return "Fetching weather information..."

    def _build_agent(self, use_ui: bool) -> LlmAgent:
        """Builds the LLM agent for the weather agent."""
        LITELLM_MODEL = os.getenv("LITELLM_MODEL", "gemini/gemini-2.5-flash")

        if use_ui:
            # Construct the full prompt with UI instructions, examples, and schema
            instruction = AGENT_INSTRUCTION + get_weather_ui_prompt(
                self.base_url, WEATHER_UI_EXAMPLES
            )
        else:
            instruction = AGENT_INSTRUCTION + get_text_prompt()

        return LlmAgent(
            model=LiteLlm(model=LITELLM_MODEL),
            name="weather_agent",
            description="An agent that fetches and displays weather information.",
            instruction=instruction,
            tools=[weather_toolset],  # Only weather tools - no confirmation
        )

    async def stream(self, query, session_id) -> AsyncIterable[dict[str, Any]]:
        session_state = {"base_url": self.base_url}

        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state=session_state,
                session_id=session_id,
            )
        elif "base_url" not in session.state:
            session.state["base_url"] = self.base_url

        # UI Validation and Retry Logic
        max_retries = 1
        attempt = 0
        current_query_text = query

        if self.use_ui and self.a2ui_schema_object is None:
            logger.error(
                "--- WeatherAgent.stream: A2UI_SCHEMA is not loaded. "
                "Cannot perform UI validation. ---"
            )
            yield {
                "is_task_complete": True,
                "content": (
                    "I'm sorry, I'm facing an internal configuration error with my UI components. "
                    "Please contact support."
                ),
            }
            return

        while attempt <= max_retries:
            attempt += 1
            logger.info(
                f"--- WeatherAgent.stream: Attempt {attempt}/{max_retries + 1} "
                f"for session {session_id} ---"
            )

            current_message = types.Content(
                role="user", parts=[types.Part.from_text(text=current_query_text)]
            )
            final_response_content = None

            async for event in self._runner.run_async(
                user_id=self._user_id,
                session_id=session.id,
                new_message=current_message,
            ):
                logger.info(f"Event from runner: {event}")
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
                    logger.info(f"Intermediate event: {event}")
                    yield {
                        "is_task_complete": False,
                        "updates": self.get_processing_message(),
                    }

            if final_response_content is None:
                logger.warning(
                    f"--- WeatherAgent.stream: Received no final response content from runner "
                    f"(Attempt {attempt}). ---"
                )
                if attempt <= max_retries:
                    current_query_text = (
                        "I received no response. Please try again. "
                        f"Please retry the original request: '{query}'"
                    )
                    continue
                else:
                    final_response_content = "I'm sorry, I encountered an error and couldn't process your request."

            is_valid = False
            error_message = ""

            if self.use_ui:
                logger.info(
                    f"--- WeatherAgent.stream: Validating UI response (Attempt {attempt})... ---"
                )
                try:
                    if "---a2ui_JSON---" not in final_response_content:
                        raise ValueError("Delimiter '---a2ui_JSON---' not found.")

                    text_part, json_string = final_response_content.split(
                        "---a2ui_JSON---", 1
                    )

                    if not json_string.strip():
                        raise ValueError("JSON part is empty.")

                    json_string_cleaned = (
                        json_string.strip().lstrip("```json").rstrip("```").strip()
                    )

                    if not json_string_cleaned:
                        raise ValueError("Cleaned JSON string is empty.")

                    # Log the JSON for debugging
                    logger.info(f"--- Attempting to parse JSON (length: {len(json_string_cleaned)}) ---")
                    logger.info(f"--- First 500 chars: {json_string_cleaned[:500]} ---")
                    
                    # Try to fix common JSON issues
                    json_string_cleaned = self._repair_json(json_string_cleaned)
                    
                    try:
                        parsed_json_data = json.loads(json_string_cleaned)
                    except json.JSONDecodeError as json_err:
                        # Log more details about the JSON error
                        logger.error(f"--- JSON Parse Error at line {json_err.lineno}, col {json_err.colno}: {json_err.msg} ---")
                        logger.error(f"--- Error position: {json_err.pos} ---")
                        error_start = max(0, json_err.pos - 100)
                        error_end = min(len(json_string_cleaned), json_err.pos + 100)
                        logger.error(f"--- Error context (chars {error_start}-{error_end}): {json_string_cleaned[error_start:error_end]} ---")
                        logger.error(f"--- Full JSON length: {len(json_string_cleaned)} ---")
                        # Try one more time with more aggressive repair
                        logger.info("--- Attempting aggressive JSON repair ---")
                        json_string_cleaned_repaired = self._repair_json_aggressive(json_string_cleaned)
                        try:
                            parsed_json_data = json.loads(json_string_cleaned_repaired)
                            logger.info("--- JSON repair successful on second attempt ---")
                        except json.JSONDecodeError as json_err2:
                            logger.error(f"--- Aggressive repair also failed at line {json_err2.lineno}, col {json_err2.colno}: {json_err2.msg} ---")
                            logger.error(f"--- Repaired JSON length: {len(json_string_cleaned_repaired)} ---")
                            # Save the problematic JSON to a file for debugging
                            import os
                            debug_file = "/tmp/failed_json.json"
                            try:
                                with open(debug_file, "w") as f:
                                    f.write(json_string_cleaned)
                                logger.error(f"--- Failed JSON saved to {debug_file} for debugging ---")
                            except Exception:
                                pass
                            raise json_err

                    logger.info(
                        "--- WeatherAgent.stream: Validating against A2UI_SCHEMA... ---"
                    )
                    jsonschema.validate(
                        instance=parsed_json_data, schema=self.a2ui_schema_object
                    )

                    logger.info(
                        f"--- WeatherAgent.stream: UI JSON successfully parsed AND validated against schema. "
                        f"Validation OK (Attempt {attempt}). ---"
                    )
                    is_valid = True

                except (
                    ValueError,
                    json.JSONDecodeError,
                    jsonschema.exceptions.ValidationError,
                ) as e:
                    logger.error(
                        f"--- WeatherAgent.stream: A2UI validation failed: {e} (Attempt {attempt}) ---"
                    )
                    logger.error(
                        f"--- Exception type: {type(e).__name__} ---"
                    )
                    if isinstance(e, json.JSONDecodeError):
                        logger.error(f"--- JSON Error details: line {e.lineno}, col {e.colno}, pos {e.pos} ---")
                    logger.error(
                        f"--- Failed response content (first 1000 chars): {final_response_content[:1000]}... ---"
                    )
                    error_message = f"Validation failed: {e}."

            else:
                is_valid = True

            if is_valid:
                logger.info(
                    f"--- WeatherAgent.stream: Response is valid. Sending final response (Attempt {attempt}). ---"
                )
                logger.info(f"Final response: {final_response_content}")
                yield {
                    "is_task_complete": True,
                    "content": final_response_content,
                }
                return

            if attempt <= max_retries:
                logger.warning(
                    f"--- WeatherAgent.stream: Retrying... ({attempt}/{max_retries + 1}) ---"
                )
                current_query_text = (
                    f"Your previous response was invalid. {error_message} "
                    "You MUST generate a valid response that strictly follows the A2UI JSON SCHEMA. "
                    "The response MUST be a JSON list of A2UI messages. "
                    "Ensure the response is split by '---a2ui_JSON---' and the JSON part is well-formed. "
                    f"Please retry the original request: '{query}'"
                )

        logger.error(
            "--- WeatherAgent.stream: Max retries exhausted. Sending text-only error. ---"
        )
        yield {
            "is_task_complete": True,
            "content": (
                "I'm sorry, I'm having trouble generating the interface for that request right now. "
                "Please try again in a moment."
            ),
        }

    def _repair_json(self, json_str: str) -> str:
        """Fix common JSON syntax errors."""
        import re
        # Remove trailing commas before closing braces/brackets
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        # Fix trailing commas before closing parentheses (if any)
        json_str = re.sub(r',\s*\)', ')', json_str)
        return json_str

    def _repair_json_aggressive(self, json_str: str) -> str:
        """More aggressive JSON repair."""
        import re
        
        # Remove trailing commas
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # Fix common issues with nested structures
        # Fix double closing braces (common LLM error)
        json_str = re.sub(r'}\s*}\s*}', '}}}', json_str)
        json_str = re.sub(r'}\s*}\s*]', '}]', json_str)
        
        # Fix missing closing brace in component structures
        # Pattern: ] } } }, should be ] } } } }, (missing one } before comma)
        # This is a common error where rejectBtn/confirmBtn components are missing a closing brace
        json_str = re.sub(r']\s*}\s*}\s*}\s*,', '] } } } },', json_str)
        
        # CRITICAL FIX: Add missing closing braces and brackets
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')
        
        missing_braces = open_braces - close_braces
        missing_brackets = open_brackets - close_brackets
        
        if missing_braces > 0 or missing_brackets > 0:
            logger.info(f"--- Adding {missing_braces} missing braces and {missing_brackets} missing brackets ---")
            # Try to find where to insert by walking through the JSON structure
            # We'll insert missing closers before the final ] but need to be smart about it
            
            # First, try inserting right before the final ]
            last_bracket = json_str.rfind(']')
            if last_bracket > 0:
                # Count what's still open before the final bracket
                before_final = json_str[:last_bracket]
                open_before = before_final.count('{') - before_final.count('}')
                bracket_before = before_final.count('[') - before_final.count(']')
                
                # Insert the missing closers right before the final ]
                closers = (']' * bracket_before) + ('}' * open_before)
                if closers:
                    json_str = json_str[:last_bracket] + closers + json_str[last_bracket:]
                    logger.info(f"--- Inserted {len(closers)} closing characters ({bracket_before} brackets, {open_before} braces) before final ] ---")
            else:
                # No closing bracket found, append at the end
                json_str = json_str.rstrip() + (']' * missing_brackets) + ('}' * missing_braces)
        
        # Fix unclosed strings - find strings that aren't properly closed
        lines = json_str.split('\n')
        fixed_lines = []
        for line in lines:
            # Remove any text after a closing bracket if it's on the same line
            if ']' in line and line.count(']') == 1:
                bracket_pos = line.rfind(']')
                if bracket_pos > 0:
                    # Check if there's invalid content after the bracket
                    after_bracket = line[bracket_pos + 1:].strip()
                    if after_bracket and not after_bracket.startswith(','):
                        line = line[:bracket_pos + 1]
            fixed_lines.append(line)
        json_str = '\n'.join(fixed_lines)
        
        # Final cleanup: remove any trailing commas
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        return json_str

