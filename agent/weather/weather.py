from typing import Any
import json

import httpx

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("weather")

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


async def make_nominatim_request(url: str) -> dict[str, Any] | None:
    """Make a request to the Nominatim API with proper error handling."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


def format_alert(feature: dict) -> dict:
    """Format an alert feature into a structured dict."""
    props = feature["properties"]
    return {
        "event": props.get("event", "Unknown"),
        "area": props.get("areaDesc", "Unknown"),
        "severity": props.get("severity", "Unknown"),
        "description": props.get("description", "No description available"),
        "instructions": props.get("instruction", "No specific instructions provided"),
    }


@mcp.tool()
async def geocode_location(location: str) -> str:
    """Convert a location name (city, address, etc.) to latitude and longitude coordinates.
    Use this tool first when you need coordinates for a location name.
    
    Args:
        location: The location name, city, address, or place (e.g., "San Francisco", "New York, NY", "Paris, France")
    
    Returns:
        JSON string with latitude, longitude, and display name of the location
    """
    # OpenStreetMap Nominatim API endpoint
    base_url = "https://nominatim.openstreetmap.org/search"
    
    # Build the request URL with parameters
    params = {
        "q": location,
        "format": "json",
        "limit": 1,  # Only get the best match
        "addressdetails": 1
    }
    
    # Convert params to query string
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{base_url}?{query_string}"
    
    data = await make_nominatim_request(url)
    
    if not data or len(data) == 0:
        return json.dumps({
            "error": f"Could not find location: {location}. Please try a different location name or be more specific."
        })
    
    # Get the first (best) result
    result = data[0]
    
    return json.dumps({
        "latitude": float(result["lat"]),
        "longitude": float(result["lon"]),
        "display_name": result.get("display_name", location),
        "location_type": result.get("type", "unknown"),
        "importance": result.get("importance", 0)
    })


@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state. Returns JSON data.

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return json.dumps({"error": "Unable to fetch alerts or no alerts found."})

    if not data["features"]:
        return json.dumps({"message": "No active alerts for this state."})

    alerts = [format_alert(feature) for feature in data["features"]]
    return json.dumps({"alerts": alerts, "count": len(alerts)})


@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a location. Returns JSON data.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
    """
    # Round coordinates to 4 decimal places (NWS API is sensitive)
    lat = round(latitude, 4)
    lon = round(longitude, 4)
    
    # First get the forecast grid endpoint
    points_url = f"{NWS_API_BASE}/points/{lat},{lon}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        return json.dumps({"error": "Unable to fetch forecast data for this location."})

    # Extract location information from points data
    city = points_data["properties"].get("relativeLocation", {}).get("properties", {}).get("city", "")
    state = points_data["properties"].get("relativeLocation", {}).get("properties", {}).get("state", "")
    location_name = f"{city}, {state}" if city and state else f"{latitude}, {longitude}"

    # Get the forecast URL from the points response
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        return json.dumps({"error": "Unable to fetch detailed forecast."})

    # Format the periods into structured JSON data
    periods = forecast_data["properties"]["periods"]
    
    # Extract current weather from first period
    current = periods[0] if periods else None
    if not current:
        return json.dumps({"error": "No forecast data available."})
    
    # NWS provides temperature in Fahrenheit
    temp_f = current["temperature"]
    temp_c = round((temp_f - 32) * 5 / 9, 1)
    
    # Extract conditions from the detailed forecast
    detailed = current["detailedForecast"].lower()
    conditions = "clear"
    if "rain" in detailed or "shower" in detailed:
        conditions = "rain"
    elif "cloud" in detailed or "overcast" in detailed:
        conditions = "cloudy"
    elif "snow" in detailed:
        conditions = "snow"
    elif "storm" in detailed or "thunder" in detailed:
        conditions = "storm"
    elif "sunny" in detailed or "clear" in detailed:
        conditions = "clear"
    
    # Extract wind speed (just the number)
    wind_speed = 0
    wind_text = current["windSpeed"]
    import re
    wind_match = re.search(r'(\d+)', wind_text)
    if wind_match:
        wind_speed = int(wind_match.group(1))
    
    result = {
        "temperature": temp_c, # Send Celsius as primary to match reference
        "temperature_f": temp_f,
        "conditions": conditions,
        "humidity": 0,
        "windSpeed": wind_speed,
        "windSpeedText": wind_text,
        "windDirection": current["windDirection"],
        "feelsLike": temp_c,
        "location": location_name,
        "periods": [
            {
                "name": p["name"],
                "temperature": p["temperature"],
                "temperatureUnit": p["temperatureUnit"],
                "windSpeed": p["windSpeed"],
                "windDirection": p["windDirection"],
                "forecast": p["detailedForecast"],
                "conditions": conditions,
            }
            for p in periods[:5]
        ]
    }
    
    return json.dumps(result)


def main():
    # Initialize and run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

