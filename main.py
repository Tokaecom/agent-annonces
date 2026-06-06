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
from seen_store import load_seen_ids, save_seen_ids
import fetch_truth
import fetch_forexlive

# feedparser pour parser le RSS directement dans main.py
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

# Pré-filtre côté script (V1.1) : un post < MIN_POST_LENGTH chars est
# considéré comme inanalysable (RT vide, post juste un lien, etc.) et
# n'est PAS envoyé à Claude. Économie de tokens (~30-50 % sur Trump).
MIN_POST_LENGTH = 50

# Vérifications de sécurité au démarrage
if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("COLLE_ICI"):
    print("ERREUR : TELEGRAM_BOT_TOKEN n'est pas configuré dans .env")
    sys.exit(1)

if not TELEGRAM_CHAT_ID:
    print("ERREUR : TELEGRAM_CHAT_ID n'est pas configuré dans .env")
    sys.exit(1)


# ============================================================
# 2.bis. CATALOGUE DES SOURCES
# ============================================================
# Pour ajouter une nouvelle source (Powell, Lagarde, BCE...), il suffit
# d'ajouter un dict ici. Les modules fetch_*.py exposent juste RSS_URL
# et SEEN_FILE, ce qui rend l'ajout d'une source ultra rapide.
SOURCES = [
    {
        "name": "Trump Truth Social",
        "rss_url": fetch_truth.RSS_URL,
        "seen_file": fetch_truth.SEEN_FILE,
        "telegram_label": "📢 Trump Truth Social",
    },
    {
        "name": "ForexLive",
        "rss_url": fetch_forexlive.RSS_URL,
        "seen_file": fetch_forexlive.SEEN_FILE,
        "telegram_label": "📢 ForexLive",
    },
]


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

def format_alert_message(post_entry, analysis: dict, source_label: str) -> str:
    """
    Construit le message Telegram à partir du post original et de l'analyse Claude.
    Format spec V1 validé le 02/06/2026.

    post_entry : objet du flux RSS (avec .summary, .link, .published, etc.)
    analysis : dict retourné par analyze_post() (contient is_relevant, reason, etc.)
    source_label : nom de la source pour le header Telegram (ex: "📢 ForexLive")
    """
    # Extraction des champs du post RSS avec defaults safe
    # Sur ForexLive, le titre est plus informatif que le summary (qui peut être tronqué).
    title = getattr(post_entry, "title", "")
    summary_text = getattr(post_entry, "summary", "")
    verbatim = title if title else (summary_text if summary_text else "(contenu vide)")
    link = getattr(post_entry, "link", "")
    published = getattr(post_entry, "published", "(date inconnue)")

    # Extraction des champs de l'analyse Claude
    summary = analysis.get("summary_for_telegram", "(résumé non disponible)")
    impact_eurusd = analysis.get("impact_eurusd", "n_a")
    impact_nasdaq = analysis.get("impact_nasdaq", "n_a")
    key_levels = analysis.get("key_levels_to_watch", "(non précisé)")
    reason = analysis.get("reason", "")

    # Construction du message (format spec V1)
    message = f"""{source_label} — {published}

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
# 4.bis. PRE-FILTRAGE POSTS COURTS (V1.1)
# ============================================================

def is_post_worth_analyzing(post_text: str) -> bool:
    """
    Retourne True si le post mérite d'être envoyé à Claude.
    Filtre côté script pour économiser des tokens API sur les posts vides
    ou trop courts (RT sans texte, juste un lien, etc.).

    Le seuil MIN_POST_LENGTH = 50 chars est calibré pour laisser passer
    les courtes annonces utiles (ex: "BCE relève taux à 4 %") tout en
    bloquant les RT vides et les emojis isolés.
    """
    if not post_text:
        return False
    if len(post_text.strip()) < MIN_POST_LENGTH:
        return False
    return True


# ============================================================
# 5. TRAITEMENT D'UNE SOURCE (un cycle pour une source donnée)
# ============================================================

def process_source(source: dict) -> dict:
    """
    Effectue un cycle complet POUR UNE SOURCE :
      1. Récupère le flux RSS de la source
      2. Identifie les nouveaux posts
      3. Pré-filtre les posts trop courts (économie tokens Claude)
      4. Pour chaque nouveau gardé : analyse Claude + envoi Telegram si pertinent
      5. Marque tous les posts du flux comme vus pour cette source

    source : dict avec les clés 'name', 'rss_url', 'seen_file', 'telegram_label'

    Retourne un dict de stats pour le log final.
    """
    stats = {
        "new_posts": 0,
        "skipped_short": 0,
        "relevant": 0,
        "telegram_sent": 0,
        "errors": 0,
    }

    name = source["name"]
    rss_url = source["rss_url"]
    seen_file = source["seen_file"]
    telegram_label = source["telegram_label"]

    print(f"\n   ── Source : {name} ──")

    # Étape 1 : récupération du flux RSS
    try:
        feed = feedparser.parse(rss_url)
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
    seen_ids = load_seen_ids(seen_file)
    is_first_run = len(seen_ids) == 0
    new_entries = [e for e in feed.entries if e.get("id") not in seen_ids]

    stats["new_posts"] = len(new_entries)

    # Cas spécial premier run : on marque tout comme vu sans analyser.
    # Sinon on enverrait potentiellement des dizaines d'alertes d'un coup !
    if is_first_run:
        print(f"   [PREMIER RUN {name}] {len(feed.entries)} posts dans le flux, tous marqués vus.")
        print(f"   Aucune analyse ni alerte. Les vrais nouveaux posts seront traités au prochain cycle.")
        all_ids = [e.get("id") for e in feed.entries if e.get("id")]
        save_seen_ids(seen_file, all_ids)
        return stats

    if not new_entries:
        print("   Aucun nouveau post.")
        return stats

    # Étape 3 : analyse de chaque nouveau post
    for entry in new_entries:
        # Combine title + summary pour avoir le maximum de contexte texte.
        # Sur ForexLive, le titre est souvent l'info principale.
        title = getattr(entry, "title", "")
        summary_text = getattr(entry, "summary", "")
        post_text = f"{title}\n\n{summary_text}".strip()

        # Pré-filtre côté script : skip les posts trop courts (V1.1)
        if not is_post_worth_analyzing(post_text):
            stats["skipped_short"] += 1
            continue

        print(f"\n   ➡️  Nouveau post détecté ({getattr(entry, 'published', '?')})")
        print(f"       Extrait : {post_text[:120].replace(chr(10), ' ')}...")

        # Appel à Claude avec le nom de la source pour qu'il s'adapte au format
        try:
            analysis = analyze_post(post_text, source_name=name)
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
            message = format_alert_message(entry, analysis, telegram_label)
            if send_telegram(message):
                stats["telegram_sent"] += 1
                print("       ✅ Alerte Telegram envoyée.")
            else:
                stats["errors"] += 1
                print("       ❌ Envoi Telegram échoué.")
        else:
            print(f"       💤 Non pertinent : {analysis.get('reason')}")

    # Étape 4 : marquage de TOUS les posts du flux comme vus pour cette source
    all_current_ids = [e.get("id") for e in feed.entries if e.get("id")]
    updated_seen = list(set(seen_ids + all_current_ids))
    save_seen_ids(seen_file, updated_seen)

    return stats


def process_cycle() -> dict:
    """
    Effectue un cycle complet sur TOUTES les sources configurées.
    Agrège les stats de chaque source pour le log final.
    """
    global_stats = {
        "new_posts": 0,
        "skipped_short": 0,
        "relevant": 0,
        "telegram_sent": 0,
        "errors": 0,
    }

    for source in SOURCES:
        try:
            source_stats = process_source(source)
        except Exception as e:
            # Filet de sécurité : si une source plante, on passe aux autres
            print(f"   [SOURCE {source['name']} ERREUR INATTENDUE] {e}")
            global_stats["errors"] += 1
            continue

        # Agrégation des stats
        for key, value in source_stats.items():
            global_stats[key] = global_stats.get(key, 0) + value

    return global_stats


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
    print(f" Sources surveillées ({len(SOURCES)}) :")
    for src in SOURCES:
        print(f"   - {src['name']} → {src['rss_url']}")
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
                f"\n   ↳ Bilan global cycle : {stats['new_posts']} nouveau(x), "
                f"{stats['skipped_short']} skippé(s) court(s), "
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
