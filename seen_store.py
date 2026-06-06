"""
Module seen_store.py - Mémoire partagée des IDs déjà traités.

Centralise la logique de persistance pour TOUTES les sources de l'agent
(Trump Truth Social, ForexLive, futures Powell/Lagarde, etc.).

Chaque source a son propre fichier JSON dans data/, ce qui évite de
mélanger les IDs entre sources (un GUID ForexLive ne risque pas d'être
confondu avec un GUID Trump).

Convention de nommage : data/seen_<source_id>.json
  - data/seen_posts.json     → Trump (legacy, conservé pour ne pas casser la prod)
  - data/seen_forexlive.json → ForexLive
  - data/seen_powell.json    → futures sources
"""

import json
import os

# Chemin du dossier data/ relatif à ce fichier
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")


def get_seen_file_path(filename: str) -> str:
    """
    Construit le chemin complet d'un fichier de mémoire dans data/.
    Accepte juste le nom de fichier (ex: 'seen_forexlive.json').
    """
    return os.path.join(DATA_DIR, filename)


def load_seen_ids(filename: str) -> list:
    """
    Charge la liste des IDs déjà traités depuis un fichier JSON.
    Si le fichier n'existe pas (premier run pour cette source), retourne [].
    En cas d'erreur de lecture, on log un warning et on repart de zéro.
    """
    path = get_seen_file_path(filename)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Avertissement : impossible de lire {path} ({e})")
        print("On repart de zéro pour cette source.")
        return []


def save_seen_ids(filename: str, ids: list) -> None:
    """
    Sauvegarde la liste des IDs déjà traités dans un fichier JSON.
    Crée le dossier data/ si besoin.
    """
    path = get_seen_file_path(filename)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2, ensure_ascii=False)
