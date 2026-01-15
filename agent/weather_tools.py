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
from typing import Any

from google.adk.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)


def show_weather_confirmation(
    location: str,
    latitude: float,
    longitude: float,
    display_name: str,
    state_code: str,
    tool_context: ToolContext,
) -> str:
    """
    Show a confirmation UI to the user for weather queries. 
    This tool should be called after geocoding a location to get user confirmation 
    on what weather information they want (forecast and/or alerts).
    
    Args:
        location: The location name the user asked about
        latitude: Latitude coordinate from geocoding
        longitude: Longitude coordinate from geocoding
        display_name: Full display name from geocoding
        state_code: US state code for alerts (e.g., 'CA', 'NY')
        tool_context: Tool context for accessing session state
    
    Returns:
        A JSON string containing the confirmation UI JSON that should be rendered immediately.
        The executor will detect this and render the UI, then wait for user confirmation.
    """
    logger.info(f"--- TOOL CALLED: show_weather_confirmation ---")
    logger.info(f"  - Location: {location}")
    logger.info(f"  - Display Name: {display_name}")
    logger.info(f"  - Coordinates: ({latitude}, {longitude})")
    logger.info(f"  - State Code: {state_code}")
    
    # Store confirmation request in session state so executor can handle it
    # tool_context.state is a dict-like object that can be accessed with .get() and set with direct assignment
    try:
        if tool_context.state is None:
            tool_context.state = {}
        
        # Set the pending confirmation in state
        tool_context.state["pending_weather_confirmation"] = {
            "location": location,
            "latitude": latitude,
            "longitude": longitude,
            "display_name": display_name,
            "state_code": state_code,
        }
        logger.info("--- Stored pending confirmation in session state ---")
    except Exception as e:
        logger.error(f"Error storing confirmation in session state: {e}", exc_info=True)
        # Continue anyway - the return value will still indicate confirmation is needed
    
    # Return a special marker that the executor will detect
    # The executor will render the actual UI
    return json.dumps({
        "_a2ui_render_confirmation": True,
        "location": location,
        "latitude": latitude,
        "longitude": longitude,
        "display_name": display_name,
        "state_code": state_code,
    })

