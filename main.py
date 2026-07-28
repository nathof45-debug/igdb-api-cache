import os
import json
import requests
import time

print("🔄 Démarrage du script de génération du BFF IGDB...")

# ==========================================
# 1. AUTHENTIFICATION TWITCH
# ==========================================
print("🔑 Authentification Twitch en cours...")
client_id = os.environ.get("TWITCH_CLIENT_ID")
client_secret = os.environ.get("TWITCH_CLIENT_SECRET")

if not client_id or not client_secret:
    print("❌ ERREUR : Les variables d'environnement TWITCH_CLIENT_ID ou TWITCH_CLIENT_SECRET sont manquantes.")
    exit(1)

auth_res = requests.post("https://id.twitch.tv/oauth2/token", data={
    "client_id": client_id,
    "client_secret": client_secret,
    "grant_type": "client_credentials"
}).json()

if "access_token" not in auth_res:
    print(f"❌ ERREUR AUTHENTIFICATION : {auth_res}")
    exit(1)

headers = {
    "Client-ID": client_id,
    "Authorization": f"Bearer {auth_res['access_token']}"
}
print("✅ Authentification réussie.")

# ==========================================
# 2. CONFIGURATION DES DATES ET CHAMPS
# ==========================================
today = int(time.time())
fourteen_days_ago = today - (14 * 24 * 60 * 60)
three_months_ago = today - (90 * 24 * 60 * 60)

# Les champs demandés sont identiques pour toutes les requêtes afin de n'avoir qu'une seule Data Class Kotlin
COMMON_FIELDS = (
    "fields name, cover.image_id, rating, first_release_date, "
    "platforms.name, genres.name, "
    "involved_companies.developer, involved_companies.publisher, involved_companies.company.name, "
    "language_supports.language.name; "
)

BASE_URL = "https://api.igdb.com/v4/games"

# ==========================================
# 3. FONCTIONS UTILITAIRES
# ==========================================
def clean_games_data(games_data, scores_dict=None):
    """Aplatit et nettoie les données complexes d'IGDB pour le mobile."""
    cleaned_list = []
    
    for game in games_data:
        clean_game = {
            "id": game.get("id"),
            "name": game.get("name"),
            "cover": game.get("cover"),
            "rating": game.get("rating"),
            "first_release_date": game.get("first_release_date"),
        }

        # Ajout du pop_score si fourni (uniquement pour la catégorie Popular)
        if scores_dict:
            clean_game["pop_score"] = scores_dict.get(str(game["id"]))
        else:
            clean_game["pop_score"] = None

        clean_game["platforms"] = [p.get("name") for p in game.get("platforms", []) if "name" in p]
        clean_game["genres"] = [g.get("name") for g in game.get("genres", []) if "name" in g]

        devs, pubs = [], []
        for company in game.get("involved_companies", []):
            comp_name = company.get("company", {}).get("name")
            if comp_name:
                if company.get("developer"): devs.append(comp_name)
                if company.get("publisher"): pubs.append(comp_name)
        
        clean_game["developers"] = devs
        clean_game["publishers"] = pubs

        langs = set()
        for lang in game.get("language_supports", []):
            lang_name = lang.get("language", {}).get("name")
            if lang_name: langs.add(lang_name)
        clean_game["languages"] = list(langs)

        cleaned_list.append(clean_game)
        
    return cleaned_list

def save_json(data, filename):
    """Sauvegarde la liste dans un fichier JSON."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 {len(data)} jeux sauvegardés dans {filename}")

# ==========================================
# 4. EXÉCUTION DES CATÉGORIES
# ==========================================

# --- CATÉGORIE 1 : Les dernières sorties (14 jours) ---
print("\n📡 Génération : Les dernières sorties...")
query_latest = f"{COMMON_FIELDS} where first_release_date >= {fourteen_days_ago} & first_release_date <= {today}; sort first_release_date desc; limit 50;"
res = requests.post(BASE_URL, headers=headers, data=query_latest)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())
    save_json(cleaned, "latest.json")
else:
    print(f"❌ Erreur Latest : {res.text}")

# --- CATÉGORIE 2 : Populaires récemment (3 mois) ---
print("\n📡 Génération : Populaires récemment...")
# Étape A : Top Primitives
query_prims = "fields game_id, value; where popularity_type = 1; sort value desc; limit 500;"
res_prims = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query_prims)

if res_prims.status_code == 200:
    scores_dict = {str(item["game_id"]): item["value"] for item in res_prims.json() if "game_id" in item}
    ids_str = ",".join(scores_dict.keys())
    
    # Étape B : Détails filtrés sur les 3 derniers mois
    if ids_str:
        query_popular = f"{COMMON_FIELDS} where id = ({ids_str}) & first_release_date >= {three_months_ago} & first_release_date <= {today}; limit 500;"
        res_games = requests.post(BASE_URL, headers=headers, data=query_popular)
        
        if res_games.status_code == 200:
            cleaned = clean_games_data(res_games.json(), scores_dict)
            # Tri local par pop_score décroissant et limitation à 50
            cleaned = sorted(cleaned, key=lambda x: x.get("pop_score") or 0, reverse=True)[:50]
            save_json(cleaned, "popular.json")
        else:
            print(f"❌ Erreur Popular (Games) : {res_games.text}")
else:
    print(f"❌ Erreur Popular (Primitives) : {res_prims.text}")

# --- CATÉGORIE 3 : Sorties à venir (Attendus) ---
print("\n📡 Génération : Sorties à venir...")
query_upcoming = f"{COMMON_FIELDS} where first_release_date > {today}; sort first_release_date asc; limit 50;"
res = requests.post(BASE_URL, headers=headers, data=query_upcoming)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())
    save_json(cleaned, "upcoming.json")
else:
    print(f"❌ Erreur Upcoming : {res.text}")

# --- CATÉGORIE 4 : Futurs blockbusters (Les plus attendus) ---
print("\n📡 Génération : Futurs blockbusters...")
query_blockbusters = f"{COMMON_FIELDS} where first_release_date > {today} & hypes != null; sort hypes desc; limit 50;"
res = requests.post(BASE_URL, headers=headers, data=query_blockbusters)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())
    save_json(cleaned, "blockbusters.json")
else:
    print(f"❌ Erreur Blockbusters : {res.text}")

print("\n🎉 Toutes les catégories ont été générées avec succès !")
