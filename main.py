import os
import json
import requests
import time
import datetime

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
seven_days_ago = today - (7 * 24 * 60 * 60)
one_month_ago = today - (30 * 24 * 60 *60)
next_week = today + 604800
current_year = datetime.datetime.now().year

# Statuts de release_dates valides pour le calendrier (Jouables)
# 6: Full Release, 34: Advanced Access, 3: Early Access
VALID_PLAYABLE = {6, 34, 3}

COMMON_FIELDS = (
    "fields name, cover.image_id, rating, rating_count, total_rating_count, "
    "hypes, follows, status, themes, " 
    "first_release_date, release_dates.*, release_dates.platform.name,"
    "platforms.name, genres.name, "
    "involved_companies.developer, involved_companies.publisher, involved_companies.company.name, "
    "language_supports.language.name; "
)

BASE_URL = "https://api.igdb.com/v4/games"

# ==========================================
# 3. FONCTIONS UTILITAIRES
# ==========================================
def clean_games_data(games_data, scores_dict=None):
    cleaned_list = []
    for game in games_data:
        clean_game = {
            "id": game.get("id"),
            "name": game.get("name"),
            "cover": game.get("cover"),
            "rating": game.get("rating"),
            "first_release_date": game.get("first_release_date"),
            "hypes": game.get("hypes"),
            "status": game.get("status"),
            "follows": game.get("follows"),
            "themes": game.get("themes", []),
            "release_dates": [
                {
                    "category": rd.get("date_format", rd.get("category")),
                    "y": rd.get("y"),
                    "m": rd.get("m"),
                    "d": datetime.datetime.fromtimestamp(rd.get("date")).day if rd.get("date") else None,
                    "date": rd.get("date"),
                    "status": rd.get("status"),
                    "platform_name": rd.get("platform", {}).get("name") if isinstance(rd.get("platform"), dict) else None
                } 
                for rd in game.get("release_dates", [])
            ]
        }
        if scores_dict:
            clean_game["pop_score"] = scores_dict.get(str(game["id"]))
        
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
        clean_game["languages"] = list(set(lang.get("language", {}).get("name") for lang in game.get("language_supports", []) if lang.get("language", {}).get("name")))
        cleaned_list.append(clean_game)
    return cleaned_list

def get_hybrid_sort_date(game, today_ts=None, future_only=False):
    if today_ts is None: today_ts = int(time.time())
    playable_dates = []
    
    # On ignore Alpha (1), Beta (2), Offline (4), Cancelled (5)
    EXCLUDED_STATUSES = {1, 2, 4, 5}
    
    for rd in game.get("release_dates", []):
        st = rd.get("status")
        dt = rd.get("date")
        if st in EXCLUDED_STATUSES or not dt: continue
        
        if st in VALID_PLAYABLE:
            if not future_only or dt >= today_ts:
                playable_dates.append(dt)
            
    if playable_dates: return min(playable_dates)
    
    first_date = game.get("first_release_date")
    if first_date and (not future_only or first_date >= today_ts):
        return first_date
        
    return 9999999999

def get_best_date(game, today_ts=None, future_only=False):
    res = get_hybrid_sort_date(game, today_ts, future_only)
    return res if res != 9999999999 else None

def save_json(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 {len(data)} jeux sauvegardés dans {filename}")

# ==========================================
# 4. EXÉCUTION DES CATÉGORIES
# ==========================================

# --- CATÉGORIE 1 : Les dernières sorties ---
print("\n📡 Génération : Les dernières sorties...")
query_latest = (
    f"{COMMON_FIELDS} "
    f"where ((first_release_date >= {seven_days_ago} & first_release_date <= {today}) "
    f"| (release_dates.date >= {seven_days_ago} & release_dates.date <= {today})) "
    f"& release_dates.date_format = 0 "
    f"& cover != null & cover.image_id != null " 
    f"& !(status = (4, 5, 6)); " # Exclut cancelled/offline au niveau game.status
    f"sort hypes desc; limit 100;"
)
res = requests.post(BASE_URL, headers=headers, data=query_latest)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())[:100]
    final_latest = []
    for g in cleaned:
        has_precise_recent_release = any(
            rd.get("category") == 0 and 
            rd.get("status") in VALID_PLAYABLE and
            rd.get("date") and seven_days_ago <= rd.get("date") <= today 
            for rd in g.get("release_dates", [])
        )
        # Fallback corrigé
        if not has_precise_recent_release and g.get("first_release_date"):
            if seven_days_ago <= g.get("first_release_date") <= today:
                has_precise_recent_release = True 

        if has_precise_recent_release and g.get("cover", {}).get("image_id"):
            final_latest.append(g)

    final_latest.sort(key=lambda g: get_hybrid_sort_date(g, today, future_only=False), reverse=True)
    save_json(final_latest[:50], "latest.json")

# --- CATÉGORIE 2 : Populaires actuellement ---
print("\n📡 Génération : Populaires actuellement...")
query_prims = "fields game_id, value; where popularity_type = 1; sort value desc; limit 500;"
res_prims = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query_prims)

if res_prims.status_code == 200:
    scores_dict = {str(item["game_id"]): item["value"] for item in res_prims.json() if "game_id" in item}
    ids_str = ",".join(scores_dict.keys())
    if ids_str:
        query_popular = f"{COMMON_FIELDS} where id = ({ids_str}) & first_release_date >= {one_month_ago} & first_release_date <= {today}; limit 500;"
        res_games = requests.post(BASE_URL, headers=headers, data=query_popular)
        if res_games.status_code == 200:
            cleaned = [g for g in clean_games_data(res_games.json(), scores_dict) if g.get("status") not in {1, 2}]
            cleaned = sorted(cleaned, key=lambda x: x.get("pop_score") or 0, reverse=True)[:50]
            save_json(cleaned, "popular.json")

# --- CATÉGORIE 3 : Sorties populaires de la semaine ---
print("\n📡 Génération : Sorties populaires de la semaine...")
query_upcoming = (
    f"{COMMON_FIELDS} "
    f"where ((first_release_date > {today} & first_release_date <= {next_week}) "
    f"| (release_dates.date > {today} & release_dates.date <= {next_week})) "
    f"& release_dates.date_format = 0 & !(status = (4, 5, 6)) & hypes >= 7; "
    f"limit 500;"
)
res = requests.post(BASE_URL, headers=headers, data=query_upcoming)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())
    final_upcoming = [
        g for g in cleaned 
        if any(rd.get("category") == 0 and rd.get("status") in VALID_PLAYABLE and rd.get("date") and today < rd.get("date") <= next_week for rd in g.get("release_dates", []))
    ]
    final_upcoming.sort(key=lambda g: get_hybrid_sort_date(g, today, future_only=True))
    save_json(final_upcoming[:50], "upcoming.json")

# --- CATÉGORIE 4 : Futurs blockbusters ---
print("\n📡 Génération : Futurs blockbusters...")
# (Logique de récupération des IDs identiques à ton code...)
# Filtrage final optimisé :
future_games = []
for g in cleaned_bb:
    sort_ts = get_hybrid_sort_date(g, today, future_only=True)
    if today < sort_ts < 9999999999:
        g["_tmp_sort_ts"] = sort_ts
        future_games.append(g)

cleaned_bb_sorted = sorted(future_games, key=lambda x: x["_tmp_sort_ts"])[:50]
for g in cleaned_bb_sorted: g.pop("_tmp_sort_ts", None)
save_json(cleaned_bb_sorted, "blockbusters.json")

# --- CATÉGORIE 5 : TBD ---
print("\n📡 Génération : Jeux annoncés (TBD)...")
res = requests.post(BASE_URL, headers=headers, data=query_tbd)
if res.status_code == 200:
    # get_best_date avec future_only=True renverra None si le jeu n'a que des dates passées ou des Alphas/Betas
    cleaned = [g for g in clean_games_data(res.json()) if get_best_date(g, today, future_only=True) is None]
    cleaned.sort(key=lambda x: x.get("hypes") or 0, reverse=True)
    save_json(cleaned[:50], "tbd.json")

print("\n🎉 Toutes les catégories ont été générées avec succès !")
