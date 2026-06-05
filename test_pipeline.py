"""
Script test_pipeline.py - Test end-to-end de l'agent IA annonces.

But : simuler un post Trump pertinent et faire passer ce post à travers
tout le pipeline (Claude analyse → format message → envoi Telegram), SANS
toucher au flux RSS réel ni au fichier seen_posts.json.

Ce script sert uniquement à valider que la plomberie complète fonctionne
AVANT de lancer main.py en condition réelle.

Lance avec : python test_pipeline.py
(depuis le venv activé)

Si tout va bien : tu reçois un message Telegram avec [TEST] dans le titre,
au format spec V1 complet. Ne le confonds pas avec une vraie alerte.
"""

# ============================================================
# 1. IMPORTS
# ============================================================
# On importe les fonctions qu'on a déjà créées dans main.py et analyze_post.py.
# Pas besoin de réécrire du code, on réutilise !
import sys
from types import SimpleNamespace
from main import send_telegram, format_alert_message
from analyze_post import analyze_post

# Encoding UTF-8 console (Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# 2. FAUX POST TRUMP (réaliste et pertinent)
# ============================================================
# On crée un objet qui imite la structure d'une entrée du flux RSS.
# SimpleNamespace permet de créer un objet avec des attributs (.summary, .link, etc.)
# en une ligne, sans définir de classe.
#
# Le post simulé : une annonce Trump réaliste avec un impact macro évident,
# pour que Claude réponde is_relevant=true et qu'on teste tout le pipeline.

fake_post = SimpleNamespace(
    summary=(
        "[TEST AGENT IA] BREAKING : Iran has just announced the complete closure "
        "of the Strait of Hormuz starting tomorrow morning. The United States will "
        "respond with overwhelming military force if our ships are not allowed to "
        "pass freely. This is unacceptable and will not stand. President DONALD J. TRUMP"
    ),
    link="https://truthsocial.com/test/fake-post-for-pipeline-validation",
    published="(POST DE TEST - simulation)",
    id="test-pipeline-fake-id-do-not-store",
)


# ============================================================
# 3. EXÉCUTION DU TEST
# ============================================================

def main():
    print("=" * 70)
    print(" TEST END-TO-END du pipeline agent IA annonces")
    print("=" * 70)
    print()
    print("Post simulé qu'on va envoyer dans le pipeline :")
    print("-" * 70)
    print(fake_post.summary)
    print("-" * 70)
    print()

    # ÉTAPE 1 : analyse par Claude
    print("➡️  ÉTAPE 1 : Envoi à Claude pour analyse...")
    try:
        analysis = analyze_post(fake_post.summary)
    except Exception as e:
        print(f"❌ ERREUR Claude : {e}")
        sys.exit(1)

    if "error" in analysis:
        print(f"❌ Claude n'a pas pu parser sa propre réponse : {analysis.get('error')}")
        print(f"   Réponse brute : {analysis.get('raw_response', '')[:300]}")
        sys.exit(1)

    print(f"   is_relevant : {analysis.get('is_relevant')}")
    print(f"   reason : {analysis.get('reason')}")
    print(f"   impact_eurusd : {analysis.get('impact_eurusd')}")
    print(f"   impact_nasdaq : {analysis.get('impact_nasdaq')}")
    print(f"   key_levels : {analysis.get('key_levels_to_watch')}")
    print()

    if not analysis.get("is_relevant"):
        print("⚠️  Claude a jugé le post NON pertinent. Test interrompu :")
        print("    le pipeline est OK jusqu'à Claude, mais on n'enverra rien sur Telegram.")
        print("    Si tu vois ce message, c'est que le post simulé n'a pas convaincu Claude.")
        print("    Soit on muscle le post, soit on ajuste le prompt système.")
        sys.exit(0)

    # ÉTAPE 2 : formatage du message
    print("➡️  ÉTAPE 2 : Formatage du message Telegram (spec V1)...")
    message = format_alert_message(fake_post, analysis)
    print()
    print("Message qui va être envoyé sur Telegram :")
    print("-" * 70)
    print(message)
    print("-" * 70)
    print()

    # ÉTAPE 3 : envoi sur Telegram
    print("➡️  ÉTAPE 3 : Envoi sur Telegram...")
    success = send_telegram(message)

    if success:
        print()
        print("✅ SUCCÈS : message envoyé sur ton Telegram.")
        print("   Va vérifier ton chat avec @TradingAgentTBot.")
        print("   Tu dois voir un message commençant par '📢 Trump Truth Social — (POST DE TEST...'")
    else:
        print()
        print("❌ ÉCHEC : l'envoi Telegram a échoué.")
        print("   Vérifie ton TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID dans .env.")
        sys.exit(1)

    print()
    print("=" * 70)
    print(" Test terminé. Note : ce post n'a PAS été stocké dans seen_posts.json,")
    print(" donc il ne va pas perturber le fonctionnement de main.py.")
    print("=" * 70)


if __name__ == "__main__":
    main()
