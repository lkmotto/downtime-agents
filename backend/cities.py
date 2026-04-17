"""
Top 50 US cities with coordinates for event fetching.
"""
from models import City

CITIES: list[City] = [
    City(name="New York", state="NY", lat=40.7128, lon=-74.0060),
    City(name="Los Angeles", state="CA", lat=34.0522, lon=-118.2437),
    City(name="Chicago", state="IL", lat=41.8781, lon=-87.6298),
    City(name="Houston", state="TX", lat=29.7604, lon=-95.3698),
    City(name="Phoenix", state="AZ", lat=33.4484, lon=-112.0740),
    City(name="Philadelphia", state="PA", lat=39.9526, lon=-75.1652),
    City(name="San Antonio", state="TX", lat=29.4241, lon=-98.4936),
    City(name="San Diego", state="CA", lat=32.7157, lon=-117.1611),
    City(name="Dallas", state="TX", lat=32.7767, lon=-96.7970),
    City(name="Austin", state="TX", lat=30.2672, lon=-97.7431),
    City(name="Jacksonville", state="FL", lat=30.3322, lon=-81.6557),
    City(name="Fort Worth", state="TX", lat=32.7555, lon=-97.3308),
    City(name="San Jose", state="CA", lat=37.3382, lon=-121.8863),
    City(name="Columbus", state="OH", lat=39.9612, lon=-82.9988),
    City(name="Charlotte", state="NC", lat=35.2271, lon=-80.8431),
    City(name="Indianapolis", state="IN", lat=39.7684, lon=-86.1581),
    City(name="San Francisco", state="CA", lat=37.7749, lon=-122.4194),
    City(name="Seattle", state="WA", lat=47.6062, lon=-122.3321),
    City(name="Denver", state="CO", lat=39.7392, lon=-104.9903),
    City(name="Washington", state="DC", lat=38.9072, lon=-77.0369),
    City(name="Nashville", state="TN", lat=36.1627, lon=-86.7816),
    City(name="Oklahoma City", state="OK", lat=35.4676, lon=-97.5164),
    City(name="El Paso", state="TX", lat=31.7619, lon=-106.4850),
    City(name="Boston", state="MA", lat=42.3601, lon=-71.0589),
    City(name="Portland", state="OR", lat=45.5152, lon=-122.6784),
    City(name="Las Vegas", state="NV", lat=36.1699, lon=-115.1398),
    City(name="Memphis", state="TN", lat=35.1495, lon=-90.0490),
    City(name="Louisville", state="KY", lat=38.2527, lon=-85.7585),
    City(name="Baltimore", state="MD", lat=39.2904, lon=-76.6122),
    City(name="Milwaukee", state="WI", lat=43.0389, lon=-87.9065),
    City(name="Albuquerque", state="NM", lat=35.0844, lon=-106.6504),
    City(name="Tucson", state="AZ", lat=32.2226, lon=-110.9747),
    City(name="Fresno", state="CA", lat=36.7378, lon=-119.7871),
    City(name="Sacramento", state="CA", lat=38.5816, lon=-121.4944),
    City(name="Mesa", state="AZ", lat=33.4152, lon=-111.8315),
    City(name="Kansas City", state="MO", lat=39.0997, lon=-94.5786),
    City(name="Atlanta", state="GA", lat=33.7490, lon=-84.3880),
    City(name="Omaha", state="NE", lat=41.2565, lon=-95.9345),
    City(name="Colorado Springs", state="CO", lat=38.8339, lon=-104.8214),
    City(name="Raleigh", state="NC", lat=35.7796, lon=-78.6382),
    City(name="Long Beach", state="CA", lat=33.7701, lon=-118.1937),
    City(name="Virginia Beach", state="VA", lat=36.8529, lon=-75.9780),
    City(name="Miami", state="FL", lat=25.7617, lon=-80.1918),
    City(name="Oakland", state="CA", lat=37.8044, lon=-122.2712),
    City(name="Minneapolis", state="MN", lat=44.9778, lon=-93.2650),
    City(name="Tampa", state="FL", lat=27.9506, lon=-82.4572),
    City(name="Tulsa", state="OK", lat=36.1540, lon=-95.9928),
    City(name="Arlington", state="TX", lat=32.7357, lon=-97.1081),
    City(name="New Orleans", state="LA", lat=29.9511, lon=-90.0715),
    City(name="Pittsburgh", state="PA", lat=40.4406, lon=-79.9959),
]


def get_city(name: str, state: str | None = None) -> City | None:
    """Look up a city by name and optional state code."""
    name_lower = name.lower()
    for city in CITIES:
        if city.name.lower() == name_lower:
            if state is None or city.state.upper() == state.upper():
                return city
    return None


def get_all_cities() -> list[City]:
    """Return all supported cities."""
    return CITIES
