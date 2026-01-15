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
import re

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    DataPart,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_parts_message,
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError
from a2ui.a2ui_extension import create_a2ui_part, try_activate_a2ui_extension
from weather.weather import geocode_location
from weather_agent import WeatherAgent

logger = logging.getLogger(__name__)


class WeatherAgentExecutor(AgentExecutor):
    """Weather AgentExecutor with human-in-the-loop support."""

    def __init__(self, base_url: str):
        # Instantiate two agents: one for UI and one for text-only.
        self.ui_agent = WeatherAgent(base_url=base_url, use_ui=True)
        self.text_agent = WeatherAgent(base_url=base_url, use_ui=False)

    def _is_weather_query(self, query: str) -> bool:
        """Check if the query is asking for weather information."""
        if not query:
            return False
        query_lower = query.lower().strip()
        weather_keywords = [
            "weather", "forecast", "temperature", "temp", "rain", "snow",
            "sunny", "cloudy", "wind", "humidity", "alerts", "storm"
        ]
        return any(keyword in query_lower for keyword in weather_keywords)

    def _extract_location_from_query(self, query: str) -> str | None:
        """Extract location from weather query."""
        # Simple pattern matching - look for "weather in/for [location]" or similar
        patterns = [
            r"weather\s+(?:in|for|at)\s+(.+?)(?:\?|$)",
            r"(?:what'?s|what is|get|show|check)\s+(?:the\s+)?weather\s+(?:in|for|at)\s+(.+?)(?:\?|$)",
            r"weather\s+(.+?)(?:\?|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                # Remove common trailing words
                location = re.sub(r"\s+(please|now|today|tomorrow)$", "", location, flags=re.IGNORECASE)
                if location and len(location) > 1:
                    return location
        return None

    def _extract_state_code(self, display_name: str) -> str:
        """Extract US state code from display_name (e.g., 'New York, NY, USA' -> 'NY')."""
        # Pattern: Look for ", XX, " or ", XX " where XX is 2 uppercase letters
        match = re.search(r",\s*([A-Z]{2})(?:\s*,|\s*$)", display_name)
        if match:
            return match.group(1)
        return ""

    def _generate_confirmation_ui(self, location: str, latitude: float, longitude: float, display_name: str, state_code: str) -> list:
        """Generate the static confirmation UI JSON directly (no LLM needed)."""
        return [
            {
                "beginRendering": {
                    "surfaceId": "weather-confirmation",
                    "root": "root",
                    "styles": {"primaryColor": "#4CAF50", "font": "Roboto"}
                }
            },
            {
                "surfaceUpdate": {
                    "surfaceId": "weather-confirmation",
                    "components": [
                        {
                            "id": "root",
                            "component": {
                                "Column": {
                                    "children": {"explicitList": ["title", "forecastCheck", "alertsCheck", "alertsConfirmRow"]},
                                    "distribution": "start",
                                    "alignment": "start"
                                }
                            }
                        },
                        {
                            "id": "title",
                            "component": {
                                "Text": {
                                    "text": {"literalString": "Select Weather Actions"},
                                    "usageHint": "h2"
                                }
                            }
                        },
                        {
                            "id": "forecastCheck",
                            "component": {
                                "CheckBox": {
                                    "label": {"literalString": "Get current forecast"},
                                    "value": {"path": "/form/forecastSelected"}
                                }
                            }
                        },
                        {
                            "id": "alertsCheck",
                            "component": {
                                "CheckBox": {
                                    "label": {"literalString": "Check weather alerts"},
                                    "value": {"path": "/form/alertsSelected"}
                                }
                            }
                        },
                        {
                            "id": "alertsConfirmRow",
                            "component": {
                                "Row": {
                                    "children": {"explicitList": ["rejectBtn", "confirmBtn"]},
                                    "distribution": "spaceEvenly",
                                    "alignment": "center"
                                }
                            }
                        },
                        {
                            "id": "rejectBtn",
                            "component": {
                                "Button": {
                                    "child": "rejectBtnText",
                                    "primary": False,
                                    "action": {
                                        "name": "rejectAlerts",
                                        "context": [
                                            {"key": "alertsConfirmed", "value": {"literalString": "rejected"}},
                                            {"key": "location", "value": {"literalString": location}},
                                            {"key": "latitude", "value": {"literalNumber": latitude}},
                                            {"key": "longitude", "value": {"literalNumber": longitude}},
                                            {"key": "display_name", "value": {"literalString": display_name}},
                                            {"key": "state_code", "value": {"literalString": state_code}},
                                            {"key": "forecastSelected", "value": {"path": "/form/forecastSelected"}},
                                            {"key": "alertsSelected", "value": {"path": "/form/alertsSelected"}}
                                        ]
                                    }
                                }
                            }
                        },
                        {
                            "id": "rejectBtnText",
                            "component": {
                                "Text": {
                                    "text": {"literalString": "Reject"}
                                }
                            }
                        },
                        {
                            "id": "confirmBtn",
                            "component": {
                                "Button": {
                                    "child": "confirmBtnText",
                                    "primary": True,
                                    "action": {
                                        "name": "confirmAlerts",
                                        "context": [
                                            {"key": "alertsConfirmed", "value": {"literalString": "confirmed"}},
                                            {"key": "location", "value": {"literalString": location}},
                                            {"key": "latitude", "value": {"literalNumber": latitude}},
                                            {"key": "longitude", "value": {"literalNumber": longitude}},
                                            {"key": "display_name", "value": {"literalString": display_name}},
                                            {"key": "state_code", "value": {"literalString": state_code}},
                                            {"key": "forecastSelected", "value": {"path": "/form/forecastSelected"}},
                                            {"key": "alertsSelected", "value": {"path": "/form/alertsSelected"}}
                                        ]
                                    }
                                }
                            }
                        },
                        {
                            "id": "confirmBtnText",
                            "component": {
                                "Text": {
                                    "text": {"literalString": "Confirm"}
                                }
                            }
                        }
                    ]
                }
            },
            {
                "dataModelUpdate": {
                    "surfaceId": "weather-confirmation",
                    "path": "/",
                    "contents": [
                        {"key": "display_name", "valueString": display_name},
                        {"key": "location", "valueString": location},
                        {"key": "latitude", "valueNumber": latitude},
                        {"key": "longitude", "valueNumber": longitude},
                        {"key": "state_code", "valueString": state_code},
                        {
                            "key": "form",
                            "valueMap": [
                                {"key": "forecastSelected", "valueBoolean": True},  # Default to True for better UX
                                {"key": "alertsSelected", "valueBoolean": False}
                            ]
                        }
                    ]
                }
            }
        ]

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        query = ""
        ui_event_part = None
        action = None

        logger.info(
            f"--- Client requested extensions: {context.requested_extensions} ---"
        )
        use_ui = try_activate_a2ui_extension(context)

        # Determine which agent to use based on whether the a2ui extension is active.
        if use_ui:
            agent = self.ui_agent
            logger.info(
                "--- WEATHER_AGENT_EXECUTOR: A2UI extension is active. Using UI agent. ---"
            )
        else:
            agent = self.text_agent
            logger.info(
                "--- WEATHER_AGENT_EXECUTOR: A2UI extension is not active. Using text agent. ---"
            )

        if context.message and context.message.parts:
            logger.info(
                f"--- WEATHER_AGENT_EXECUTOR: Processing {len(context.message.parts)} message parts ---"
            )
            for i, part in enumerate(context.message.parts):
                if isinstance(part.root, DataPart):
                    if "userAction" in part.root.data:
                        logger.info(f"  Part {i}: Found a2ui UI ClientEvent payload.")
                        ui_event_part = part.root.data["userAction"]
                    else:
                        logger.info(f"  Part {i}: DataPart (data: {part.root.data})")
                elif isinstance(part.root, TextPart):
                    logger.info(f"  Part {i}: TextPart (text: {part.root.text})")
                else:
                    logger.info(f"  Part {i}: Unknown part type ({type(part.root)})")

        if ui_event_part:
            logger.info(f"╔════════════════════════════════════════════════════════╗")
            logger.info(f"║ RECEIVED A2UI CLIENT EVENT                             ║")
            logger.info(f"╠════════════════════════════════════════════════════════╣")
            logger.info(f"║ Full Event: {ui_event_part}")
            logger.info(f"╚════════════════════════════════════════════════════════╝")
            # Action can be in 'actionName' or 'name' field
            action = ui_event_part.get("actionName") or ui_event_part.get("name")
            ctx_raw = ui_event_part.get("context", {})

            logger.info(f">>> Action Name: {action}")
            logger.info(f">>> Context (raw): {ctx_raw}")

            # Convert context array to dict if needed
            if isinstance(ctx_raw, list):
                ctx = {item.get("key", ""): item.get("value", "") for item in ctx_raw if isinstance(item, dict)}
            else:
                ctx = ctx_raw if isinstance(ctx_raw, dict) else {}

            logger.info(f">>> Parsed context (dict): {ctx}")

            if action == "confirmAlerts":
                logger.info(f"🎯 CONFIRM ALERTS ACTION DETECTED!")
                location = ctx.get("location", "Unknown Location")
                latitude = ctx.get("latitude", 0.0)
                longitude = ctx.get("longitude", 0.0)
                display_name = ctx.get("display_name", location)
                state_code = ctx.get("state_code", "")

                # Extract checkbox values from context - handle both boolean and path objects
                forecast_selected_raw = ctx.get("forecastSelected", False)
                alerts_selected_raw = ctx.get("alertsSelected", False)

                logger.info(f"Raw checkbox values from context - forecastSelected: {forecast_selected_raw} (type: {type(forecast_selected_raw)}), alertsSelected: {alerts_selected_raw} (type: {type(alerts_selected_raw)})")

                # If values are dicts, they might be path objects or literal objects
                # Frontend should resolve paths, but handle both cases
                if isinstance(forecast_selected_raw, dict):
                    # Check if it's a literal boolean
                    if "literalBoolean" in forecast_selected_raw:
                        forecast_selected = forecast_selected_raw["literalBoolean"]
                    # If it's a path object, the frontend should have resolved it, but if not, we can't resolve it here
                    # So we'll default to False and log a warning
                    elif "path" in forecast_selected_raw:
                        logger.warning(f"Received unresolved path for forecastSelected: {forecast_selected_raw['path']}. Frontend should resolve paths before sending actions.")
                        forecast_selected = False  # Can't resolve path here, default to False
                    else:
                        forecast_selected = False
                elif isinstance(forecast_selected_raw, bool):
                    forecast_selected = forecast_selected_raw
                elif isinstance(forecast_selected_raw, str):
                    # String "true"/"false" or path string
                    forecast_selected = forecast_selected_raw.lower() in ["true", "1", "yes"]
                else:
                    forecast_selected = bool(forecast_selected_raw) if forecast_selected_raw not in [None, ""] else False

                if isinstance(alerts_selected_raw, dict):
                    if "literalBoolean" in alerts_selected_raw:
                        alerts_selected = alerts_selected_raw["literalBoolean"]
                    elif "path" in alerts_selected_raw:
                        logger.warning(f"Received unresolved path for alertsSelected: {alerts_selected_raw['path']}. Frontend should resolve paths before sending actions.")
                        alerts_selected = False
                    else:
                        alerts_selected = False
                elif isinstance(alerts_selected_raw, bool):
                    alerts_selected = alerts_selected_raw
                elif isinstance(alerts_selected_raw, str):
                    alerts_selected = alerts_selected_raw.lower() in ["true", "1", "yes"]
                else:
                    alerts_selected = bool(alerts_selected_raw) if alerts_selected_raw not in [None, ""] else False

                logger.info(f"Extracted checkbox values - forecast: {forecast_selected}, alerts: {alerts_selected}")

                # Build selected options list based on checkbox values
                selected_options = []
                if forecast_selected:
                    selected_options.append("forecast")
                if alerts_selected:
                    selected_options.append("alerts")

                # If no options selected, default to forecast (most common use case)
                if not selected_options:
                    logger.info("No options selected, defaulting to forecast")
                    selected_options = ["forecast"]
                    forecast_selected = True

                # Build query based on selected options - make it VERY explicit with full context
                options_text = ", ".join(selected_options)
                query = f"""=== THIS IS A CONFIRMATION MESSAGE - DO NOT CALL show_weather_confirmation() ===

PREVIOUS CONVERSATION CONTEXT:
- User asked: "What is the weather in {display_name}?"
- You called geocode_location("{display_name}") and got coordinates: lat={latitude}, lon={longitude}
- You called show_weather_confirmation() and the confirmation UI was shown to the user
- The user has NOW confirmed their selection

USER CONFIRMED WEATHER REQUEST:
Location: {display_name}
Coordinates: latitude={latitude}, longitude={longitude}  
State Code: {state_code}
Selected Options: {options_text}

CRITICAL INSTRUCTIONS - READ CAREFULLY:
1. DO NOT call show_weather_confirmation() - it was already called and the user has confirmed
2. DO NOT call geocode_location() - you already have the coordinates from before
3. IMMEDIATELY fetch weather data using these EXACT function calls based on selected options:
"""
                # Add specific function calls based on selected options
                if "forecast" in selected_options:
                    query += f"   - Call get_forecast({latitude}, {longitude})\n"
                if "alerts" in selected_options:
                    query += f"   - Call get_alerts(\"{state_code}\")\n"

                query += """4. Display the results using WEATHER_FORECAST_EXAMPLE or WEATHER_ALERTS_EXAMPLE templates

This is NOT a new weather query - this is the CONFIRMATION of your previous query. Fetch the data now."""

                logger.info(f"╔══════════════════════════════════════════════════════════╗")
                logger.info(f"║        CONFIRMATION MESSAGE TO LLM                       ║")
                logger.info(f"╠══════════════════════════════════════════════════════════╣")
                logger.info(f"║ Action: {action}")
                logger.info(f"║ Selected options: {selected_options}")
                logger.info(f"║ Forecast selected: {forecast_selected}")
                logger.info(f"║ Alerts selected: {alerts_selected}")
                logger.info(f"║ Location: {display_name}")
                logger.info(f"║ Coordinates: ({latitude}, {longitude})")
                logger.info(f"║ State Code: {state_code}")
                logger.info(f"╠══════════════════════════════════════════════════════════╣")
                logger.info(f"║ FULL MESSAGE TO LLM:")
                logger.info(f"╠══════════════════════════════════════════════════════════╣")
                logger.info(f"{query}")
                logger.info(f"╚══════════════════════════════════════════════════════════╝")

            elif action == "rejectAlerts":
                location = ctx.get("location", "Unknown Location")
                display_name = ctx.get("display_name", location)
                query = f"User rejected weather query for {display_name}. No weather data will be fetched."

            elif action == "confirm_weather_selection":
                # Legacy support for old action name
                location = ctx.get("location", "Unknown Location")
                latitude = ctx.get("latitude", 0.0)
                longitude = ctx.get("longitude", 0.0)
                state_code = ctx.get("state_code", "")
                selected_options = ctx.get("selected_options", [])

                # Build query based on selected options
                options_text = ", ".join(selected_options) if selected_options else "forecast, alerts"
                query = f"User confirmed weather query for {location} (lat: {latitude}, lon: {longitude}, state: {state_code}). Selected options: {options_text}. Please fetch the weather data."

            elif action == "toggle_option":
                # This is handled by the frontend, but we can log it
                logger.info(f"Option toggled: {ctx}")
                # Don't send query for toggle actions - just return early
                return

            else:
                query = f"User submitted an event: {action} with data: {ctx}"
        else:
            logger.info("No a2ui UI event part found. Falling back to text input.")
            query = context.get_user_input()
            logger.info(f"Text input received: '{query}'")

        # If no query was set, return early
        if not query:
            logger.warning("No query to process. Returning early.")
            return

        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        logger.info(f"--- WEATHER_AGENT_EXECUTOR: Sending query to LLM: '{query}' ---")
        logger.info(f"--- Using session_id (context_id): {task.context_id} to preserve conversation history ---")

        try:
            # Stream agent response and collect it
            # Using the same task.context_id ensures conversation history is preserved in the agent's session
            agent_response_content = None
            async for item in agent.stream(query, task.context_id):
                is_task_complete = item["is_task_complete"]
                if not is_task_complete:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(item["updates"], task.context_id, task.id),
                    )
                    continue

                agent_response_content = item["content"]
                break

            # After agent finishes, check if confirmation tool was called
            # We need to check the agent's session state
            if use_ui and agent_response_content:
                try:
                    # Get the agent's session to check for pending confirmation
                    agent_session = await agent._runner.session_service.get_session(
                        app_name=agent._agent.name,
                        user_id=agent._user_id,
                        session_id=task.context_id,
                    )

                    if agent_session and agent_session.state:
                        # Convert state to dict if needed
                        state_dict = dict(agent_session.state) if not isinstance(agent_session.state, dict) else agent_session.state

                        if state_dict.get("pending_weather_confirmation"):
                            confirmation_data = state_dict["pending_weather_confirmation"]
                            logger.info(f"--- Confirmation tool was called for: {confirmation_data.get('display_name', 'Unknown')} ---")

                            # Skip confirmation UI if weather data already fetched
                            if "temperature" in agent_response_content.lower() or "forecast" in agent_response_content.lower():
                                logger.warning(f"⚠️  Weather data already in response, skipping confirmation UI")
                                if isinstance(agent_session.state, dict):
                                    del agent_session.state["pending_weather_confirmation"]
                                else:
                                    agent_session.state = {k: v for k, v in state_dict.items() if k != "pending_weather_confirmation"}
                                # Continue to show weather data - don't return
                            else:
                                logger.info(f"--- Rendering confirmation UI ---")
                                if isinstance(agent_session.state, dict):
                                    del agent_session.state["pending_weather_confirmation"]
                                else:
                                    agent_session.state = {k: v for k, v in state_dict.items() if k != "pending_weather_confirmation"}

                                confirmation_ui = self._generate_confirmation_ui(
                                    location=confirmation_data["location"],
                                    latitude=confirmation_data["latitude"],
                                    longitude=confirmation_data["longitude"],
                                    display_name=confirmation_data["display_name"],
                                    state_code=confirmation_data["state_code"]
                                )

                                final_parts = []
                                text_message = f"What information would you like to get for {confirmation_data.get('display_name', confirmation_data.get('location', 'this location'))}?"
                                final_parts.append(Part(root=TextPart(text=text_message)))

                                for ui_message in confirmation_ui:
                                    final_parts.append(create_a2ui_part(ui_message))

                                await updater.update_status(
                                    TaskState.input_required,
                                    new_agent_parts_message(final_parts, task.context_id, task.id),
                                    final=False,
                                )
                                logger.info("--- Confirmation UI rendered, waiting for user confirmation ---")
                                return
                except Exception as e:
                    logger.error(f"Error checking for confirmation tool: {e}", exc_info=True)
                    # Continue with normal response processing

            # No confirmation pending - process normal agent response
            final_state = (
                    TaskState.completed
                    if action in ["confirmAlerts", "confirm_weather_selection", "rejectAlerts"]
                    else TaskState.input_required
                )

            if not agent_response_content:
                logger.warning("No agent response content received")
                error_message = "I'm sorry, I didn't receive a response. Please try again."
                await updater.update_status(
                    TaskState.completed,
                    new_agent_text_message(error_message, task.context_id, task.id),
                    final=True,
                )
                return

            logger.info(f"--- WEATHER_AGENT_EXECUTOR: Received content length: {len(agent_response_content) if agent_response_content else 0} ---")
            final_parts = []
            if "---a2ui_JSON---" in agent_response_content:
                logger.info("Splitting final response into text and UI parts.")
                text_content, json_string = agent_response_content.split("---a2ui_JSON---", 1)

                if text_content.strip():
                    final_parts.append(Part(root=TextPart(text=text_content.strip())))

                if json_string.strip():
                    try:
                        json_string_cleaned = (
                            json_string.strip().lstrip("```json").rstrip("```").strip()
                        )
                        json_data = json.loads(json_string_cleaned)

                        if isinstance(json_data, list):
                            logger.info(
                                f"Found {len(json_data)} messages. Creating individual DataParts."
                            )
                            for message in json_data:
                                final_parts.append(create_a2ui_part(message))
                        else:
                            logger.info(
                                "Received a single JSON object. Creating a DataPart."
                            )
                            final_parts.append(create_a2ui_part(json_data))

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse UI JSON: {e}")
                        final_parts.append(Part(root=TextPart(text=json_string)))
            else:
                final_parts.append(Part(root=TextPart(text=agent_response_content.strip())))

                logger.info("--- FINAL PARTS TO BE SENT ---")
                for i, part in enumerate(final_parts):
                    logger.info(f"  - Part {i}: Type = {type(part.root)}")
                    if isinstance(part.root, TextPart):
                        logger.info(f"    - Text: {part.root.text[:200]}...")
                    elif isinstance(part.root, DataPart):
                        logger.info(f"    - Data: {str(part.root.data)[:200]}...")
                logger.info("-----------------------------")

                await updater.update_status(
                    final_state,
                    new_agent_parts_message(final_parts, task.context_id, task.id),
                    final=(final_state == TaskState.completed),
                )
        except Exception as e:
            logger.error(f"--- WEATHER_AGENT_EXECUTOR: Error processing request: {e} ---", exc_info=True)
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Full traceback: {error_details}")
            error_message = f"I encountered an error while processing your request. Please try again. Error: {type(e).__name__}: {str(e)}"
            await updater.update_status(
                TaskState.completed,
                new_agent_text_message(error_message, task.context_id, task.id),
                final=True,
            )

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        raise ServerError(error=UnsupportedOperationError())

