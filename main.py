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
three_months_ago = current_time - (90 * 24 * 60 * 60)

# 3. Requête IGDB avec Pagination (Boucle "While")
games = []
offset = 0
max_games_to_check = 5000 # Sécurité : on s'arrête après avoir vérifié 5000 jeux

# Tant qu'on n'a pas 50 jeux et qu'on n'a pas dépassé la limite de sécurité
while len(games) < 50 and offset < max_games_to_check:
    
    query = (
        "fields game_id.name, game_id.cover.image_id, game_id.rating, game_id.first_release_date, value; "
        "where popularity_type = 1; "
        "sort value desc; "
        "limit 500; "
        f"offset {offset};" # C'est ici qu'on décale la recherche (0, puis 500, puis 1000...)
    )
    
    response = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query)
    pop_score_data = response.json()
    
    # Si l'API ne renvoie plus de données, on arrête tout
    if not pop_score_data or type(pop_score_data) is not list:
        break

    # 4. Filtrage des données de cette "page"
    for item in pop_score_data:
        if "game_id" in item:
            game_info = item["game_id"]
            release_date = game_info.get("first_release_date")
            
            if release_date and (three_months_ago <= release_date <= current_time):
                game_info["pop_score"] = item.get("value")
                games.append(game_info)
                
                # On s'arrête dès qu'on en a 50
                if len(games) >= 50:
                    break
    
    # Petit message qui s'affichera dans les logs de GitHub Actions pour t'aider à suivre
    print(f"Recherche dans les {offset + 500} jeux les plus populaires... Trouvés : {len(games)}/50")
    
    # On prépare le décalage pour la prochaine requête
    offset += 500

# 5. Sauvegarde du fichier JSON
with open("popular.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)
    
print("Terminé ! Le fichier popular.json a été mis à jour.")
