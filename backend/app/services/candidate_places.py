"""Offline geographic references relative to GeoNames populated places."""
from functools import lru_cache
from math import asin, cos, radians, sin

from geonamescache import GeonamesCache
from scipy.spatial import cKDTree


def _sphere(lat, lon):
    lat, lon = radians(lat), radians(lon)
    return cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat)


@lru_cache(maxsize=1)
def _settlements():
    gazetteer = GeonamesCache()
    countries = gazetteer.get_countries()
    cities = gazetteer.get_cities().values()
    coordinates, names = [], []
    for city in cities:
        coordinates.append(_sphere(city['latitude'], city['longitude']))
        country = countries.get(city['countrycode'], {}).get('name', city['countrycode'])
        names.append(f"{city['name']}, {country}")
    return cKDTree(coordinates), names


def place_reference(lat, lon):
    tree, names = _settlements()
    chord, index = tree.query(_sphere(lat, lon))
    distance = round(12742 * asin(min(1, chord / 2)))
    return f"{distance} km from {names[index]}"
