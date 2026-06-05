"""
Script "Hello Nathan" - Étape 1 du projet agent IA annonces.

But : envoyer un message Telegram pour valider que la chaîne complète
(code Python → API Telegram → ton compte) fonctionne.

Lance ce script avec : python hello_telegram.py
(depuis le venv activé)
"""

# ============================================================
# 1. IMPORTS
# ============================================================
# Les imports chargent les bibliothèques dont on a besoin.
# - 'os' : pour lire les variables d'environnement
# - 'sys' : pour quitter le script proprement si erreur
# - 'requests' : pour faire des requêtes HTTP (vers l'API Telegram)
# - 'dotenv' : pour lire le fichier .env automatiquement

import os
import sys
import requests
from dotenv import load_dotenv


# ============================================================
# 2. CHARGEMENT DES SECRETS DEPUIS .env
# ============================================================
# load_dotenv() lit le fichier .env et rend ses variables
# accessibles via os.getenv("NOM_DE_LA_VARIABLE").
# C'est la bonne pratique : le code ne contient JAMAIS de secret en dur.

# override=True force la priorité du .env sur les variables système.
# Sans ça, si une variable du même nom existe (même vide), load_dotenv()
# ne la surcharge pas. SCRIPT_DIR force le bon chemin peu importe le CWD.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"), override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# 3. VÉRIFICATIONS DE SÉCURITÉ
# ============================================================
# On vérifie que les secrets sont bien chargés AVANT de tenter
# l'appel. Si on oublie ça, on aura une erreur cryptique plus tard.

if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("COLLE_ICI"):
    print("ERREUR : TELEGRAM_BOT_TOKEN n'est pas configuré dans .env")
    print("Édite le fichier .env et remplace la valeur par ton vrai token.")
    sys.exit(1)

if not TELEGRAM_CHAT_ID:
    print("ERREUR : TELEGRAM_CHAT_ID n'est pas configuré dans .env")
    sys.exit(1)


# ============================================================
# 4. CONSTRUCTION DE LA REQUÊTE
# ============================================================
# L'API Telegram pour envoyer un message s'utilise via une URL
# de la forme : https://api.telegram.org/bot<TOKEN>/sendMessage
# avec un POST contenant chat_id et text.
# Doc officielle : https://core.telegram.org/bots/api#sendmessage

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": "Hello Nathan, ton agent IA annonces est en vie. Étape 1 validée.",
}


# ============================================================
# 5. ENVOI DE LA REQUÊTE
# ============================================================
# requests.post(...) envoie la requête HTTP et attend la réponse.
# On capture la réponse pour vérifier qu'elle est OK (code 200).

print("Envoi du message vers Telegram en cours...")

try:
    response = requests.post(url, json=payload, timeout=10)
except requests.exceptions.RequestException as e:
    print(f"ERREUR réseau : {e}")
    sys.exit(1)


# ============================================================
# 6. ANALYSE DE LA RÉPONSE
# ============================================================
# Si Telegram répond avec un code 200 et ok=True, c'est bon.
# Sinon, on affiche l'erreur retournée par Telegram.

if response.status_code == 200 and response.json().get("ok"):
    print("Message envoyé avec succès.")
    print("Va voir ton Telegram, tu dois avoir reçu 'Hello Nathan' de ton bot.")
else:
    print(f"ERREUR : Telegram a répondu avec le code {response.status_code}")
    print(f"Détails : {response.text}")
    sys.exit(1)
