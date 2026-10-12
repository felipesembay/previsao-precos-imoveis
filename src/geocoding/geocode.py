import os

from dotenv import load_dotenv
from opencage.geocoder import OpenCageGeocode

load_dotenv()

OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")

geocoder = OpenCageGeocode(OPENCAGE_API_KEY)


def geocode_endereco_opencage(endereco):
    results = geocoder.geocode(endereco, language="pt", countrycode="br")

    if not results:
        return None

    r = results[0]

    return {
        "lat": r["geometry"]["lat"],
        "lon": r["geometry"]["lng"],
        "confidence": r.get("confidence"),
        "components": r.get("components"),
        "formatted": r.get("formatted")
    }