import math
import os

import httpx


ROUTES_MATRIX_URL = (
    "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
)


class RoutesServiceError(Exception):
    pass


def _duration_to_seconds(duration: str) -> float:
    try:
        return float(duration.removesuffix("s"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RoutesServiceError(
            "Google returned an invalid route duration."
        ) from exc


def calculate_walking_routes(
    client_latitude: float,
    client_longitude: float,
    barbers: list[dict],
) -> list[dict]:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    if not api_key:
        raise RoutesServiceError(
            "GOOGLE_MAPS_API_KEY is not configured."
        )

    if not -90 <= client_latitude <= 90:
        raise RoutesServiceError("Invalid client latitude.")

    if not -180 <= client_longitude <= 180:
        raise RoutesServiceError("Invalid client longitude.")

    valid_barbers = []

    for barber in barbers:
        latitude = barber.get("latitude")
        longitude = barber.get("longitude")

        if latitude is None or longitude is None:
            continue

        if not -90 <= latitude <= 90:
            continue

        if not -180 <= longitude <= 180:
            continue

        valid_barbers.append(barber)

    if not valid_barbers:
        return []

    request_body = {
        "origins": [
            {
                "waypoint": {
                    "location": {
                        "latLng": {
                            "latitude": client_latitude,
                            "longitude": client_longitude,
                        }
                    }
                }
            }
        ],
        "destinations": [
            {
                "waypoint": {
                    "location": {
                        "latLng": {
                            "latitude": barber["latitude"],
                            "longitude": barber["longitude"],
                        }
                    }
                }
            }
            for barber in valid_barbers
        ],
        "travelMode": "WALK",
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "originIndex,destinationIndex,status,condition,"
            "distanceMeters,duration"
        ),
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                ROUTES_MATRIX_URL,
                json=request_body,
                headers=headers,
            )
            response.raise_for_status()

    except httpx.HTTPStatusError as exc:
        raise RoutesServiceError(
            "Google Routes rejected the route request."
        ) from exc

    except httpx.RequestError as exc:
        raise RoutesServiceError(
            "Google Routes is temporarily unavailable."
        ) from exc

    route_elements = response.json()

    if not isinstance(route_elements, list):
        raise RoutesServiceError(
            "Google returned an invalid route response."
        )

    routes = []

    for element in route_elements:
        destination_index = element.get("destinationIndex")

        if not isinstance(destination_index, int):
            continue

        if destination_index >= len(valid_barbers):
            continue

        status = element.get("status") or {}

        if status.get("code", 0) != 0:
            continue

        if element.get("condition") != "ROUTE_EXISTS":
            continue

        distance_meters = element.get("distanceMeters")
        duration = element.get("duration")

        if distance_meters is None or duration is None:
            continue

        duration_seconds = _duration_to_seconds(duration)
        barber = valid_barbers[destination_index]

        routes.append(
            {
                "barber_id": barber["barber_id"],
                "distance_meters": distance_meters,
                "distance_km": round(distance_meters / 1000, 2),
                "duration_seconds": duration_seconds,
                "walking_minutes": math.ceil(duration_seconds / 60),
            }
        )

    routes.sort(
        key=lambda route: (
            route["duration_seconds"],
            route["distance_meters"],
        )
    )

    return routes