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

three_days_ago = today - (3 * 24 * 60 * 60)
seven_days_ago = today - (7 * 24 * 60 * 60)
fourteen_days_ago = today - (14 * 24 * 60 * 60)

one_month_ago = today - (30 * 24 * 60 *60)
three_months_ago = today - (90 * 24 * 60 * 60)

next_week = today + 604800 # Calcul de la limite dans 7 jours

current_year = datetime.datetime.now().year #Renvoit l'année en cours

one_year_from_now = today + (365 * 24 * 60 * 60)

# Les champs demandés sont identiques pour toutes les requêtes afin de n'avoir qu'une seule Data Class Kotlin
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
    """Aplatit et nettoie les données complexes d'IGDB pour le mobile."""
    cleaned_list = []
    
    for game in games_data:
        clean_game = {
            "id": game.get("id"),
            "name": game.get("name"),
            "cover": game.get("cover"),
            "rating": game.get("rating"),
            "first_release_date": game.get("first_release_date"),
            "hypes": game.get("hypes"),
            "status": game.get("status"), # Récupère l'ID du statut (ex: 0, 4, 7...)
            "follows": game.get("follows"), # Nombre de followers sur IGDB
            "themes": game.get("themes", []), # Liste d'IDs de thèmes (ex: [32, 1, 2...])
            "release_dates": [
                {
                    "category": rd.get("date_format", rd.get("category")), # Récupère 0 (Jour), 1 (Mois) ou 2 (Année)
                    "y": rd.get("y"),                # Récupère l'année (ex: 2027)
                    "m": rd.get("m"),                # Récupère le mois
                    "d": datetime.datetime.fromtimestamp(rd.get("date")).day if rd.get("date") else None,
                    "date": rd.get("date"),
                    "status": rd.get("status"),
                    "platform_name": rd.get("platform", {}).get("name") if isinstance(rd.get("platform"), dict) else None
                } 
                for rd in game.get("release_dates", [])
            ]
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

def get_hybrid_sort_date(game, today_ts):
    """Calcule la date de tri en privilégiant l'accès le plus tôt pour le joueur."""
    playable_dates = []
    
    # Statuts qui comptent comme une "sortie" pour un joueur
    PLAYABLE_STATUSES = {6, 34, 3} 
    
    for rd in game.get("release_dates", []):
        # On ignore les déchets (annulés/offline)
        if rd.get("status") in (4, 5): continue
        
        # On collecte les dates des versions jouables
        if rd.get("status") in PLAYABLE_STATUSES and rd.get("date"):
             if rd.get("date") >= today_ts:
                playable_dates.append(rd.get("date"))
            
    # Si on a trouvé des dates jouables, on prend la plus ancienne (souvent l'Advanced Access)
    if playable_dates:
        return min(playable_dates)
        
    # Si aucune date future n'est trouvée dans release_dates, 
    # on vérifie si first_release_date est dans le futur
    first_date = game.get("first_release_date")
    if first_date and first_date >= today_ts:
        return first_date
        
    return 9999999999

def get_best_date(game, today_ts=None):
    if today_ts is None:
        import time
        today_ts = int(time.time())
    
    res = get_hybrid_sort_date(game, today_ts)
    return res if res != 9999999999 else None

def save_json(data, filename):
    """Sauvegarde la liste dans un fichier JSON."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 {len(data)} jeux sauvegardés dans {filename}")

# ==========================================
# 4. EXÉCUTION DES CATÉGORIES
# ==========================================

# --- CATÉGORIE 1 : Les dernières sorties (Les 50 meilleurs jeux des 14 derniers jours) ---
print("\n📡 Génération : Les dernières sorties (Les 50 meilleurs jeux des 14 derniers jours, trié par popularité)...")

# Filtres :
# - Fenêtre de 7 jours (entre seven_days_ago et today)
# - cover != null : pour des jeux un peu sérieux
# - NOUVEAU TRI : sort follows desc (Les jeux les plus suivis en premier)
query_latest = (
    f"{COMMON_FIELDS} "
    # 1. On groupe les deux conditions de date dans un grand bloc
    f"where ((first_release_date >= {seven_days_ago} & first_release_date <= {today}) "
    f"| (release_dates.date >= {seven_days_ago} & release_dates.date <= {today})) "
    # 2. On impose la cover et le statut à TOUS les jeux qui sortent de ce bloc
    f"& cover != null & cover.image_id != null " 
    f"& (status = null | status != (6, 7)); "
    f"sort hypes desc; "
    f"limit 100;"
)
res = requests.post(BASE_URL, headers=headers, data=query_latest)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())[:100]
    # On ne garde que si : 
    # - La date est entre (today - 7j) et AUJOURD'HUI
    # - ET le jeu possède une jaquette (cover) avec un image_id
    cleaned = [
        g for g in cleaned 
        if get_best_date(g) and seven_days_ago <= get_best_date(g, today) <= today
        and g.get("cover") and g.get("cover").get("image_id")
            ]
    # On trie quand même par date pour la cohérence visuelle
    cleaned.sort(key=get_hybrid_sort_date, reverse=True)
    save_json(cleaned[:50], "latest.json")
    print("✅ Fichier latest.json généré avec succès.")
else:
    print(f"❌ Erreur Latest : {res.text}")

# --- CATÉGORIE 2 : Populaires actuellement (1 mois) ---
print("\n📡 Génération : Populaires actuellement...")
# Étape A : Top Primitives
query_prims = "fields game_id, value; where popularity_type = 1; sort value desc; limit 500;"
res_prims = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query_prims)

if res_prims.status_code == 200:
    scores_dict = {str(item["game_id"]): item["value"] for item in res_prims.json() if "game_id" in item}
    ids_str = ",".join(scores_dict.keys())
    
    # Étape B : Détails filtrés sur le dernier mois
    if ids_str:
        #query_popular = f"{COMMON_FIELDS} where id = ({ids_str}) & (first_release_date >= {one_month_ago} | release_dates.date >= {one_month_ago}); limit 500;"
        query_popular = f"{COMMON_FIELDS} where id = ({ids_str}) & first_release_date >= {one_month_ago} & first_release_date <= {today}; limit 500;"
        res_games = requests.post(BASE_URL, headers=headers, data=query_popular)
        
        if res_games.status_code == 200:
            cleaned = clean_games_data(res_games.json(), scores_dict)
            # Tri local par pop_score décroissant et limitation à 50
            cleaned = sorted(cleaned, key=lambda x: x.get("pop_score") or 0, reverse=True)[:50]
            save_json(cleaned, "popular.json")
            print("✅ Fichier popular.json généré avec succès.")
        else:
            print(f"❌ Erreur Popular (Games) : {res_games.text}")
else:
    print(f"❌ Erreur Popular (Primitives) : {res_prims.text}")

# --- CATÉGORIE 3 : Sorties populaires de la semaine ---
print("\n📡 Génération : Sorties populaires de la semaine...")

query_upcoming = (
    f"{COMMON_FIELDS} "
    f"where ((first_release_date > {today} & first_release_date <= {next_week}) "
    f"| (release_dates.date > {today} & release_dates.date <= {next_week})) "
    f"& release_dates.date_format = 0 " # On ne veut que des jeux avec AU MOINS une date précise
    f"& (status = null | status != (6, 7)) & hypes >= 7; "
    f"limit 500;"
)

res = requests.post(BASE_URL, headers=headers, data=query_upcoming)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())
    # FILTRE DE SÉCURITÉ : On vérifie que la date de cette semaine est bien précise
    final_upcoming = []
    for g in cleaned:
        # On cherche s'il existe une date précise (category/date_format 0) dans la fenêtre de 7 jours
        if any(rd.get("category") == 0 and rd.get("date") and today < rd.get("date") <= next_week 
               for rd in g.get("release_dates", [])):
            final_upcoming.append(g)
            
    final_upcoming.sort(key=lambda g: get_hybrid_sort_date(g, today))
    save_json(final_upcoming[:50], "upcoming.json")
else:
    print(f"❌ Erreur Upcoming : {res.text}")
    
# --- CATÉGORIE 4 : Futurs blockbusters (Les plus attendus via Popscore Type 2) ---
print("\n📡 Génération : Futurs blockbusters (Popscore - Multi-pages)...")

# Étape A : Parcourir le Top 2500 de Popscore (par pages de 500 via offset)
scores_dict_bb = {}
# On fait 5 appels pour récupérer le top 2500 historique
for offset in [0, 500, 1000, 1500, 2000]:
    query_prims = f"fields game_id, value; where popularity_type = 2; sort value desc; limit 500; offset {offset};"
    res_prims = requests.post("https://api.igdb.com/v4/popularity_primitives", headers=headers, data=query_prims)
    
    if res_prims.status_code == 200:
        for item in res_prims.json():
            if "game_id" in item:
                scores_dict_bb[str(item["game_id"])] = item["value"]
    else:
        print(f"❌ Erreur Popscore offset {offset}")

all_ids = list(scores_dict_bb.keys())
future_blockbusters = []

# Étape B : Interroger l'endpoint Games par lots (chunks) de 500 IDs
# On parcourt nos 2500 IDs en coupant par paquets de 500
for i in range(0, len(all_ids), 500):
    chunk_ids = ",".join(all_ids[i:i+500])
    
    # On applique ta condition exigeante : Date future OU Année future
    query_bb_games = (
        f"{COMMON_FIELDS} "
        f"where id = ({chunk_ids}) "
        f"& release_dates.y >= {current_year} "
        f"& (first_release_date > {today} | first_release_date = null); "
        f"limit 500;"
    )
    
    res_bb_games = requests.post(BASE_URL, headers=headers, data=query_bb_games)
    
    if res_bb_games.status_code == 200:
        future_blockbusters.extend(res_bb_games.json())
    else:
        print(f"❌ Erreur Games chunk {i} : {res_bb_games.text}")

# Étape C : Nettoyage et tri final
cleaned_bb = clean_games_data(future_blockbusters, scores_dict_bb)


# --- CORRECTION FILTRAGE STRICT PYTHON ---
# On ne garde que les jeux qui sont VRAIMENT dans le futur.
# On utilise get_best_date (ou get_hybrid_sort_date) pour vérifier la date réelle.
future_games_with_date = []
for g in cleaned_bb:
    sort_ts = get_hybrid_sort_date(g)
    if sort_ts > today and sort_ts < 9999999999:
        g["_tmp_sort_ts"] = sort_ts # On stocke le timestamp pour le tri
        future_games_with_date.append(g)
# ------------------------------------------

all_sorted_chronologically = sorted(future_games_with_date, key=lambda x: x["_tmp_sort_ts"])

cleaned_bb_sorted = all_sorted_chronologically[:50]

for g in cleaned_bb_sorted:
    if "_tmp_sort_ts" in g: del g["_tmp_sort_ts"]

save_json(cleaned_bb_sorted, "blockbusters.json")
print(f"✅ Fichier blockbusters.json généré avec {len(cleaned_bb_sorted)} hits majeurs, triés chronologiquement.")

# --- CATÉGORIE 5 : Les plus attendus sans date (TBD) ---
print("\n📡 Génération : Jeux annoncés (Les plus attendus sans date...)")

query_tbd = (
    f"{COMMON_FIELDS} "
    # 1. On ne veut QUE les jeux sans aucune date
    f"where first_release_date = null "
    
    # 2. On impose une jaquette
    f"& cover != null "
    
    # 3. FILTRE DE NOTORIÉTÉ (Exclut les petits projets)
    # On demande au moins 30 "Hypes" OU 30 "Follows"
    f"& (hypes >= 20 | follows >= 20) "
    
    # 4. SÉCURITÉ STATUT
    f"& (status = null | status != (6, 7)); "
    
    f"sort hypes desc; "
    f"limit 150;"
)

res = requests.post(BASE_URL, headers=headers, data=query_tbd)
if res.status_code == 200:
    cleaned = clean_games_data(res.json())
    # On ne garde que si : pas de date DU TOUT
    cleaned = [g for g in cleaned if get_best_date(g) is None]
    # Pour le TBD, on trie par Hype (attente) plutôt que par date
    cleaned.sort(key=lambda x: x.get("hypes") or 0, reverse=True)
    save_json(cleaned, "tbd.json")
    print("✅ Fichier tbd.json généré avec succès.")
else:
    print(f"❌ Erreur TBD : {res.text}")

print("\n🎉 Toutes les catégories ont été générées avec succès !")
