import os
import json
import requests

auth_res = requests.post("https://id.twitch.tv/oauth2/token", data={
    "client_id": os.environ["TWITCH_CLIENT_ID"],
    "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
    "grant_type": "client_credentials"
}).json()

headers = {
    "Client-ID": os.environ["TWITCH_CLIENT_ID"],
    "Authorization": f"Bearer {auth_res['access_token']}"
}

query = "fields name, cover.image_id, rating, first_release_date; sort popularity desc; limit 50;"
games = requests.post("https://api.igdb.com/v4/games", headers=headers, data=query).json()

with open("popular.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)
