import requests
import pandas as pd
import time

URL = "https://apigw.prod.quintoandar.com.br/house-listing-search/v2/search/list"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Origin": "https://www.quintoandar.com.br"
}

all_data = []

latitudes = [-23.8, -23.7, -23.6, -23.5, -23.4]
longitudes = [-46.8, -46.7, -46.6, -46.5, -46.4]

fields = [

"id",
"rent",
"totalCost",
"iptuPlusCondominium",
"salePrice",

"area",
"bedrooms",
"bathrooms",
"parkingSpaces",
"suites",

"neighbourhood",
"city",
"regionName",
"address",

"type",
"forRent",
"forSale",

"isFurnished",
"isPrimaryMarket",

"amenities",
"installations",

"listingTags",
"categories",

"visitStatus",

"imageList",
"coverImage",

"yield",
"yieldStrategy",

"shortRentDescription",

"activeSpecialConditions"
]

for i in range(len(latitudes)-1):
    for j in range(len(longitudes)-1):

        north = latitudes[i+1]
        south = latitudes[i]
        east = longitudes[j+1]
        west = longitudes[j]

        offset = 0
        page_size = 50

        print(f"Área {i}-{j}")

        while True:

            payload = {
                "context": {
                    "mapShowing": True,
                    "listShowing": True
                },

                "filters": {
                    "businessContext": "RENT",
                    "location": {
                        "coordinate": {
                            "lat": (north + south)/2,
                            "lng": (east + west)/2
                        },
                        "viewport": {
                            "north": north,
                            "south": south,
                            "east": east,
                            "west": west
                        },
                        "countryCode": "BR"
                    }
                },

                "pagination": {
                    "pageSize": page_size,
                    "offset": offset
                },

                "slug": "sao-paulo-sp-brasil",

                "fields": fields
            }

            r = requests.post(URL, headers=headers, json=payload)

            if r.status_code != 200:
                print("Erro:", r.text)
                break

            data = r.json()

            listings = data.get("hits", {}).get("hits", [])

            if not listings:
                break

            for item in listings:

                source = item.get("_source", {})

                source["lat_viewport"] = (north + south)/2
                source["lon_viewport"] = (east + west)/2

                all_data.append(source)

            offset += page_size

            print(len(all_data), "imóveis")

            time.sleep(0.8)

df = pd.DataFrame(all_data)

df = df.drop_duplicates(subset="id")

df.to_csv("quintoandar_sp_full.csv", index=False)

print("Total:", len(df))