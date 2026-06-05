"""
Script analyze_post.py - Étape 3 du projet agent IA annonces.

But : prendre un post Truth Social en entrée et demander à Claude d'évaluer :
  1. Est-ce que ce post est pertinent pour le trading EUR/USD ou NASDAQ ?
  2. Si oui, quel impact attendu et quels niveaux surveiller ?

Pour cette étape, on teste avec 2 posts hardcodés (1 non pertinent, 1 pertinent)
pour valider que Claude détecte bien la différence.

À l'étape 4, on connectera ce script avec fetch_truth.py (récupération RSS)
et hello_telegram.py (envoi de l'analyse vers Telegram).

Lance ce script avec : python analyze_post.py
(depuis le venv activé)
"""

# ============================================================
# 1. IMPORTS
# ============================================================
# - anthropic : SDK officiel pour appeler l'API Claude
# - dotenv : pour charger la clé API depuis .env
# - json : pour parser la réponse JSON de Claude
# - os, sys : utilitaires standard

import os
import sys
import json
from dotenv import load_dotenv
from anthropic import Anthropic

# Force l'encoding UTF-8 sur la sortie console (idem fetch_truth.py)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# 2. CHARGEMENT DE LA CLÉ API
# ============================================================
# On force le chemin du .env relatif au script (pas au dossier courant),
# sinon load_dotenv() ne trouve pas le fichier si on lance le script
# depuis un autre dossier (cas courant en prod ou via tâche planifiée).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# override=True force la priorité du .env sur les variables d'environnement
# système. Sans ça, si une variable du même nom existe déjà (même vide)
# dans l'environnement, load_dotenv() ne la surcharge pas par défaut.
load_dotenv(os.path.join(SCRIPT_DIR, ".env"), override=True)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not ANTHROPIC_API_KEY or not ANTHROPIC_API_KEY.startswith("sk-ant-"):
    print("ERREUR : ANTHROPIC_API_KEY n'est pas configurée dans .env")
    print("Crée ta clé sur https://console.anthropic.com puis ajoute-la dans .env.")
    sys.exit(1)


# ============================================================
# 3. CONFIGURATION DU CLIENT CLAUDE
# ============================================================
# On instancie le client une fois, il sera réutilisé pour chaque appel.
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Choix du modèle. Claude Sonnet 4.5 = bon équilibre coût/qualité pour ce use case
# (analyse de texte avec nuances macro/géopolitique).
# Coût indicatif : ~3$ par million de tokens en entrée, ~15$ par million en sortie.
# Pour un post moyen + analyse, on est à ~0,003€ par appel.
MODEL = "claude-sonnet-4-5"


# ============================================================
# 4. PROMPT SYSTÈME (le "rôle" et les règles données à Claude)
# ============================================================
# C'est ici qu'on définit le comportement de Claude. Plus le prompt est précis,
# meilleure est l'analyse. On lui donne :
#  - Son rôle (analyste pour Nathan)
#  - Le contexte trading de Nathan
#  - Les critères de pertinence
#  - Le format de sortie attendu (JSON strict pour qu'on puisse le parser)

SYSTEM_PROMPT = """Tu es un analyste trading senior spécialisé en macro et géopolitique. \
Tu travailles pour Nathan, un trader basé en France qui :
- Trade en intraday EUR/USD
- Fait du scalping sur le NASDAQ
- Est actuellement en challenge FTMO 10K phase 1
- A déjà cramé 2 comptes par non-respect du stop loss → la discipline SL est non-négociable

Ta mission : pour chaque post Trump qu'on te transmet, déterminer s'il est pertinent \
pour le trading EUR/USD ou NASDAQ, et lui livrer EN PRIORITÉ ce qui s'est passé (l'événement \
factuel), avant toute analyse directionnelle.

Critères de pertinence (réponds OUI à au moins UN) :
- Annonce sur la politique monétaire (Fed, BCE, taux, inflation)
- Annonce sur les tarifs commerciaux ou guerres commerciales
- Annonce sur les sanctions économiques
- Annonce sur le pétrole, l'énergie, l'or
- Annonce sur les relations US-Chine, US-Iran, US-Russie, US-Europe
- Annonce sur un conflit géopolitique majeur (Iran, Ukraine, Taiwan, etc.)
- Annonce sur la dette US, le déficit, le shutdown
- Annonce qui mentionne explicitement un secteur ou actif financier
- Annonce qui peut faire bouger immédiatement le dollar ou les indices

Critères de NON-pertinence (politique interne sans impact marché) :
- Politique partisane US (Démocrates vs Républicains)
- Affaires personnelles, divertissement, religion
- Élections locales ou régionales US (sauf si impact macro évident)
- Commentaires sur les médias, célébrités, sport
- Posts sur l'immigration interne, sécurité urbaine
- Auto-promotion, posts narcissiques sans contenu macro

===== RÈGLES DE COHÉRENCE DIRECTIONNELLE (à respecter STRICTEMENT) =====

EUR/USD = cours de l'euro exprimé en dollars.
- "bullish" sur EUR/USD = l'euro monte vs le dollar = LE DOLLAR S'AFFAIBLIT
- "bearish" sur EUR/USD = l'euro baisse vs le dollar = LE DOLLAR SE RENFORCE

Donc :
- Choc géopolitique majeur (Iran, guerre, escalade) → dollar = safe haven = il monte = EUR/USD **BEARISH**
- Fed hawkish, inflation US chaude, économie US forte → dollar plus fort = EUR/USD **BEARISH**
- Fed dovish, perte de confiance US, déficit US creusé → dollar plus faible = EUR/USD **BULLISH**
- BCE hawkish, croissance UE forte → euro plus fort = EUR/USD **BULLISH**
- BCE dovish, crise UE, conflit avec UE → euro plus faible = EUR/USD **BEARISH**

NASDAQ :
- Risk-on (paix, deal commercial, Fed dovish, baisse taux) → NASDAQ **BULLISH**
- Risk-off (guerre, choc géopolitique, Fed hawkish, taux qui montent) → NASDAQ **BEARISH**
- Tarifs sur la tech / semi-conducteurs / hardware → NASDAQ **BEARISH**

VÉRIFICATION INTERNE OBLIGATOIRE avant de répondre :
Si ton "summary_for_telegram" mentionne "USD safe haven" ou "dollar bid" → alors impact_eurusd DOIT être "bearish" (pas bullish).
Si ton summary dit "risk-off" → alors impact_nasdaq DOIT être "bearish".
Toute incohérence entre summary et champs impact_* = erreur grave.

===== RÈGLE SUR LES NIVEAUX (anti-hallucination) =====

Tu N'AS PAS le contexte des prix actuels du marché. Si tu cites un niveau chiffré précis (ex: "1.0800", "18000"), tu te trompes presque toujours, parce que ta connaissance des prix est obsolète.

Pour "key_levels_to_watch" :
- Cite UNIQUEMENT des actifs et des zones QUALITATIVES (pas de chiffres).
- Exemples acceptés : "pétrole Brent/WTI (spike attendu)", "DXY (dollar index)", "VIX", "résistance technique majeure EUR/USD", "support clé NASDAQ", "rendement 10y US".
- Exemples INTERDITS : "1.0800 sur EUR/USD", "18000 sur NASDAQ", "75$ sur Brent".
- Exception : si le post Trump cite lui-même un niveau précis (rare), tu peux le reprendre.

Nathan a ses propres niveaux sur ses graphs. Il n'a pas besoin que tu inventes les siens, il a besoin de savoir QUELS ACTIFS surveiller et DANS QUEL SENS.

===== FORMAT DE RÉPONSE =====

Tu réponds UNIQUEMENT en JSON valide, sans aucun texte avant ou après.

{
  "is_relevant": true ou false,
  "reason": "explication courte (1 phrase) de pourquoi pertinent ou pas",
  "impact_eurusd": "bullish" | "bearish" | "neutral" | "n_a",
  "impact_nasdaq": "bullish" | "bearish" | "neutral" | "n_a",
  "key_levels_to_watch": "actifs et zones qualitatives à surveiller (PAS DE CHIFFRES), ou null si non-pertinent",
  "summary_for_telegram": "résumé en 2-3 lignes max prêt à envoyer sur Telegram, ou null si non-pertinent. STRUCTURE OBLIGATOIRE : Ligne 1 = CE QUI S'EST PASSÉ (fait brut, sans analyse). Ligne 2 = pourquoi ça compte (impact attendu, COHÉRENT avec impact_eurusd et impact_nasdaq). Ligne 3 optionnelle = actifs/zones qualitatives à surveiller. PAS DE NIVEAUX CHIFFRÉS."
}

IMPORTANT : tu ne donnes JAMAIS de recommandation d'achat ou de vente. Tu analyses, \
tu hiérarchises, tu informes. La décision d'entrer en position appartient toujours à Nathan."""


# ============================================================
# 5. FONCTION D'ANALYSE
# ============================================================

def analyze_post(post_text: str) -> dict:
    """
    Envoie un post à Claude et retourne l'analyse JSON parsée.
    En cas d'erreur de parsing, retourne un dict d'erreur.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Voici un post Trump à analyser :\n\n---\n{post_text}\n---"
            }
        ]
    )

    # La réponse de Claude est dans response.content[0].text
    raw_text = response.content[0].text.strip()

    # On parse le JSON. Si Claude a mis du texte autour du JSON, on tente de l'extraire.
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        # Fallback : on extrait ce qui ressemble à du JSON entre la première { et la dernière }
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(raw_text[start:end+1])
            except json.JSONDecodeError:
                pass
        return {
            "error": "JSON parsing failed",
            "raw_response": raw_text,
            "exception": str(e)
        }


def print_analysis(post_text: str, analysis: dict):
    """Affiche le post original et son analyse de manière lisible."""
    print("\n" + "=" * 70)
    print("POST ORIGINAL :")
    print("-" * 70)
    print(post_text)
    print("-" * 70)
    print("ANALYSE CLAUDE :")
    print("-" * 70)
    if "error" in analysis:
        print(f"❌ ERREUR : {analysis['error']}")
        print(f"Réponse brute : {analysis.get('raw_response', '')[:500]}")
    else:
        emoji = "🚨" if analysis.get("is_relevant") else "💤"
        print(f"{emoji} Pertinent : {analysis.get('is_relevant')}")
        print(f"   Raison : {analysis.get('reason')}")
        if analysis.get("is_relevant"):
            print(f"   Impact EUR/USD : {analysis.get('impact_eurusd')}")
            print(f"   Impact NASDAQ : {analysis.get('impact_nasdaq')}")
            print(f"   Niveaux à surveiller : {analysis.get('key_levels_to_watch')}")
            print(f"\n   📩 Résumé Telegram prêt :")
            print(f"   {analysis.get('summary_for_telegram')}")
    print("=" * 70)


# ============================================================
# 6. PROGRAMME PRINCIPAL : tests avec 2 posts d'exemple
# ============================================================

def main():
    # Post 1 : NON-pertinent (politique interne, anti-communisme, aucun impact marché)
    post_non_pertinent = (
        "Has anyone ever seen a Happy Communist? Communists always do well with the Voters "
        "or, as they would say, THE PEOPLE, in the Early Years! But, in the end, the Country, "
        "State, or City, GOES TO HELL! Great Violence proceeds at levels never seen before, "
        "and the entity dissolves into Poverty, Squalor, and Crime. President DONALD J. TRUMP"
    )

    # Post 2 : PERTINENT (annonce sur Iran/blocus, impact macro et géopolitique évident)
    post_pertinent = (
        "Great progress with our negotiations with Iran. The blockade against Iran could be "
        "lifted by Labor Day. Oil prices will come down significantly, and the world will be "
        "a much safer place. We are doing what others said was impossible! President DONALD J. TRUMP"
    )

    print("\n🧪 TEST 1 : post NON-pertinent attendu")
    analysis1 = analyze_post(post_non_pertinent)
    print_analysis(post_non_pertinent, analysis1)

    print("\n🧪 TEST 2 : post PERTINENT attendu")
    analysis2 = analyze_post(post_pertinent)
    print_analysis(post_pertinent, analysis2)


if __name__ == "__main__":
    main()
