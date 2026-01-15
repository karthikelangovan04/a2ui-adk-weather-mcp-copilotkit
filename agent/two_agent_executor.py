"""
Two-Agent Executor for Weather Application

This executor coordinates between:
1. ConfirmationAgent - Handles location geocoding and HITL confirmation UI
2. WeatherAgent - Fetches and displays weather data

Flow:
User Query → ConfirmationAgent → (UI Confirmation) → WeatherAgent → Weather Display
"""

import logging
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    Part,
    Task,
    TaskState,
    DataPart,
    TextPart,
)
from a2a.utils import (
    new_agent_parts_message,
    new_agent_text_message,
)
from confirmation_agent import ConfirmationAgent
from weather_agent import WeatherAgent

logger = logging.getLogger(__name__)


def create_a2ui_part(json_data: dict) -> Part:
    """Create a Part with DataPart from A2UI JSON."""
    return Part(root=DataPart(data=json_data))


class TwoAgentExecutor(AgentExecutor):
    """Executor that coordinates between Confirmation and Weather agents."""
    
    def __init__(self, base_url: str = "http://localhost:10002"):
        self.confirmation_agent = ConfirmationAgent()
        self.weather_agent = WeatherAgent(base_url=base_url, use_ui=True)
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel the current execution."""
        logger.info("Cancelling task execution")
        # No cleanup needed for now
        pass
        
    def _generate_confirmation_ui(self, location: str, latitude: float, longitude: float, display_name: str, state_code: str) -> list:
        """Generate the static confirmation UI JSON."""
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
                                    "children": {"explicitList": ["title", "forecastCheck", "alertsCheck", "buttonRow"]},
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
                            "id": "buttonRow",
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
                                    "child": "rejectText",
                                    "primary": False,
                                    "action": {
                                        "name": "rejectWeather",
                                        "context": [
                                            {"key": "confirmed", "value": {"literalString": "rejected"}}
                                        ]
                                    }
                                }
                            }
                        },
                        {
                            "id": "rejectText",
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
                                    "child": "confirmText",
                                    "primary": True,
                                    "action": {
                                        "name": "confirmWeather",
                                        "context": [
                                            {"key": "confirmed", "value": {"literalString": "confirmed"}},
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
                            "id": "confirmText",
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
                                {"key": "forecastSelected", "valueBoolean": True},
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
        """Execute the two-agent workflow."""
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        
        # Check if A2UI extension is requested
        from a2ui.a2ui_extension import try_activate_a2ui_extension
        use_ui = try_activate_a2ui_extension(context)
        
        try:
            await updater.update_status(TaskState.working, None)
            
            # Extract user input and check for UI events
            query = ""
            ui_event_part = None
            action = None
            
            if context.message and context.message.parts:
                for part in context.message.parts:
                    if isinstance(part.root, DataPart):
                        if "userAction" in part.root.data:
                            ui_event_part = part.root.data["userAction"]
                    elif isinstance(part.root, TextPart):
                        query = part.root.text
            
            # Handle UI button clicks
            if ui_event_part:
                logger.info(f"📋 UI Event Received: {ui_event_part}")
                action = ui_event_part.get("actionName") or ui_event_part.get("name")
                ctx_raw = ui_event_part.get("context", {})
                
                # Convert context to dict if needed
                if isinstance(ctx_raw, list):
                    ctx = {item.get("key", ""): item.get("value", "") for item in ctx_raw if isinstance(item, dict)}
                else:
                    ctx = ctx_raw if isinstance(ctx_raw, dict) else {}
                
                if action == "confirmWeather":
                    logger.info(f"✅ User confirmed weather request!")
                    
                    # Extract data from context
                    location = ctx.get("location", "Unknown")
                    latitude = ctx.get("latitude", 0.0)
                    longitude = ctx.get("longitude", 0.0)
                    display_name = ctx.get("display_name", location)
                    state_code = ctx.get("state_code", "")
                    
                    # Extract checkbox values
                    forecast_selected_raw = ctx.get("forecastSelected", False)
                    alerts_selected_raw = ctx.get("alertsSelected", False)
                    
                    # Robust extraction of boolean values
                    forecast_selected = False
                    alerts_selected = False
                    
                    if isinstance(forecast_selected_raw, dict):
                        if "literalBoolean" in forecast_selected_raw:
                            forecast_selected = forecast_selected_raw["literalBoolean"]
                        elif "path" in forecast_selected_raw:
                            forecast_selected = True  # If path exists, consider it selected
                    elif isinstance(forecast_selected_raw, bool):
                        forecast_selected = forecast_selected_raw
                    elif isinstance(forecast_selected_raw, str):
                        forecast_selected = forecast_selected_raw.lower() == "true"
                    
                    if isinstance(alerts_selected_raw, dict):
                        if "literalBoolean" in alerts_selected_raw:
                            alerts_selected = alerts_selected_raw["literalBoolean"]
                        elif "path" in alerts_selected_raw:
                            alerts_selected = True
                    elif isinstance(alerts_selected_raw, bool):
                        alerts_selected = alerts_selected_raw
                    elif isinstance(alerts_selected_raw, str):
                        alerts_selected = alerts_selected_raw.lower() == "true"
                    
                    logger.info(f"Selections - Forecast: {forecast_selected}, Alerts: {alerts_selected}")
                    
                    # Build query for Weather Agent
                    selected_options = []
                    if forecast_selected:
                        selected_options.append("forecast")
                    if alerts_selected:
                        selected_options.append("alerts")
                    
                    if not selected_options:
                        selected_options = ["forecast"]  # Default to forecast
                    
                    options_text = " and ".join(selected_options)
                    
                    # Build explicit instructions for the WeatherAgent
                    query = f"""The user has confirmed they want weather information for {display_name}.
Location: {display_name}
Coordinates: latitude={latitude}, longitude={longitude}
State Code: {state_code}
User selected: {options_text}

YOU MUST:"""
                    
                    if "forecast" in selected_options:
                        query += f"\n1. Call get_forecast({latitude}, {longitude}) to get forecast data"
                    if "alerts" in selected_options:
                        query += f"\n2. Call get_alerts('{state_code}') to get weather alerts"
                    
                    query += f"\n\nThen display ALL the data you receive using A2UI JSON format with cards and widgets."
                    
                    logger.info(f"🌤️  Transferring to Weather Agent with query: {query}")
                    
                elif action == "rejectWeather":
                    logger.info(f"❌ User rejected weather request")
                    await updater.update_status(
                        TaskState.completed,
                        new_agent_text_message("No problem! Let me know if you change your mind.", context.task_id, context.task_id),
                        final=True,
                    )
                    return
                else:
                    query = f"User action: {action}"
            else:
                query = context.get_user_input()
            
            # Determine which agent to use
            agent = None
            if not ui_event_part:
                # New query - use Confirmation Agent
                logger.info(f"🔍 Using Confirmation Agent for query: {query}")
                agent = self.confirmation_agent
            else:
                # User confirmed - use Weather Agent
                logger.info(f"🌤️  Using Weather Agent")
                agent = self.weather_agent
            
            # Stream response from the appropriate agent
            agent_response_content = None
            async for item in agent.stream(query, context.task_id):
                is_task_complete = item["is_task_complete"]
                if not is_task_complete:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(item["updates"], context.task_id, context.task_id),
                    )
                    continue
                
                agent_response_content = item["content"]
                break
            
            # Check if confirmation tool was called
            if use_ui and agent_response_content and agent == self.confirmation_agent:
                try:
                    # Check agent session for pending confirmation
                    agent_session = await agent._runner.session_service.get_session(
                        app_name=agent._agent.name,
                        user_id=agent._user_id,
                        session_id=context.task_id,
                    )
                    
                    if agent_session and agent_session.state:
                        state_dict = dict(agent_session.state) if not isinstance(agent_session.state, dict) else agent_session.state
                        
                        if state_dict.get("pending_weather_confirmation"):
                            confirmation_data = state_dict["pending_weather_confirmation"]
                            logger.info(f"📍 Confirmation tool called, rendering UI for: {confirmation_data.get('display_name')}")
                            
                            # Clear from session
                            if isinstance(agent_session.state, dict):
                                del agent_session.state["pending_weather_confirmation"]
                            else:
                                agent_session.state = {k: v for k, v in state_dict.items() if k != "pending_weather_confirmation"}
                            
                            # Generate and render UI
                            confirmation_ui = self._generate_confirmation_ui(
                                location=confirmation_data["location"],
                                latitude=confirmation_data["latitude"],
                                longitude=confirmation_data["longitude"],
                                display_name=confirmation_data["display_name"],
                                state_code=confirmation_data["state_code"]
                            )
                            
                            final_parts = []
                            text_message = f"What information would you like to get for {confirmation_data.get('display_name')}?"
                            final_parts.append(Part(root=TextPart(text=text_message)))
                            
                            for ui_message in confirmation_ui:
                                final_parts.append(create_a2ui_part(ui_message))
                            
                            await updater.update_status(
                                TaskState.input_required,
                                new_agent_parts_message(final_parts, context.task_id, context.task_id),
                                final=False,
                            )
                            logger.info("✅ Confirmation UI rendered, waiting for user")
                            return
                except Exception as e:
                    logger.error(f"Error checking confirmation: {e}", exc_info=True)
            
            # Normal response handling
            if not agent_response_content:
                logger.warning("No response from agent")
                await updater.update_status(
                    TaskState.completed,
                    new_agent_text_message("Sorry, I didn't get a response. Please try again.", context.task_id, context.task_id),
                    final=True,
                )
                return
            
            # Check if response contains A2UI JSON
            final_parts = []
            if "---a2ui_JSON---" in agent_response_content:
                text_content, json_string = agent_response_content.split("---a2ui_JSON---", 1)
                
                if text_content.strip():
                    final_parts.append(Part(root=TextPart(text=text_content.strip())))
                
                if json_string.strip():
                    try:
                        import json
                        import re
                        # Remove markdown code block markers
                        json_string_cleaned = json_string.strip()
                        json_string_cleaned = re.sub(r'^```json\s*', '', json_string_cleaned)
                        json_string_cleaned = re.sub(r'\s*```$', '', json_string_cleaned)
                        json_string_cleaned = json_string_cleaned.strip()
                        
                        json_data = json.loads(json_string_cleaned)
                        
                        if isinstance(json_data, list):
                            for message in json_data:
                                final_parts.append(create_a2ui_part(message))
                        else:
                            final_parts.append(create_a2ui_part(json_data))
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse UI JSON: {e}")
                        logger.error(f"JSON string was: {json_string_cleaned[:200]}")
                        final_parts.append(Part(root=TextPart(text=json_string)))
            else:
                final_parts.append(Part(root=TextPart(text=agent_response_content.strip())))
            
            await updater.update_status(
                TaskState.completed,
                new_agent_parts_message(final_parts, context.task_id, context.task_id),
                final=True,
            )
            
        except Exception as e:
            logger.error(f"Executor error: {e}", exc_info=True)
            await updater.update_status(
                TaskState.completed,
                new_agent_text_message(f"Error: {str(e)}", context.task_id, context.task_id),
                final=True,
            )

