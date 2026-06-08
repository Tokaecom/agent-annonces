"""
Module topic_store.py - Déduplication thématique des alertes.

But : si plusieurs posts du flux parlent du même événement (ex: 8 posts ForexLive
sur le cessez-le-feu Iran-Israël en 10 min), on ne notifie qu'UNE seule fois,
pas 8 fois.

Mécanique :
- Chaque alerte envoyée enregistre son "topic" (déterminé par Claude) avec un timestamp.
- Avant d'envoyer une nouvelle alerte, on vérifie si le même topic a déjà été
  alerté dans les COOLDOWN_MINUTES dernières minutes.
- Si oui, on skip (déjà alerté, pas besoin de spammer).
- Si non, on envoie et on marque le topic.

Stockage : data/recent_topics.json
Format : { "topic_id": "ISO timestamp UTC", ... }
"""

import json
import os
from datetime import datetime, timedelta, timezone

# Cooldown : combien de minutes sans réalerter sur le même topic
COOLDOWN_MINUTES = 30

# Chemin du fichier de mémoire
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
TOPICS_FILE = os.path.join(DATA_DIR, "recent_topics.json")


def _load_topics() -> dict:
    """Charge le fichier de topics récents. Retourne un dict {topic: ISO timestamp}."""
    if not os.path.exists(TOPICS_FILE):
        return {}
    try:
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"   [topic_store] Avertissement : impossible de lire {TOPICS_FILE} ({e}). On repart de zéro.")
        return {}


def _save_topics(topics: dict) -> None:
    """Sauvegarde le dict de topics dans le fichier JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f, indent=2, ensure_ascii=False)


def _prune_old_topics(topics: dict) -> dict:
    """Supprime les topics expirés (> COOLDOWN_MINUTES). Évite que le fichier grossisse à l'infini."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=COOLDOWN_MINUTES)
    pruned = {}
    for topic, ts_str in topics.items():
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts > cutoff:
                pruned[topic] = ts_str
        except ValueError:
            # Timestamp mal formé, on le drop
            continue
    return pruned


def is_topic_recently_alerted(topic: str) -> bool:
    """
    Retourne True si le topic a déjà été alerté dans les COOLDOWN_MINUTES dernières minutes.
    Sinon retourne False (on peut envoyer une nouvelle alerte sur ce topic).

    Convention : si topic est "other" ou vide, on retourne toujours False
    (pas de déduplication sur le bucket fourre-tout).
    """
    if not topic or topic == "other":
        return False

    topics = _load_topics()
    if topic not in topics:
        return False

    try:
        last_ts = datetime.fromisoformat(topics[topic])
    except ValueError:
        return False

    now = datetime.now(timezone.utc)
    delta = now - last_ts
    return delta < timedelta(minutes=COOLDOWN_MINUTES)


def mark_topic_alerted(topic: str) -> None:
    """
    Marque un topic comme alerté MAINTENANT (timestamp UTC actuel).
    Au passage, supprime les topics expirés du fichier pour qu'il reste petit.
    """
    if not topic:
        return

    topics = _load_topics()
    topics = _prune_old_topics(topics)
    topics[topic] = datetime.now(timezone.utc).isoformat()
    _save_topics(topics)


def get_recent_topics_summary() -> str:
    """
    Utilitaire de debug : retourne un résumé des topics actuellement en cooldown.
    Utile pour les logs.
    """
    topics = _prune_old_topics(_load_topics())
    if not topics:
        return "aucun"
    parts = []
    now = datetime.now(timezone.utc)
    for topic, ts_str in topics.items():
        try:
            ts = datetime.fromisoformat(ts_str)
            elapsed = int((now - ts).total_seconds() / 60)
            parts.append(f"{topic} (il y a {elapsed} min)")
        except ValueError:
            continue
    return ", ".join(parts)
