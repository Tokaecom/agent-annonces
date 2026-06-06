"""
Script fetch_forexlive.py - Source ForexLive (InvestingLive depuis 2025).

ForexLive (renommé InvestingLive après rachat) publie en continu :
  - Analyses techniques EUR/USD et autres paires majeures
  - Réactions marché aux annonces macro (NFP, CPI, décisions Fed/BCE)
  - News politique monétaire (Powell, Lagarde, BCE, BoJ)
  - Géopolitique avec impact marchés (Iran, Chine, Russie)
  - News pétrole / commodities

C'est une source NETTEMENT plus dense que Trump : ratio signal/bruit
beaucoup plus élevé, mais avec un volume aussi plus important
(plusieurs dizaines de posts/jour). Le filtre Claude reste indispensable.

Le flux RSS est public et ne demande pas d'authentification.

Pour tester en standalone : python fetch_forexlive.py
(depuis le venv activé)
"""

import feedparser
import sys
from datetime import datetime

from seen_store import load_seen_ids, save_seen_ids

# Encoding UTF-8 force pour la console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# URL du flux RSS principal de ForexLive (= InvestingLive)
# Note : forexlive.com/feed redirige (301) vers investinglive.com/feed
# On utilise directement l'URL cible pour éviter le redirect.
RSS_URL = "https://investinglive.com/feed/"

# Nom du fichier de mémoire des posts déjà vus pour CETTE source.
# Géré par seen_store.py qui ajoute le préfixe data/ automatiquement.
SEEN_FILE = "seen_forexlive.json"

# Combien de posts on affiche au premier run en standalone
FIRST_RUN_DISPLAY = 5


def format_post(entry) -> str:
    """Formate un post ForexLive pour affichage console lisible."""
    date_str = getattr(entry, "published", "(date inconnue)")
    title = getattr(entry, "title", "(titre vide)")
    summary = getattr(entry, "summary", "")
    link = getattr(entry, "link", "(pas de lien)")
    creator = getattr(entry, "author", "(auteur inconnu)")
    category = getattr(entry, "tags", [{}])[0].get("term", "Général") if hasattr(entry, "tags") else "Général"

    # Le summary peut contenir du HTML. On garde brut, l'analyse Claude saura gérer.
    return (
        f"\n{'=' * 70}\n"
        f"📢 {date_str} — {creator} [{category}]\n"
        f"{'-' * 70}\n"
        f"{title}\n\n"
        f"{summary[:400]}{'...' if len(summary) > 400 else ''}\n\n"
        f"🔗 {link}\n"
    )


def main():
    """Test standalone : affiche les nouveaux posts de ForexLive."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Récupération du flux ForexLive...")

    feed = feedparser.parse(RSS_URL)

    if feed.bozo and not feed.entries:
        print(f"ERREUR : impossible de récupérer le flux ({feed.bozo_exception})")
        sys.exit(1)

    if not feed.entries:
        print("Le flux est vide. Réessaye plus tard.")
        return

    print(f"Flux récupéré : {len(feed.entries)} posts disponibles.")

    seen_ids = load_seen_ids(SEEN_FILE)
    is_first_run = len(seen_ids) == 0

    if is_first_run:
        print(f"\n*** PREMIER RUN ForexLive détecté ***")
        print(f"Affichage des {FIRST_RUN_DISPLAY} posts les plus récents,")
        print("puis on marque tout comme 'vu' pour ne pas spammer aux prochains runs.\n")

    new_entries = [e for e in feed.entries if e.get("id") not in seen_ids]

    if not new_entries:
        print("Aucun nouveau post depuis le dernier check.")
        return

    if is_first_run:
        to_display = new_entries[:FIRST_RUN_DISPLAY]
    else:
        to_display = new_entries
        print(f"\n🚨 {len(to_display)} NOUVEAU(X) POST(S) ForexLive détecté(s) :")

    for entry in to_display:
        print(format_post(entry))

    # Marque tous les posts du flux comme vus (même non affichés au premier run)
    all_current_ids = [e.get("id") for e in feed.entries if e.get("id")]
    updated_seen = list(set(seen_ids + all_current_ids))
    save_seen_ids(SEEN_FILE, updated_seen)

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Mémoire mise à jour : {len(updated_seen)} posts ForexLive marqués vus.")


if __name__ == "__main__":
    main()
