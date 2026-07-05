from __future__ import annotations

import httpx


NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_HEADERS = {"User-Agent": "AI-Traffic-Route-Finder/1.0 (demo project)"}
PHOTON_SEARCH_URL = "https://photon.komoot.io/api/"
BROWSER_HEADERS = {"User-Agent": "AI-Traffic-Route-Finder/1.0 demo@example.com"}

LOCAL_BANGLADESH_PLACES = [
    {"name": "Dhaka, Bangladesh", "lat": 23.8103, "lng": 90.4125, "aliases": ["dhaka", "dacca"]},
    {"name": "Gulshan 1, Dhaka, Bangladesh", "lat": 23.7806, "lng": 90.4193, "aliases": ["gulshan", "gulshan 1"]},
    {"name": "Gulshan 2, Dhaka, Bangladesh", "lat": 23.7948, "lng": 90.4143, "aliases": ["gulshan 2"]},
    {"name": "Banani, Dhaka, Bangladesh", "lat": 23.7937, "lng": 90.4043, "aliases": ["banani"]},
    {"name": "Bashundhara Residential Area, Dhaka, Bangladesh", "lat": 23.8195, "lng": 90.4486, "aliases": ["bashundhara", "bashundhara r/a", "bashundhara residential"]},
    {"name": "Badda, Dhaka, Bangladesh", "lat": 23.7804, "lng": 90.4266, "aliases": ["badda", "uttar badda", "middle badda"]},
    {"name": "Rampura, Dhaka, Bangladesh", "lat": 23.7639, "lng": 90.4217, "aliases": ["rampura"]},
    {"name": "Mohakhali, Dhaka, Bangladesh", "lat": 23.7797, "lng": 90.4054, "aliases": ["mohakhali", "mohakali"]},
    {"name": "Tejgaon, Dhaka, Bangladesh", "lat": 23.7644, "lng": 90.3938, "aliases": ["tejgaon"]},
    {"name": "Farmgate, Dhaka, Bangladesh", "lat": 23.7561, "lng": 90.3890, "aliases": ["farmgate", "farm gate"]},
    {"name": "Uttara, Dhaka, Bangladesh", "lat": 23.8759, "lng": 90.3795, "aliases": ["uttara", "uttara dhaka"]},
    {"name": "Uttara Sector 10, Dhaka, Bangladesh", "lat": 23.8796, "lng": 90.3886, "aliases": ["uttara sector 10", "sector 10 uttara"]},
    {"name": "Tongi, Gazipur, Bangladesh", "lat": 23.8915, "lng": 90.4023, "aliases": ["tongi"]},
    {"name": "Hazrat Shahjalal International Airport, Dhaka, Bangladesh", "lat": 23.8430, "lng": 90.3978, "aliases": ["airport", "dhaka airport"]},
    {"name": "Mirpur 1, Dhaka, Bangladesh", "lat": 23.8050, "lng": 90.3680, "aliases": ["mirpur 1", "mirpur-1", "mipur 1", "mipur-1"]},
    {"name": "Mirpur 10, Dhaka, Bangladesh", "lat": 23.8067, "lng": 90.3686, "aliases": ["mirpur 10", "mirpur-10", "mipur 10"]},
    {"name": "Mirpur 12, Dhaka, Bangladesh", "lat": 23.8277, "lng": 90.3653, "aliases": ["mirpur 12", "mirpur-12", "pallabi"]},
    {"name": "Mirpur, Dhaka, Bangladesh", "lat": 23.8223, "lng": 90.3654, "aliases": ["mirpur", "mipur"]},
    {"name": "Mohammadpur, Dhaka, Bangladesh", "lat": 23.7658, "lng": 90.3589, "aliases": ["mohammadpur", "mohammedpur"]},
    {"name": "Dhanmondi 32, Dhaka, Bangladesh", "lat": 23.7516, "lng": 90.3776, "aliases": ["dhanmondi", "dhanmondi 32"]},
    {"name": "New Market, Dhaka, Bangladesh", "lat": 23.7332, "lng": 90.3838, "aliases": ["new market", "newmarket"]},
    {"name": "Azimpur, Dhaka, Bangladesh", "lat": 23.7298, "lng": 90.3854, "aliases": ["azimpur"]},
    {"name": "Lalbagh, Dhaka, Bangladesh", "lat": 23.7189, "lng": 90.3882, "aliases": ["lalbagh"]},
    {"name": "Shahbagh, Dhaka, Bangladesh", "lat": 23.7383, "lng": 90.3956, "aliases": ["shahbagh"]},
    {"name": "Motijheel, Dhaka, Bangladesh", "lat": 23.7330, "lng": 90.4172, "aliases": ["motijheel"]},
    {"name": "Paltan, Dhaka, Bangladesh", "lat": 23.7363, "lng": 90.4108, "aliases": ["paltan"]},
    {"name": "Wari, Dhaka, Bangladesh", "lat": 23.7115, "lng": 90.4124, "aliases": ["wari"]},
    {"name": "Jatrabari, Dhaka, Bangladesh", "lat": 23.7104, "lng": 90.4349, "aliases": ["jatrabari"]},
    {"name": "Khilgaon, Dhaka, Bangladesh", "lat": 23.7509, "lng": 90.4253, "aliases": ["khilgaon"]},
    {"name": "Malibagh, Dhaka, Bangladesh", "lat": 23.7505, "lng": 90.4127, "aliases": ["malibagh"]},
    {"name": "Khilkhet, Dhaka, Bangladesh", "lat": 23.8294, "lng": 90.4262, "aliases": ["khilkhet"]},
    {"name": "Savar, Dhaka, Bangladesh", "lat": 23.8583, "lng": 90.2667, "aliases": ["savar"]},
    {"name": "Gazipur, Bangladesh", "lat": 23.9999, "lng": 90.4203, "aliases": ["gazipur", "gajipur"]},
    {"name": "Chandra, Gazipur, Bangladesh", "lat": 24.0470, "lng": 90.2382, "aliases": ["chandra"]},
    {"name": "Narayanganj, Bangladesh", "lat": 23.6238, "lng": 90.5000, "aliases": ["narayanganj"]},
    {"name": "Kanchpur, Narayanganj, Bangladesh", "lat": 23.7054, "lng": 90.5248, "aliases": ["kanchpur"]},
    {"name": "Mawa, Munshiganj, Bangladesh", "lat": 23.4742, "lng": 90.2615, "aliases": ["mawa"]},
    {"name": "Cumilla Kandirpar, Cumilla, Bangladesh", "lat": 23.4619, "lng": 91.1850, "aliases": ["cumilla", "comilla", "kandirpar"]},
    {"name": "Feni, Bangladesh", "lat": 23.0159, "lng": 91.3976, "aliases": ["feni"]},
    {"name": "Chattogram, Bangladesh", "lat": 22.3569, "lng": 91.7832, "aliases": ["chattogram", "chittagong"]},
    {"name": "Chattogram City Gate, Bangladesh", "lat": 22.3676, "lng": 91.7827, "aliases": ["chattogram city gate", "chittagong city gate"]},
    {"name": "Cox's Bazar, Bangladesh", "lat": 21.4272, "lng": 92.0058, "aliases": ["cox bazar", "coxs bazar", "cox's bazar"]},
    {"name": "Sylhet Zindabazar, Sylhet, Bangladesh", "lat": 24.8949, "lng": 91.8687, "aliases": ["sylhet", "zindabazar"]},
    {"name": "Rajshahi Shaheb Bazar, Rajshahi, Bangladesh", "lat": 24.3745, "lng": 88.6042, "aliases": ["rajshahi", "shaheb bazar"]},
    {"name": "Khulna, Bangladesh", "lat": 22.8456, "lng": 89.5403, "aliases": ["khulna"]},
    {"name": "Barishal, Bangladesh", "lat": 22.7010, "lng": 90.3535, "aliases": ["barisal", "barishal"]},
    {"name": "Rangpur, Bangladesh", "lat": 25.7439, "lng": 89.2752, "aliases": ["rangpur"]},
    {"name": "Mymensingh, Bangladesh", "lat": 24.7471, "lng": 90.4203, "aliases": ["mymensingh"]},
    {"name": "Jashore, Bangladesh", "lat": 23.1667, "lng": 89.2167, "aliases": ["jashore", "jessore"]},
]


def _normalize(value: str) -> str:
    return " ".join(
        value.lower()
        .replace("-", " ")
        .replace(",", " ")
        .replace("'", "")
        .split()
    )


def _local_place_matches(query: str, limit: int) -> list[dict]:
    normalized_query = _normalize(query)
    if len(normalized_query) < 2:
        return []

    ranked = []
    for place in LOCAL_BANGLADESH_PLACES:
        names = [place["name"], *place["aliases"]]
        normalized_names = [_normalize(name) for name in names]
        if any(name == normalized_query for name in normalized_names):
            score = 0
        elif any(name.startswith(normalized_query) for name in normalized_names):
            score = 1
        elif any(normalized_query in name for name in normalized_names):
            score = 2
        elif any(normalized_query in name or name in normalized_query for name in normalized_names):
            score = 3
        else:
            continue
        ranked.append((score, place))

    ranked.sort(key=lambda item: (item[0], item[1]["name"]))
    return [
        {
            "name": place["name"],
            "lat": place["lat"],
            "lng": place["lng"],
            "place_id": f"local-{_normalize(place['name']).replace(' ', '-')}",
        }
        for _, place in ranked[: max(1, min(limit, 10))]
    ]


def _dedupe_results(results: list[dict], limit: int) -> list[dict]:
    seen = set()
    unique = []
    for item in results:
        key = (
            round(float(item.get("lat", 0)), 5),
            round(float(item.get("lng", 0)), 5),
            _normalize(item.get("name", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= max(1, min(limit, 10)):
            break
    return unique


class GeocodeService:
    async def search(self, query: str, limit: int = 6) -> list[dict]:
        if not query or len(query.strip()) < 2:
            return []

        clean_query = query.strip()
        local_matches = _local_place_matches(clean_query, limit)
        external_results = []

        photon_params = {
            "q": f"{clean_query}, Bangladesh",
            "limit": max(1, min(limit, 10)),
            "bbox": "88.0,20.4,92.8,26.8",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(PHOTON_SEARCH_URL, params=photon_params, headers=BROWSER_HEADERS)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            payload = {}

        for item in payload.get("features", []):
            try:
                properties = item.get("properties", {})
                coordinates = item["geometry"]["coordinates"]
                name_parts = [
                    properties.get("name"),
                    properties.get("street"),
                    properties.get("city") or properties.get("county") or properties.get("state"),
                    properties.get("country"),
                ]
                name = ", ".join(dict.fromkeys(part for part in name_parts if part))
                if not name:
                    name = properties.get("osm_key", "Bangladesh place")
                external_results.append(
                    {
                        "name": name,
                        "place_id": properties.get("osm_id"),
                        "lat": float(coordinates[1]),
                        "lng": float(coordinates[0]),
                    }
                )
            except Exception:
                continue

        if external_results:
            return _dedupe_results([*local_matches, *external_results], limit)

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
                return local_matches

        for item in data:
            try:
                external_results.append(
                    {
                        "name": item.get("display_name", "Unknown place"),
                        "lat": float(item["lat"]),
                        "lng": float(item["lon"]),
                    }
                )
            except Exception:
                continue
        if external_results:
            return _dedupe_results([*local_matches, *external_results], limit)
        return local_matches

    async def reverse(self, lat: float, lng: float) -> dict | None:
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
