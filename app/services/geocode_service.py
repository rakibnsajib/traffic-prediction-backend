from __future__ import annotations

import os

import httpx


GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_GEOCODING_URL = os.getenv(
    "GOOGLE_GEOCODING_URL", "https://maps.googleapis.com/maps/api/geocode/json"
)
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_HEADERS = {"User-Agent": "AI-Traffic-Route-Finder/1.0 (demo project)"}


class GeocodeService:
    async def search(self, query: str, limit: int = 6) -> list[dict]:
        if not query or len(query.strip()) < 2:
            return []

        clean_query = query.strip()

        if GOOGLE_MAPS_API_KEY:
            params = {
                "address": clean_query,
                "components": "country:BD",
                "region": "bd",
                "key": GOOGLE_MAPS_API_KEY,
            }
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(GOOGLE_GEOCODING_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
            except Exception:
                payload = {}

            results = []
            if payload.get("status") == "OK":
                for item in payload.get("results", [])[: max(1, min(limit, 10))]:
                    try:
                        location = item["geometry"]["location"]
                        results.append(
                            {
                                "name": item.get("formatted_address", "Unknown place"),
                                "place_id": item.get("place_id"),
                                "lat": float(location["lat"]),
                                "lng": float(location["lng"]),
                            }
                        )
                    except Exception:
                        continue
                if results:
                    return results

        params = {
            "q": clean_query,
            "format": "jsonv2",
            "limit": max(1, min(limit, 10)),
            "addressdetails": 1,
            "countrycodes": "bd",
            "viewbox": "88.0,26.8,92.8,20.4",
            "bounded": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(NOMINATIM_SEARCH_URL, params=params, headers=NOMINATIM_HEADERS)
                response.raise_for_status()
                data = response.json()
        except Exception:
            data = []

        if not data:
            fallback_params = {
                "q": f"{clean_query}, Bangladesh",
                "format": "jsonv2",
                "limit": max(1, min(limit, 10)),
                "addressdetails": 1,
                "countrycodes": "bd",
            }
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(NOMINATIM_SEARCH_URL, params=fallback_params, headers=NOMINATIM_HEADERS)
                    response.raise_for_status()
                    data = response.json()
            except Exception:
                return []

        results = []
        for item in data:
            try:
                results.append(
                    {
                        "name": item.get("display_name", "Unknown place"),
                        "lat": float(item["lat"]),
                        "lng": float(item["lon"]),
                    }
                )
            except Exception:
                continue
        return results

    async def reverse(self, lat: float, lng: float) -> dict | None:
        if GOOGLE_MAPS_API_KEY:
            params = {
                "latlng": f"{lat},{lng}",
                "key": GOOGLE_MAPS_API_KEY,
            }
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(GOOGLE_GEOCODING_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
            except Exception:
                payload = {}

            if payload.get("status") == "OK" and payload.get("results"):
                item = payload["results"][0]
                name = item.get("formatted_address")
                if name:
                    return {
                        "name": name,
                        "display_name": name,
                        "place_id": item.get("place_id"),
                        "lat": lat,
                        "lng": lng,
                    }

        params = {
            "lat": lat,
            "lon": lng,
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": 18,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(NOMINATIM_REVERSE_URL, params=params, headers=NOMINATIM_HEADERS)
                response.raise_for_status()
                item = response.json()
        except Exception:
            return None

        address = item.get("address", {})
        name = (
            item.get("name")
            or address.get("building")
            or address.get("amenity")
            or address.get("road")
            or address.get("neighbourhood")
            or address.get("suburb")
            or address.get("city")
            or address.get("town")
            or address.get("village")
            or item.get("display_name")
        )
        if not name:
            return None

        return {
            "name": name,
            "display_name": item.get("display_name", name),
            "lat": lat,
            "lng": lng,
        }


geocode_service = GeocodeService()
