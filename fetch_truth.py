"""
Script fetch_truth.py - Étape 2 du projet agent IA annonces.

But : récupérer les derniers posts de Trump sur Truth Social via le flux
RSS de trumpstruth.org, détecter les NOUVEAUX posts (ceux qu'on n'a pas
encore vus) et les afficher dans la console.

Pour l'instant, on n'envoie rien sur Telegram. Le pipeline complet
(récupération + analyse Claude + envoi Telegram) sera assemblé à l'étape 4.

Lance ce script avec : python fetch_truth.py
(depuis le venv activé)
"""

# ============================================================
# 1. IMPORTS
# ============================================================

import feedparser
import sys
from datetime import datetime

# Fonctions de mémoire (seen_ids) déléguées au module partagé seen_store.
# Ça évite la duplication entre fetch_truth.py et fetch_forexlive.py.
from seen_store import load_seen_ids, save_seen_ids

# Force l'encoding UTF-8 sur la sortie console.
# Sans ça, les emojis (📢, 🔗, etc.) plantent sur Windows (console cp1252 par défaut).
# C'est un grand classique des scripts Python sur Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# 2. CONSTANTES (configurations du script)
# ============================================================
# URL du flux RSS public maintenu par Defending Democracy Together.
# Ce flux agrège TOUS les posts de Trump sur Truth Social.
RSS_URL = "https://www.trumpstruth.org/feed"

# Nom du fichier de mémoire pour CETTE source.
# seen_store ajoute le préfixe data/ automatiquement.
SEEN_FILE = "seen_posts.json"

# Combien de posts on affiche au premier run (pour ne pas spammer la console).
FIRST_RUN_DISPLAY = 5


def format_post(entry):
    """
    Formate un post RSS pour affichage console lisible.
    Les champs RSS varient un peu selon les flux, on prend ce qui existe.
    """
    # Date : on essaie d'avoir un format propre, sinon on prend brut
    if hasattr(entry, "published"):
        date_str = entry.published
    else:
        date_str = "(date inconnue)"

    # Titre / résumé : selon les flux, le contenu peut être dans .title,
    # .summary, .description, etc. trumpstruth.org met le texte dans summary.
    if hasattr(entry, "summary"):
        text = entry.summary
    elif hasattr(entry, "title"):
        text = entry.title
    else:
        text = "(contenu vide)"

    # Lien vers le post original sur Truth Social
    link = getattr(entry, "link", "(pas de lien)")

    return f"\n{'=' * 70}\n📢 {date_str}\n{'-' * 70}\n{text}\n\n🔗 {link}\n"


# ============================================================
# 4. PROGRAMME PRINCIPAL
# ============================================================

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Récupération du flux RSS Trump...")

    # Étape 1 : on parse le flux RSS
    feed = feedparser.parse(RSS_URL)

    # Vérification basique : le flux a bien été récupéré
    if feed.bozo and not feed.entries:
        print(f"ERREUR : impossible de récupérer le flux ({feed.bozo_exception})")
        sys.exit(1)

    if not feed.entries:
        print("Le flux est vide. Réessaye plus tard.")
        return

    print(f"Flux récupéré : {len(feed.entries)} posts disponibles dans le flux.")

    # Étape 2 : on charge l'historique des posts déjà vus
    seen_ids = load_seen_ids(SEEN_FILE)
    is_first_run = len(seen_ids) == 0

    if is_first_run:
        print(f"\n*** PREMIER RUN détecté ***")
        print(f"Affichage des {FIRST_RUN_DISPLAY} posts les plus récents,")
        print("puis on marque tout comme 'vu' pour ne pas spammer aux prochains runs.\n")

    # Étape 3 : on identifie les nouveaux posts (= ceux dont l'ID n'est pas dans seen_ids)
    new_entries = [e for e in feed.entries if e.get("id") not in seen_ids]

    if not new_entries:
        print("Aucun nouveau post depuis le dernier check.")
        return

    # Étape 4 : on affiche les nouveaux
    if is_first_run:
        # Au premier run, on affiche seulement les N plus récents
        to_display = new_entries[:FIRST_RUN_DISPLAY]
    else:
        # Aux runs suivants, on affiche TOUS les vrais nouveaux
        to_display = new_entries
        print(f"\n🚨 {len(to_display)} NOUVEAU(X) POST(S) détecté(s) :")

    for entry in to_display:
        print(format_post(entry))

    # Étape 5 : on marque TOUS les posts du flux actuel comme vus
    # (même ceux qu'on n'a pas affichés au premier run, pour ne pas les
    # ressortir comme "nouveaux" au prochain run)
    all_current_ids = [e.get("id") for e in feed.entries if e.get("id")]

    # On fusionne avec l'historique existant, sans doublons
    updated_seen = list(set(seen_ids + all_current_ids))
    save_seen_ids(SEEN_FILE, updated_seen)

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Mémoire mise à jour : {len(updated_seen)} posts marqués comme vus au total.")


# ============================================================
# 5. POINT D'ENTRÉE
# ============================================================
# La convention Python : ce bloc s'exécute seulement si on lance
# directement le script (python fetch_truth.py), pas si on l'importe
# depuis un autre script.

if __name__ == "__main__":
    main()
