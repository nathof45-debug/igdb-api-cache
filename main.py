import os
import json
import requests

# 1. Authentification auprès de Twitch
auth_res = requests.post("https://id.twitch.tv/oauth2/token", data={
    "client_id": os.environ["TWITCH_CLIENT_ID"],
    "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
    "grant_type": "client_credentials"
}).json()

headers = {
    "Client-ID": os.environ["TWITCH_CLIENT_ID"],
    "Authorization": f"Bearer {auth_res['access_token']}"
}

# 2. Requête IGDB sur le nouvel endpoint PopScore
# popularity_type = 1 correspond aux visites sur IGDB.com
query = (
    "fields game_id.name, game_id.cover.image_id, game_id.rating, game_id.first_release_date, value; "
    "where popularity_type = 1; "
    "sort value desc; "
    "limit 50;"
)
pop_score_data = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query).json()

# 3. Nettoyage et formatage des données
# L'API renvoie une liste de scores. On extrait les données de la clé "game_id"
# pour avoir une liste de jeux propre, comme dans ton ancienne version.
games = []
for item in pop_score_data:
    if "game_id" in item:
        game_info = item["game_id"]
        # On intègre le score PopScore directement dans l'objet du jeu
        game_info["pop_score"] = item.get("value")
        games.append(game_info)

# 4. Sauvegarde du fichier JSON
with open("popular.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)
