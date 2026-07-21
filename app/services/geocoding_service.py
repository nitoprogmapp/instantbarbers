import os

import httpx


GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
REQUEST_TIMEOUT_SECONDS = 10.0


class GeocodingError(Exception):
    pass


class AddressNotFoundError(GeocodingError):
    pass


class GeocodingServiceError(GeocodingError):
    pass


def geocode_address(address: str) -> tuple[float, float]:
    clean_address = address.strip()

    if not clean_address:
        raise AddressNotFoundError("Address is required.")

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    if not api_key:
        raise GeocodingServiceError(
            "Google Maps API key is not configured."
        )

    try:
        response = httpx.get(
            GEOCODING_URL,
            params={
                "address": clean_address,
                "key": api_key,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

    except httpx.TimeoutException as exc:
        raise GeocodingServiceError(
            "Google Maps did not respond in time."
        ) from exc

    except (httpx.HTTPError, ValueError) as exc:
        raise GeocodingServiceError(
            "Google Maps geocoding request failed."
        ) from exc

    status = data.get("status")

    if status == "ZERO_RESULTS":
        raise AddressNotFoundError(
            "The address could not be located."
        )

    if status != "OK":
        raise GeocodingServiceError(
            "Google Maps could not geocode the address."
        )

    results = data.get("results") or []

    if not results:
        raise GeocodingServiceError(
            "Google Maps returned an invalid response."
        )

    location = (
        results[0]
        .get("geometry", {})
        .get("location", {})
    )

    latitude = location.get("lat")
    longitude = location.get("lng")

    if latitude is None or longitude is None:
        raise GeocodingServiceError(
            "Google Maps did not return coordinates."
        )

    return float(latitude), float(longitude)