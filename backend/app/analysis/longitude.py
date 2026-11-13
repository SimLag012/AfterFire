"""Geographic bounds for a compact group of FIRMS detections."""


def longitude_summary(longitudes):
    """Return centre, west, east and width. Wrapped intervals have west > east."""
    if not longitudes:
        return 0.0, 0.0, 0.0, 0.0
    west, east = min(longitudes), max(longitudes)
    if east - west <= 180:
        return sum(longitudes) / len(longitudes), west, east, east - west
    shifted = [lon + 360 if lon < 0 else lon for lon in longitudes]
    west, east = min(shifted), max(shifted)
    centre = sum(shifted) / len(shifted)
    return (centre + 180) % 360 - 180, west, east - 360, east - west
