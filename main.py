import os
import json
import requests
import time

print("🔄 Démarrage du script...")

# 1. Authentification Twitch
print("🔑 Authentification Twitch en cours...")
auth_res = requests.post("https://id.twitch.tv/oauth2/token", data={
    "client_id": os.environ["TWITCH_CLIENT_ID"],
    "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
    "grant_type": "client_credentials"
}).json()

if "access_token" not in auth_res:
    print(f"❌ ERREUR AUTHENTIFICATION: {auth_res}")
    exit(1)

headers = {
    "Client-ID": os.environ["TWITCH_CLIENT_ID"],
    "Authorization": f"Bearer {auth_res['access_token']}"
}

# 2. Calcul du temps (Les 3 derniers mois)
current_time = int(time.time())
three_months_ago = current_time - (90 * 24 * 60 * 60)

# 3. Boucle de recherche
games = []
offset = 0
max_games_to_check = 5000 # On fouille jusqu'à 5000 jeux maximum

while len(games) < 50 and offset < max_games_to_check:
    print(f"\n📡 1/2: Récupération des PopScores (offset: {offset})...")
    
    # REQUÊTE 1 : On récupère uniquement les IDs et les Scores
    query_prims = f"fields game_id, value; where popularity_type = 1; sort value desc; limit 500; offset {offset};"
    res_prims = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query_prims)
    
    if res_prims.status_code != 200:
        print(f"❌ ERREUR PRIMITIVES: {res_prims.text}")
        break
        
    prims_data = res_prims.json()
    if not prims_data:
        print("🛑 Plus de données dans le PopScore.")
        break
        
    # On stocke les scores dans un dictionnaire pour les associer plus tard { "ID_du_jeu": Score }
    scores_dict = {}
    for item in prims_data:
        if "game_id" in item and "value" in item:
            scores_dict[str(item["game_id"])] = item["value"]
            
    # REQUÊTE 2 : On demande les détails de ces jeux précis, ET on filtre la date directement via l'API !
    print(f"📡 2/2: Récupération des détails et filtrage des dates pour ces {len(scores_dict)} jeux...")
    ids_str = ",".join(scores_dict.keys())
    
    query_games = (
        f"fields name, cover.image_id, rating, first_release_date; "
        f"where id = ({ids_str}) & first_release_date >= {three_months_ago} & first_release_date <= {current_time}; "
        f"limit 500;"
    )
    
    res_games = requests.post("https://api.igdb.com/v4/games", headers=headers, data=query_games)
    
    if res_games.status_code != 200:
        print(f"❌ ERREUR GAMES: {res_games.text}")
        break
        
    games_data = res_games.json()
    print(f"✅ Trouvés : {len(games_data)} jeux sortis ces 3 derniers mois dans ce lot.")
    
    # On ajoute le PopScore aux données du jeu et on l'ajoute à notre liste finale
    for game in games_data:
        game["pop_score"] = scores_dict[str(game["id"])]
        games.append(game)
        
    offset += 500
    print(f"📊 Total des jeux récents validés : {len(games)}/50")

# 4. Tri et Nettoyage final
# IGDB ne renvoie pas les jeux dans l'ordre demandé lors de la 2ème requête, 
# donc on les trie nous-mêmes par PopScore décroissant.
games = sorted(games, key=lambda x: x.get("pop_score", 0), reverse=True)

# On coupe la liste pour n'en garder que 50 exactement
games = games[:50]

# 5. Sauvegarde
print(f"\n💾 Sauvegarde de {len(games)} jeux dans popular.json...")
with open("popular.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)
    
print("🎉 Terminé !")
