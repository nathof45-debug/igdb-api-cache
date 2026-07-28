import os
import json
import requests
import time

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

# 2. Calcul du temps pour le filtrage
current_time = int(time.time())
# 90 jours * 24 heures * 60 minutes * 60 secondes
three_months_ago = current_time - (90 * 24 * 60 * 60) 

# 3. Requête IGDB sur le PopScore
# On demande 500 résultats à IGDB pour être sûr d'avoir assez de jeux récents
query = (
    "fields game_id.name, game_id.cover.image_id, game_id.rating, game_id.first_release_date, value; "
    "where popularity_type = 1; "
    "sort value desc; "
    "limit 500;"
)
pop_score_data = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query).json()

# 4. Nettoyage et filtrage des dates avec Python
games = []
for item in pop_score_data:
    if "game_id" in item:
        game_info = item["game_id"]
        release_date = game_info.get("first_release_date")
        
        # On vérifie que le jeu possède une date de sortie
        # Et qu'il est sorti entre il y a 3 mois et aujourd'hui
        if release_date and (three_months_ago <= release_date <= current_time):
            # On ajoute le PopScore dans les données du jeu
            game_info["pop_score"] = item.get("value")
            games.append(game_info)
            
            # Dès qu'on a nos 50 jeux récents, on arrête la recherche
            if len(games) >= 50:
                break

# 5. Sauvegarde du fichier JSON
with open("popular.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)
