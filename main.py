"""
Script main.py - Pipeline complet de l'agent IA annonces.

But : assembler les 3 briques (récupération RSS + analyse Claude + envoi Telegram)
en un pipeline complet qui peut tourner soit en boucle locale, soit en mode one-shot.

Pipeline complet par cycle :
  1. Récupère le flux RSS Trump (via fonctions importées de fetch_truth.py)
  2. Pour chaque nouveau post détecté :
     a. Envoie le texte à Claude pour analyse (via fonction importée de analyze_post.py)
     b. Si Claude répond is_relevant=true :
        → Construit le message Telegram au format spec V1
        → Envoie via API Telegram
     c. Marque le post comme vu (pertinent ou non, pour ne pas le re-traiter)
  3. Affiche un log compact du cycle
  4. Si mode boucle : attend 5 minutes puis reboucle
     Si mode one-shot (--once) : exit après le cycle

Deux modes d'exécution :
  - python main.py          → boucle infinie (mode local de debug, Ctrl+C pour arrêter)
  - python main.py --once   → un seul cycle puis exit (mode prod via GitHub Actions)
"""

# ============================================================
# 1. IMPORTS
# ============================================================
# Imports standard Python
import os
import sys
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

# Imports depuis nos propres scripts (réutilisation de code !)
# Note : ces imports n'exécutent PAS le main() des scripts, parce qu'on a
# protégé chaque main() avec `if __name__ == "__main__":`.
# On récupère uniquement les fonctions dont on a besoin.
from analyze_post import analyze_post
from fetch_truth import load_seen_ids, save_seen_ids, RSS_URL

# feedparser pour parser le RSS directement dans main.py (plutôt que de re-importer
# toute la logique main() de fetch_truth.py qui contient de l'affichage console)
import feedparser

# Force l'encoding UTF-8 sur la sortie console.
# Indispensable sur Windows à cause des emojis.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# 2. CONFIGURATION
# ============================================================
# Chargement du .env pour les secrets (token Telegram + clé API Claude
# est déjà chargée par analyze_post.py au moment de l'import).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"), override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Fréquence de polling du flux RSS, en secondes.
# 5 minutes = 300 secondes. Bon équilibre réactivité / charge serveur.
POLL_INTERVAL_SECONDS = 5 * 60

# Vérifications de sécurité au démarrage
if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("COLLE_ICI"):
    print("ERREUR : TELEGRAM_BOT_TOKEN n'est pas configuré dans .env")
    sys.exit(1)

if not TELEGRAM_CHAT_ID:
    print("ERREUR : TELEGRAM_CHAT_ID n'est pas configuré dans .env")
    sys.exit(1)


# ============================================================
# 3. FONCTION D'ENVOI TELEGRAM
# ============================================================
# Réutilise la logique de hello_telegram.py mais en version fonction réutilisable.
# On accepte un paramètre `parse_mode` pour pouvoir envoyer du Markdown plus tard si besoin.

def send_telegram(text: str) -> bool:
    """
    Envoie un message Telegram via l'API du bot.
    Retourne True si succès, False sinon.

    Note : Telegram limite chaque message à 4096 caractères max.
    Notre format spec V1 fait ~600-1000 caractères, on est large.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        # disable_web_page_preview évite que Telegram génère un aperçu
        # encombrant du lien Truth Social en bas du message.
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200 and response.json().get("ok"):
            return True
        else:
            print(f"   [Telegram KO] {response.status_code} : {response.text[:200]}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"   [Telegram ERREUR réseau] {e}")
        return False


# ============================================================
# 4. FORMATAGE DU MESSAGE D'ALERTE (format spec V1)
# ============================================================

def format_alert_message(post_entry, analysis: dict) -> str:
    """
    Construit le message Telegram à partir du post original et de l'analyse Claude.
    Format spec V1 validé le 02/06/2026.

    post_entry : objet du flux RSS (avec .summary, .link, .published, etc.)
    analysis : dict retourné par analyze_post() (contient is_relevant, reason, etc.)
    """
    # Extraction des champs du post RSS avec defaults safe
    verbatim = getattr(post_entry, "summary", "(contenu vide)")
    link = getattr(post_entry, "link", "")
    published = getattr(post_entry, "published", "(date inconnue)")

    # Extraction des champs de l'analyse Claude
    summary = analysis.get("summary_for_telegram", "(résumé non disponible)")
    impact_eurusd = analysis.get("impact_eurusd", "n_a")
    impact_nasdaq = analysis.get("impact_nasdaq", "n_a")
    key_levels = analysis.get("key_levels_to_watch", "(non précisé)")
    reason = analysis.get("reason", "")

    # Construction du message (format spec V1)
    message = f"""📢 Trump Truth Social — {published}

"{verbatim}"

💡 Contexte : {reason}

📊 Marchés impactés :
  • EUR/USD : {impact_eurusd}
  • NASDAQ : {impact_nasdaq}

🎯 Niveaux à surveiller : {key_levels}

📝 Résumé : {summary}

⚠️ Reminder discipline : SL placé AVANT entry, jamais déplacé. Si SL touché, on prend la perte et on ferme.

🔗 {link}"""

    return message


# ============================================================
# 5. TRAITEMENT D'UN CYCLE (un poll RSS)
# ============================================================

def process_cycle() -> dict:
    """
    Effectue un cycle complet :
      1. Récupère le flux RSS
      2. Identifie les nouveaux posts
      3. Pour chaque nouveau : analyse Claude + envoi Telegram si pertinent
      4. Marque tous les posts du flux comme vus

    Retourne un dict de stats pour le log final.
    """
    stats = {
        "new_posts": 0,
        "relevant": 0,
        "telegram_sent": 0,
        "errors": 0,
    }

    # Étape 1 : récupération du flux RSS
    try:
        feed = feedparser.parse(RSS_URL)
    except Exception as e:
        print(f"   [RSS ERREUR] {e}")
        stats["errors"] += 1
        return stats

    if feed.bozo and not feed.entries:
        print(f"   [RSS ERREUR] Flux invalide ({feed.bozo_exception})")
        stats["errors"] += 1
        return stats

    if not feed.entries:
        print("   [RSS] Flux vide.")
        return stats

    # Étape 2 : identification des nouveaux posts
    seen_ids = load_seen_ids()
    is_first_run = len(seen_ids) == 0
    new_entries = [e for e in feed.entries if e.get("id") not in seen_ids]

    stats["new_posts"] = len(new_entries)

    # Cas spécial premier run : on marque tout comme vu sans analyser.
    # Sinon on enverrait potentiellement 100 alertes Telegram d'un coup !
    if is_first_run:
        print(f"   [PREMIER RUN] {len(feed.entries)} posts dans le flux, tous marqués comme vus.")
        print("   Aucune analyse ni alerte. Les vrais nouveaux posts seront traités au prochain cycle.")
        all_ids = [e.get("id") for e in feed.entries if e.get("id")]
        save_seen_ids(all_ids)
        return stats

    if not new_entries:
        print("   Aucun nouveau post.")
        return stats

    # Étape 3 : analyse de chaque nouveau post
    for entry in new_entries:
        post_text = getattr(entry, "summary", "") or getattr(entry, "title", "")
        if not post_text:
            print("   [SKIP] Post vide, ignoré.")
            continue

        print(f"\n   ➡️  Nouveau post détecté ({getattr(entry, 'published', '?')})")
        print(f"       Extrait : {post_text[:120]}...")

        # Appel à Claude
        try:
            analysis = analyze_post(post_text)
        except Exception as e:
            print(f"       [Claude ERREUR] {e}")
            stats["errors"] += 1
            continue

        if "error" in analysis:
            print(f"       [Claude parsing KO] {analysis.get('error')}")
            stats["errors"] += 1
            continue

        if analysis.get("is_relevant"):
            stats["relevant"] += 1
            print(f"       🚨 PERTINENT : {analysis.get('reason')}")

            # Construction et envoi du message Telegram
            message = format_alert_message(entry, analysis)
            if send_telegram(message):
                stats["telegram_sent"] += 1
                print("       ✅ Alerte Telegram envoyée.")
            else:
                stats["errors"] += 1
                print("       ❌ Envoi Telegram échoué.")
        else:
            print(f"       💤 Non pertinent : {analysis.get('reason')}")

    # Étape 4 : marquage de TOUS les posts du flux comme vus
    # (même les non pertinents, pour ne pas les ré-analyser au prochain cycle)
    all_current_ids = [e.get("id") for e in feed.entries if e.get("id")]
    updated_seen = list(set(seen_ids + all_current_ids))
    save_seen_ids(updated_seen)

    return stats


# ============================================================
# 6. BOUCLE PRINCIPALE
# ============================================================

def main():
    # Mode "--once" : un seul cycle puis exit. Utilisé par GitHub Actions
    # qui se charge lui-même de la périodicité via cron.
    # Sans flag : boucle infinie comme avant, utile en local pour le debug.
    run_once = "--once" in sys.argv

    print("=" * 70)
    print(" Agent IA Annonces Trading - Pipeline complet")
    print("=" * 70)
    if run_once:
        print(" Mode : ONE-SHOT (un seul cycle, puis exit)")
    else:
        print(f" Mode : BOUCLE (polling toutes les {POLL_INTERVAL_SECONDS // 60} min)")
    print(f" Source : {RSS_URL}")
    print(f" Telegram chat : {TELEGRAM_CHAT_ID}")
    if not run_once:
        print(" Ctrl+C pour arrêter.")
    print("=" * 70)

    cycle_count = 0

    while True:
        cycle_count += 1
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n[Cycle #{cycle_count} - {now}]")

        try:
            stats = process_cycle()
            print(
                f"   ↳ Bilan : {stats['new_posts']} nouveau(x), "
                f"{stats['relevant']} pertinent(s), "
                f"{stats['telegram_sent']} Telegram envoyé(s), "
                f"{stats['errors']} erreur(s)."
            )
        except Exception as e:
            # Filet de sécurité : si une exception inattendue casse le cycle,
            # on log et on continue. L'agent ne doit JAMAIS crasher silencieusement.
            print(f"   [CYCLE ERREUR INATTENDUE] {e}")

        # Mode one-shot : on sort proprement après un seul cycle.
        if run_once:
            print("\n✅ Cycle one-shot terminé. Exit.")
            sys.exit(0)

        # Mode boucle : attente jusqu'au prochain cycle
        print(f"   💤 Attente {POLL_INTERVAL_SECONDS // 60} min jusqu'au prochain cycle...")
        try:
            time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n\n🛑 Arrêt demandé par l'utilisateur (Ctrl+C). À plus, Nathan.")
            sys.exit(0)


# ============================================================
# 7. POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    main()
