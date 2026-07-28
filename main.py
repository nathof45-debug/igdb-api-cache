import os
import json
import requests
import time
from datetime import datetime

print("🔄 Démarrage du script...")

# 1. Authentification
print("🔑 Authentification Twitch en cours...")
auth_res = requests.post("https://id.twitch.tv/oauth2/token", data={
    "client_id": os.environ["TWITCH_CLIENT_ID"],
    "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
    "grant_type": "client_credentials"
}).json()

if "access_token" not in auth_res:
    print(f"❌ ERREUR AUTHENTIFICATION: {auth_res}")
    exit(1)

print("✅ Authentification réussie !")

headers = {
    "Client-ID": os.environ["TWITCH_CLIENT_ID"],
    "Authorization": f"Bearer {auth_res['access_token']}"
}

# 2. Calcul du temps
current_time = int(time.time())
three_months_ago = current_time - (90 * 24 * 60 * 60)

print(f"📅 Recherche des jeux sortis entre le : {datetime.fromtimestamp(three_months_ago)} et le {datetime.fromtimestamp(current_time)}")

# 3. Requête IGDB avec Pagination
games = []
offset = 0
max_games_to_check = 5000

while len(games) < 50 and offset < max_games_to_check:
    print(f"\n📡 Envoi de la requête à IGDB (offset: {offset})...")
    
    query = (
        "fields game_id.name, game_id.cover.image_id, game_id.rating, game_id.first_release_date, value; "
        "where popularity_type = 1; "
        "sort value desc; "
        "limit 500; "
        f"offset {offset};"
    )
    
    response = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query)
    
    if response.status_code != 200:
        print(f"❌ ERREUR IGDB ({response.status_code}) : {response.text}")
        break
        
    pop_score_data = response.json()
    print(f"✅ {len(pop_score_data)} résultats reçus pour cette page.")
    
    # Afficher la structure du TOUT PREMIER jeu pour vérifier le format de la donnée
    if offset == 0 and len(pop_score_data) > 0:
        print("🔍 Structure brute du premier jeu reçu :")
        print(json.dumps(pop_score_data[0], indent=2))

    if not pop_score_data:
        print("🛑 Plus aucune donnée renvoyée par IGDB, arrêt de la recherche.")
        break

    # Variables pour compter pourquoi les jeux sont rejetés
    stats_no_date = 0
    stats_too_old = 0
    stats_future = 0
    stats_added = 0

    # 4. Filtrage
    for item in pop_score_data:
        if "game_id" in item:
            game_info = item["game_id"]
            release_date = game_info.get("first_release_date")
            
            if not release_date:
                stats_no_date += 1
            elif release_date < three_months_ago:
                stats_too_old += 1
            elif release_date > current_time:
                stats_future += 1
            else:
                game_info["pop_score"] = item.get("value")
                games.append(game_info)
                stats_added += 1
                
                if len(games) >= 50:
                    break

    print(f"📊 Bilan de la page (offset {offset}) :")
    print(f"   - Sans date de sortie : {stats_no_date}")
    print(f"   - Trop vieux (< 3 mois) : {stats_too_old}")
    print(f"   - Pas encore sortis (futur) : {stats_future}")
    print(f"   - ✅ Validés et ajoutés : {stats_added}")
    print(f"   - TOTAL validés pour l'instant : {len(games)}/50")
    
    offset += 500

# 5. Sauvegarde
print(f"\n💾 Sauvegarde de {len(games)} jeux dans popular.json...")
with open("popular.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)
    
print("🎉 Terminé !")
