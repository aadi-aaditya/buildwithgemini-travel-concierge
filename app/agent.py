# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google.cloud import firestore, storage
from google import genai
from google.genai import types
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService

from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from app.a2ui_utils import a2ui_callback

load_dotenv()

PROJECT_ID = "qwiklabs-gcp-02-52babdffede5"
BUCKET_NAME = "travel-concierge-media-qwiklabs-gcp-02-52babdffede5"
MEMORY_BANK_ID = "6386112517948571648"

# Load Agent Engine resource name from deployment_metadata.json if available
METADATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "deployment_metadata.json")
agent_engine_resource_name = None
if os.path.exists(METADATA_PATH):
    try:
        with open(METADATA_PATH, "r") as f:
            metadata = json.load(f)
            agent_engine_resource_name = metadata.get("remote_agent_runtime_id")
    except Exception as e:
        print(f"Warning: Could not read deployment_metadata.json: {e}")

code_executor = (
    AgentEngineSandboxCodeExecutor(agent_engine_resource_name=agent_engine_resource_name)
    if agent_engine_resource_name
    else AgentEngineSandboxCodeExecutor()
)


def memory_service_builder():
    """Builds a VertexAiMemoryBankService instance for deployed environments."""
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-central1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """Callback triggered after each agent turn to extract and store durable memories into Memory Bank."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def get_live_exchange_rates(from_currency: str = "USD") -> str:
    """Fetches real-time foreign exchange rates for a base currency from the Frankfurter public API.

    Args:
        from_currency: The 3-letter currency code to convert from (e.g. 'USD', 'EUR', 'GBP'). Defaults to 'USD'.

    Returns:
        A formatted string of current live exchange rates for major world currencies.
    """
    base = from_currency.upper().strip()
    api_endpoint = os.getenv("EXCHANGE_RATE_API_URL", f"https://api.frankfurter.app/latest?from={base}")
    try:
        req = urllib.request.Request(api_endpoint, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                rates = data.get("rates", {})
                date = data.get("date", "latest")
                targets = ["EUR", "JPY", "GBP", "CAD", "AUD", "CHF", "CNY", "MXN"]
                summary_rates = {k: rates[k] for k in targets if k in rates}
                return f"Live Exchange Rates as of {date} (Base: {base}): {summary_rates}"
            return f"Unable to fetch exchange rates (HTTP status {response.status})."
    except Exception as e:
        return f"Error fetching live exchange rates: {str(e)}"


def geocode_address(address: str) -> str:
    """Uses the Google Maps Geocoding API to convert an address or landmark into latitude and longitude coordinates.

    Args:
        address: The address, city, or landmark string to geocode (e.g. 'Kyoto, Japan' or 'Eiffel Tower, Paris').

    Returns:
        A formatted string containing the full name, formatted address, and geographical location coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    encoded_address = urllib.parse.quote_plus(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "OK" and data.get("results"):
                first = data["results"][0]
                formatted_addr = first.get("formatted_address", address)
                location = first.get("geometry", {}).get("location", {})
                lat = location.get("lat")
                lng = location.get("lng")
                return (
                    f"Geocoded Address: '{formatted_addr}'\n"
                    f"Location: (latitude: {lat}, longitude: {lng})"
                )
            return f"Geocoding failed with status: {data.get('status', 'UNKNOWN')}"
    except Exception as e:
        return f"Error executing Geocoding request: {str(e)}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 1000.0,
) -> str:
    """Uses the Google Maps Places API (New) searchNearby endpoint to find nearby places of a given type.

    Args:
        latitude: Latitude coordinate for the search center.
        longitude: Longitude coordinate for the search center.
        place_type: Type of place to search for (e.g. 'restaurant', 'tourist_attraction', 'lodging', 'museum', 'cafe'). Defaults to 'tourist_attraction'.
        radius_meters: Search radius in meters (e.g. 500.0 to 5000.0). Defaults to 1000.0.

    Returns:
        A formatted string listing nearby places with their name, formatted address, and location coordinates.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius_meters),
            }
        },
    }

    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                places = data.get("places", [])
                if not places:
                    return f"No nearby places found of type '{place_type}' within {radius_meters}m."
                results = []
                for p in places:
                    name = p.get("displayName", {}).get("text", "Unknown")
                    addr = p.get("formattedAddress", "N/A")
                    loc = p.get("location", {})
                    results.append(
                        f"- Name: {name}\n"
                        f"  Address: {addr}\n"
                        f"  Location: (latitude: {loc.get('latitude')}, longitude: {loc.get('longitude')})"
                    )
                return f"Found {len(results)} nearby '{place_type}' places:\n" + "\n".join(results)
            return f"Places API request failed with HTTP status {response.status}."
    except Exception as e:
        return f"Error executing Places searchNearby request: {str(e)}"


def generate_destination_postcard(
    prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates a visual travel postcard image for a destination using Gemini image generation, saves it as an artifact, and uploads it to Cloud Storage.

    Args:
        prompt: A description of the destination landscape or scene to generate (e.g. 'Sunset over Kyoto bamboo forest', 'Amalfi coast cliffside villa').

    Returns:
        The public HTTPS URL of the generated image stored in Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=f"Generate a scenic travel postcard image of: {prompt}",
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )

    image_bytes = None
    mime_type = "image/jpeg"
    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                image_bytes = part.inline_data.data
                if part.inline_data.mime_type:
                    mime_type = part.inline_data.mime_type
                break

    if not image_bytes:
        return "Failed to generate image bytes from model response."

    filename = f"postcard_{uuid.uuid4().hex[:8]}.jpg"

    # 1. Save artifact for ADK Playground / UI Artifacts panel
    artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload in-memory bytes directly to public Cloud Storage bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    return public_url


def generate_destination_video(
    prompt: str,
    tool_context: ToolContext,
) -> str:
    """Generates a short travel video snippet for a destination using Gemini Omni video generation, saves it as an artifact, and uploads it to Cloud Storage.

    Args:
        prompt: A description of the destination scene or attraction to generate as a video (e.g. 'A scenic aerial flyover of ocean waves on a Hawaiian beach at sunset').

    Returns:
        The public HTTPS URL of the generated video stored in Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    
    video_bytes = None
    mime_type = "video/mp4"

    try:
        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"Generate a scenic travel video snippet of: {prompt}",
        )
        if hasattr(interaction, "output_video") and interaction.output_video:
            data = interaction.output_video.data
            if isinstance(data, str):
                video_bytes = base64.b64decode(data)
            elif isinstance(data, bytes):
                video_bytes = data
            if hasattr(interaction.output_video, "mime_type") and interaction.output_video.mime_type:
                mime_type = interaction.output_video.mime_type
    except Exception as e:
        return f"Error generating video with gemini-omni-flash-preview: {str(e)}"

    if not video_bytes:
        return f"Failed to generate video bytes for prompt: '{prompt}'."

    filename = f"video_{uuid.uuid4().hex[:8]}.mp4"

    # 1. Save artifact for ADK Playground / UI Artifacts panel
    artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
    tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload in-memory bytes directly to public Cloud Storage bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    return public_url


def search_destinations(
    query: str = "",
    category: str = "",
    min_rating: float = 0.0,
    max_price: float = 10000.0,
) -> str:
    """Searches the Firestore travel catalog for destinations matching given criteria.

    Args:
        query: Optional free-text search query term to match against destination name, city, country, or description (e.g. 'Paris', 'Japan', 'temple').
        category: Optional category filter (e.g. 'Culture', 'Beach', 'Adventure', 'Luxury').
        min_rating: Optional minimum rating filter (e.g. 4.5).
        max_price: Optional maximum price per night in USD (e.g. 300.0).

    Returns:
        A string listing matching travel destinations from Firestore.
    """
    db = firestore.Client(project=PROJECT_ID)
    collection = db.collection("destinations")
    docs = collection.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        if query:
            q = query.lower()
            text = f"{data.get('name', '')} {data.get('city', '')} {data.get('country', '')} {data.get('description', '')}".lower()
            if q not in text:
                continue
        if category and category.lower() not in data.get("category", "").lower():
            continue
        if min_rating > 0 and data.get("rating", 0) < min_rating:
            continue
        if max_price < 10000.0 and data.get("price_per_night", float("inf")) > max_price:
            continue
        results.append(data)

    if not results:
        return "No destinations found matching your criteria."

    return str(results)


def add_destination(
    destination_id: str,
    name: str,
    city: str,
    country: str,
    category: str,
    description: str,
    price_per_night: float,
    rating: float,
    highlights: str = "",
) -> str:
    """Adds a new travel destination to the Firestore travel catalog.

    Args:
        destination_id: A unique kebab-case ID for the destination (e.g. 'tokyo-japan').
        name: Name of the destination package or resort.
        city: City where the destination is located.
        country: Country where the destination is located.
        category: Category of travel (e.g. 'Culture', 'Beach', 'Adventure', 'Luxury').
        description: A brief summary description of the destination.
        price_per_night: Price per night in USD.
        rating: Customer rating from 1.0 to 5.0.
        highlights: Optional comma-separated highlights or attraction points.

    Returns:
        A confirmation message indicating successful addition to Firestore.
    """
    db = firestore.Client(project=PROJECT_ID)
    doc_ref = db.collection("destinations").document(destination_id)

    highlights_list = [h.strip() for h in highlights.split(",")] if highlights else []

    item = {
        "destination_id": destination_id,
        "name": name,
        "city": city,
        "country": country,
        "category": category,
        "description": description,
        "price_per_night": float(price_per_night),
        "rating": float(rating),
        "highlights": highlights_list,
    }
    doc_ref.set(item)
    return f"Successfully added destination '{name}' ({destination_id}) to Firestore."


def calculate_trip_budget(
    price_per_night: float,
    num_days: int,
    num_travelers: int = 1,
    currency: str = "USD",
    daily_expenses_per_person: float = 100.0,
) -> str:
    """Calculates an estimated total budget breakdown for a trip.

    Args:
        price_per_night: Lodging price per night in USD.
        num_days: Number of days/nights for the trip duration.
        num_travelers: Number of travelers. Defaults to 1.
        currency: Preferred currency code for conversion (e.g. 'USD', 'EUR', 'GBP', 'CAD'). Defaults to 'USD'.
        daily_expenses_per_person: Estimated daily budget per person for meals/activities in USD. Defaults to 100.0.

    Returns:
        A string summarizing the itemized trip budget breakdown and total estimated cost.
    """
    lodging_total = price_per_night * num_days
    expenses_total = daily_expenses_per_person * num_days * num_travelers
    subtotal = lodging_total + expenses_total
    taxes_and_fees = round(subtotal * 0.12, 2)
    total_usd = round(subtotal + taxes_and_fees, 2)
    per_person_usd = round(total_usd / max(num_travelers, 1), 2)

    rates = {
        "USD": 1.0,
        "EUR": 0.92,
        "GBP": 0.79,
        "JPY": 155.0,
        "CAD": 1.35,
        "AUD": 1.50,
    }
    curr = currency.upper()
    rate = rates.get(curr, 1.0)
    total_converted = round(total_usd * rate, 2)

    return (
        f"Trip Budget Breakdown ({num_days} days, {num_travelers} traveler(s)):\n"
        f"- Lodging Total: ${lodging_total:.2f} USD\n"
        f"- Estimated Meals & Activities: ${expenses_total:.2f} USD\n"
        f"- Taxes & Fees (12%): ${taxes_and_fees:.2f} USD\n"
        f"- Total Estimated Cost: ${total_usd:.2f} USD (~{total_converted:,.2f} {curr})\n"
        f"- Cost Per Person: ${per_person_usd:.2f} USD"
    )


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an expert Travel Concierge assistant. You help users discover and manage travel destinations. "
        "Pay special attention to and remember all user dietary restrictions, health requirements, and allergies (e.g. peanuts, gluten, dairy, shellfish) stated across sessions, and actively filter, account for, or warn about them when suggesting places, restaurants, or travel plans. "
        "Use preloaded memories from previous conversations to personalize your responses. "
        "Use generate_destination_postcard to generate a visual postcard image for any destination, "
        "geocode_address to turn an address or city into lat/lng coordinates, "
        "find_nearby_places to search for nearby attractions/restaurants/lodging, "
        "search_destinations to look up available travel packages/destinations in the database, "
        "add_destination to register new travel locations, get_live_exchange_rates to fetch live currency conversion rates, "
        "and calculate_trip_budget to compute trip costs. You can also write and execute Python code in a safe sandbox for complex math or data processing. "
        "You can also answer questions about weather and time."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        get_weather,
        get_current_time,
        get_live_exchange_rates,
        geocode_address,
        find_nearby_places,
        generate_destination_postcard,
        generate_destination_video,
        search_destinations,
        add_destination,
        calculate_trip_budget,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
    code_executor=code_executor,
)

app = App(
    root_agent=root_agent,
    name="app",
)
