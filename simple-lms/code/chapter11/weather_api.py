import json
import os
import time

import redis
import requests


REDIS_URL = os.getenv("WEATHER_REDIS_URL", "redis://redis:6379/2")
WEATHER_API_BASE_URL = os.getenv("WEATHER_API_BASE_URL", "https://api.example.com/weather")
CACHE_TTL_SECONDS = 300


def get_redis_client():
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def build_cache_key(city):
    normalized_city = city.strip().lower().replace(" ", "_")
    return f"weather:{normalized_city}"


def _fetch_weather_from_api(city):
    """Simulasi API call yang lambat."""
    time.sleep(2)

    try:
        response = requests.get(f"{WEATHER_API_BASE_URL}/{city}", timeout=3)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        data = {
            "city": city,
            "temperature_c": 30,
            "condition": "Sunny",
            "provider": "mock-fallback",
        }

    return data


def get_weather(city):
    """Ambil data cuaca dengan cache Redis selama 5 menit."""
    redis_client = get_redis_client()
    cache_key = build_cache_key(city)

    cached_data = redis_client.get(cache_key)
    if cached_data:
        result = json.loads(cached_data)
        result["cache_status"] = "hit"
        return result

    result = _fetch_weather_from_api(city)
    redis_client.set(cache_key, json.dumps(result))
    redis_client.expire(cache_key, CACHE_TTL_SECONDS)
    result["cache_status"] = "miss"
    return result
