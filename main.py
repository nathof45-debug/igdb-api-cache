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
max_games_to_check = 5000

while len(games) < 50 and offset < max_games_to_check:
    print(f"\n📡 1/2: Récupération des PopScores (offset: {offset})...")
    
    query_prims = f"fields game_id, value; where popularity_type = 1; sort value desc; limit 500; offset {offset};"
    res_prims = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query_prims)
    
    if res_prims.status_code != 200:
        print(f"❌ ERREUR PRIMITIVES: {res_prims.text}")
        break
        
    prims_data = res_prims.json()
    if not prims_data:
        break
        
    scores_dict = {}
    for item in prims_data:
        if "game_id" in item and "value" in item:
            scores_dict[str(item["game_id"])] = item["value"]
            
    print(f"📡 2/2: Récupération des détails et filtrage des dates pour ces {len(scores_dict)} jeux...")
    ids_str = ",".join(scores_dict.keys())
    
    # --- NOUVELLE REQUÊTE ENRICHIE ---
    query_games = (
        f"fields name, cover.image_id, rating, first_release_date, "
        f"platforms.name, genres.name, "
        f"involved_companies.developer, involved_companies.publisher, involved_companies.company.name, "
        f"language_supports.language.name; "
        f"where id = ({ids_str}) & first_release_date >= {three_months_ago} & first_release_date <= {current_time}; "
        f"limit 500;"
    )
    
    res_games = requests.post("https://api.igdb.com/v4/games", headers=headers, data=query_games)
    
    if res_games.status_code != 200:
        print(f"❌ ERREUR GAMES: {res_games.text}")
        break
        
    games_data = res_games.json()
    
    # --- NETTOYAGE ET FORMATAGE POUR LE MOBILE ---
    for game in games_data:
        # Création d'un objet propre et plat
        clean_game = {
            "id": game.get("id"),
            "name": game.get("name"),
            "cover": game.get("cover"),
            "rating": game.get("rating"),
            "first_release_date": game.get("first_release_date"),
            "pop_score": scores_dict[str(game["id"])]
        }

        # Extraction des plateformes (Liste de strings)
        clean_game["platforms"] = [p.get("name") for p in game.get("platforms", []) if "name" in p]
        
        # Extraction des genres (Liste de strings)
        clean_game["genres"] = [g.get("name") for g in game.get("genres", []) if "name" in g]

        # Tri des développeurs et éditeurs
        devs = []
        pubs = []
        for company in game.get("involved_companies", []):
            comp_name = company.get("company", {}).get("name")
            if comp_name:
                if company.get("developer"):
                    devs.append(comp_name)
                if company.get("publisher"):
                    pubs.append(comp_name)
        
        clean_game["developers"] = devs
        clean_game["publishers"] = pubs

        # Extraction des langues (Utilisation de 'set' pour éviter les doublons si une langue a audio + sous-titres)
        langs = set()
        for lang in game.get("language_supports", []):
            lang_name = lang.get("language", {}).get("name")
            if lang_name:
                langs.add(lang_name)
        clean_game["languages"] = list(langs)

        # Ajout du jeu nettoyé à notre liste finale
        games.append(clean_game)
        
    offset += 500
    print(f"📊 Total des jeux récents validés : {len(games)}/50")

# 4. Tri et Nettoyage final
games = sorted(games, key=lambda x: x.get("pop_score", 0), reverse=True)
games = games[:50]

# 5. Sauvegarde
print(f"\n💾 Sauvegarde de {len(games)} jeux dans popular.json...")
with open("popular.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)
    
print("🎉 Terminé !")
