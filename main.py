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

seven_days_ago = today - (7 * 24 * 3600)
two_months_ago = today - (60 * 24 * 3600)
one_year_ago = int(time.time()) - (365 * 24 * 3600)
next_week = today + 604800
current_year = datetime.datetime.now().year

VALID_PLAYABLE = {6, 34, 3}

# IDs des game_types à exclure : 5 (Mod), 12 (Fork), 14 (Update)
EXCLUDED_GAME_TYPES = {5, 12, 14}
# Mots-clés / Slugs à exclure (Fangames et contenus non officiels)
EXCLUDED_KEYWORDS_SLUGS = {"unofficial", "fan-made", "fan-game", "rom-hack", "fangame"}

# Ajout de keywords.slug aux COMMON_FIELDS
COMMON_FIELDS = (
    "fields name, cover.image_id, rating, rating_count, total_rating_count, "
    "hypes, follows, status, themes, created_at, game_type, keywords.slug, " 
    "first_release_date, release_dates.*, release_dates.platform.name, "
    "platforms.name, platforms.id, "
    "genres.name, genres.id, "
    "involved_companies.id, "
    "involved_companies.developer, involved_companies.publisher, "
    "involved_companies.company.name, involved_companies.company.id, "
    "language_supports.language.name, language_supports.language.id; "
)

BASE_URL = "https://api.igdb.com/v4/games"

# Clause de filtrage globale pour l'API IGDB
NO_FANGAME_FILTER = (
    "& (game_type = null | game_type != (5, 12, 14)) "
    "& (keywords = null | keywords.slug != (\"unofficial\", \"fan-made\", \"fan-game\", \"rom-hack\", \"fangame\"))"
)

# ==========================================
# 3. FONCTIONS UTILITAIRES
# ==========================================
def clean_games_data(games_data, scores_dict=None):
    """Aplatit et nettoie les données complexes d'IGDB pour le mobile."""
    cleaned_list = []
    
    for game in games_data:
        # --- 1. Exclusion des game_types indésirables (Mod, Fork, Update) ---
        g_type = game.get("game_type")
        if isinstance(g_type, dict):
            g_type = g_type.get("id")
        if g_type in EXCLUDED_GAME_TYPES:
            continue
            
        # --- 2. Exclusion des Fangames via keywords ---
        keywords = game.get("keywords", [])
        keyword_slugs = [k.get("slug") for k in keywords if isinstance(k, dict) and k.get("slug")]
        if any(slug in EXCLUDED_KEYWORDS_SLUGS for slug in keyword_slugs):
            continue

        # --- 3. Exclusion des Fangames via mots-clés dans le Titre ---
        game_name_lower = (game.get("name") or "").lower()
        if any(bad_word in game_name_lower for bad_word in ["fangame", "fan game", "fan-game", "rom hack"]):
            continue

        game_id = game.get("id")
        
        # Plateformes, Genres, Studios, Langues...
        platforms = game.get("platforms", [])
        p_names = [p.get("name") for p in platforms if p.get("name")]
        p_ids = [p.get("id") for p in platforms if p.get("id")]

        genres = game.get("genres", [])
        g_names = [g.get("name") for g in genres if g.get("name")]
        g_ids = [g.get("id") for g in genres if g.get("id")]

        dev_names, dev_ids = [], []
        pub_names, pub_ids = [], []
        for inv in game.get("involved_companies", []):
            company = inv.get("company", {})
            c_name = company.get("name")
            c_id = company.get("id")
            if c_name and c_id:
                if inv.get("developer"):
                    dev_names.append(c_name)
                    dev_ids.append(c_id)
                if inv.get("publisher"):
                    pub_names.append(c_name)
                    pub_ids.append(c_id)

        l_names = list(set(
            ls.get("language", {}).get("name") 
            for ls in game.get("language_supports", []) 
            if ls.get("language", {}).get("name")
        ))

        clean_game = {
            "id": game_id,
            "name": game.get("name"),
            "cover": game.get("cover"),
            "rating": game.get("rating"),
            "first_release_date": game.get("first_release_date"),
            "hypes": game.get("hypes"),
            "status": game.get("status"),
            "follows": game.get("follows"),
            "themes": game.get("themes", []),
            "pop_score": scores_dict.get(str(game_id)) if scores_dict else None,
            "platforms": p_names,
            "platform_ids": p_ids,
            "genres": g_names,
            "genre_ids": g_ids,
            "developers": dev_names,
            "developer_ids": dev_ids,
            "publishers": pub_names,
            "publisher_ids": pub_ids,
            "languages": l_names,
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
        cleaned_list.append(clean_game)
        
    return cleaned_list

def get_hybrid_sort_date(game, today_ts=None, future_only=False):
    if today_ts is None: today_ts = int(time.time())
    playable_dates = []
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
    f"& (status = null | status != (4, 5)) & hypes != null "
    f"{NO_FANGAME_FILTER}; "
    f"sort hypes desc; "
    f"limit 100;"
)
res = requests.post(BASE_URL, headers=headers, data=query_latest)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())[:100]
    final_latest = []
    
    for g in cleaned:
        # 1. SÉCURITÉ ANTI-FUTUR : On supprime toutes les dates > today
        # Ainsi, l'application Android ne pourra pas afficher "2026"
        past_releases = [
            rd for rd in g.get("release_dates", [])
            if rd.get("date") and rd.get("date") <= today
        ]
        g["release_dates"] = past_releases # Remplacement dans l'objet
        
        # 2. Vérification stricte : il FAUT une date "précise" (0) et jouable cette semaine
        has_precise_recent_release = any(
            rd.get("category") == 0 and 
            rd.get("status") in VALID_PLAYABLE and
            seven_days_ago <= rd.get("date") <= today 
            for rd in past_releases
        )
        
        # 3. Sécurité globale : Le jeu dans son ensemble ne doit pas être futur
        global_date = g.get("first_release_date")
        is_globally_released = not global_date or global_date <= today
        
        if has_precise_recent_release and is_globally_released and g.get("cover") and g.get("cover").get("image_id"):
            final_latest.append(g)

    # Tri par date de sortie pour avoir les plus récents en premier
    final_latest.sort(key=lambda g: get_hybrid_sort_date(g, today, future_only=False), reverse=True)
    
    save_json(final_latest[:100], "latest.json")
    print("✅ Fichier latest.json généré avec succès.")
else:
    print(f"❌ Erreur Latest : {res.text}")

# --- CATÉGORIE 2 : Populaires actuellement ---
print("\n📡 Génération : Populaires actuellement...")
query_prims = "fields game_id, value; where popularity_type = 1; sort value desc; limit 500;"
res_prims = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query_prims)

if res_prims.status_code == 200:
    scores_dict = {str(item["game_id"]): item["value"] for item in res_prims.json() if "game_id" in item}
    ids_str = ",".join(scores_dict.keys())
    if ids_str:
        query_popular = (
            f"{COMMON_FIELDS} "
            f"where id = ({ids_str}) "
            f"& first_release_date >= {two_months_ago} "
            f"& first_release_date <= {today} "
            f"{NO_FANGAME_FILTER}; "
            f"limit 500;"
        )
        res_games = requests.post(BASE_URL, headers=headers, data=query_popular)
        if res_games.status_code == 200:
            cleaned = [g for g in clean_games_data(res_games.json(), scores_dict) if g.get("status") not in {1, 2}]
            cleaned = sorted(cleaned, key=lambda x: x.get("pop_score") or 0, reverse=True)
            save_json(cleaned[:100], "popular.json")
            print("✅ Fichier popular.json généré avec succès.")

# --- CATÉGORIE 3 : Sorties populaires de la semaine ---
print("\n📡 Génération : Sorties populaires de la semaine...")
query_upcoming = (
    f"{COMMON_FIELDS} "
    f"where ((first_release_date > {today} & first_release_date <= {next_week}) "
    f"| (release_dates.date > {today} & release_dates.date <= {next_week})) "
    f"& release_dates.date_format = 0 "
    f"& (status = null | status != (6, 7)) & hypes >= 7 "
    f"{NO_FANGAME_FILTER}; "
    f"limit 500;"
)
res = requests.post(BASE_URL, headers=headers, data=query_upcoming)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())
    final_upcoming = []
    for g in cleaned:
        if any(rd.get("category") == 0 and rd.get("status") in {6, 34, 3} and rd.get("date") and today < rd.get("date") <= next_week 
               for rd in g.get("release_dates", [])):
            final_upcoming.append(g)
    final_upcoming.sort(key=lambda g: get_hybrid_sort_date(g, today, future_only=True))
    save_json(final_upcoming[:100], "upcoming.json")

# --- CATÉGORIE 4 : Futurs blockbusters ---
print("\n📡 Génération : Futurs blockbusters (Popscore - Multi-pages)...")
scores_dict_bb = {}
for offset in [0, 500, 1000, 1500, 2000]:
    query_prims = f"fields game_id, value; where popularity_type = 2; sort value desc; limit 500; offset {offset};"
    res_prims = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query_prims)
    if res_prims.status_code == 200:
        for item in res_prims.json():
            if "game_id" in item:
                scores_dict_bb[str(item["game_id"])] = item["value"]

all_ids = list(scores_dict_bb.keys())
future_blockbusters = []

for i in range(0, len(all_ids), 500):
    chunk_ids = ",".join(all_ids[i:i+500])
    query_bb_games = (
        f"{COMMON_FIELDS} "
        f"where id = ({chunk_ids}) "
        f"& release_dates.y >= {current_year} "
        f"& (first_release_date > {today} | first_release_date = null) "
        f"{NO_FANGAME_FILTER}; "
        f"limit 500;"
    )
    res_bb_games = requests.post(BASE_URL, headers=headers, data=query_bb_games)
    if res_bb_games.status_code == 200:
        future_blockbusters.extend(res_bb_games.json())

cleaned_bb = clean_games_data(future_blockbusters, scores_dict_bb)
future_games_with_date = []
for g in cleaned_bb:
    sort_ts = get_hybrid_sort_date(g, today, future_only=True)
    if sort_ts > today and sort_ts < 9999999999:
        g["_tmp_sort_ts"] = sort_ts
        future_games_with_date.append(g)

all_sorted_chronologically = sorted(future_games_with_date, key=lambda x: x["_tmp_sort_ts"])
cleaned_bb_sorted = all_sorted_chronologically[:100]
for g in cleaned_bb_sorted:
    if "_tmp_sort_ts" in g: del g["_tmp_sort_ts"]

save_json(cleaned_bb_sorted, "blockbusters.json")
print(f"✅ Fichier blockbusters.json généré avec {len(cleaned_bb_sorted)} hits majeurs.")

# --- CATÉGORIE 5 : Nouveaux jeux annoncés & très attendus (TBD) ---
print("\n📡 Génération : Nouvelles annonces les plus attendues (TBD récents & populaires...)")
query_tbd = (
    f"{COMMON_FIELDS} "
    f"where created_at >= {one_year_ago} "
    f"& first_release_date = null "
    f"& cover != null "
    f"& (game_type = null | game_type = (0, 8, 9, 10, 11)) "
    f"& (hypes >= 5 | follows >= 5) "
    f"& (status = null | status != (6, 7)) "
    f"{NO_FANGAME_FILTER}; "
    f"sort hypes desc; "
    f"limit 150;"
)
res = requests.post(BASE_URL, headers=headers, data=query_tbd)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())
    cleaned = [g for g in cleaned if get_best_date(g) is None]
    cleaned.sort(key=lambda x: x.get("hypes") or 0, reverse=True)
    save_json(cleaned[:100], "tbd.json")
    print(f"✅ Fichier tbd.json généré avec succès ({len(cleaned[:100])} jeux).")

print("\n🎉 Toutes les catégories ont été générées avec succès !")
