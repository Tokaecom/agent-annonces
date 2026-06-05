# Agent IA Annonces non-calendrier

Agent Python qui surveille en temps réel les annonces macro et géopolitiques non-calendrier (Trump sur Truth Social, banques centrales hors agenda, événements géopolitiques) et envoie une analyse d'impact sur Telegram pour aider la prise de décision trading EUR/USD et NAS.

Spec complète dans `C:\Jarvis\jarvis-starter-kit\context\projets\agent-annonces.md`.

---

## Structure du projet

```
agent-annonces/
├── venv/               # Environnement virtuel Python (ne pas commit)
├── .env                # Secrets (ne pas commit, créé à l'étape 1)
├── .env.example        # Template des secrets attendus
├── .gitignore          # Fichiers à ignorer
├── requirements.txt    # Liste des bibliothèques Python utilisées
└── README.md           # Ce fichier
```

---

## Comment activer le venv

Dans un terminal PowerShell, depuis le dossier du projet :

```powershell
.\venv\Scripts\Activate.ps1
```

Tu devrais voir `(venv)` apparaître devant le prompt. Pour désactiver : `deactivate`.

Si PowerShell bloque l'activation à cause de la policy d'exécution, lance une fois :

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## Comment installer les dépendances

Une fois le venv activé :

```powershell
pip install -r requirements.txt
```

---

## État d'avancement

- [x] **Étape 0** : préparation environnement (Python 3.12, venv, structure)
- [x] **Étape 1** : bot Telegram qui dit "Hello Nathan"
- [x] **Étape 2** : récupération automatique des posts Truth Social (via trumpstruth.org RSS)
- [x] **Étape 3** : analyse d'annonce par Claude (filtrage pertinence + niveaux + résumé Telegram)
- [x] **Étape 4** : assemblage complet (Truth Social → Claude → Telegram)
- [x] **Étape 6** : mise en production 24/7 via GitHub Actions
- [ ] **Étape 5** : ajout d'autres sources (Powell, Lagarde, ForexLive)

## Scripts disponibles

- `hello_telegram.py` : envoie un message test "Hello Nathan" sur Telegram (étape 1)
- `fetch_truth.py` : récupère les nouveaux posts Trump via flux RSS de trumpstruth.org et les affiche dans la console (étape 2). Mémorise les posts déjà vus dans `data/seen_posts.json`
- `analyze_post.py` : prend un post Truth Social en entrée et demande à Claude de déterminer s'il est pertinent pour le trading EUR/USD ou NASDAQ. Retourne une analyse JSON structurée (pertinence, impact, niveaux, résumé Telegram prêt) (étape 3)
- `main.py` : pipeline complet. Deux modes :
  - `python main.py` → boucle infinie (polling toutes les 5 min, mode local de debug)
  - `python main.py --once` → un seul cycle puis exit (mode prod, utilisé par GitHub Actions)
- `test_pipeline.py` : test end-to-end qui simule un post pertinent sans toucher au flux RSS réel

## Déploiement 24/7 (production)

L'agent tourne automatiquement toutes les 5 minutes via GitHub Actions, sans besoin d'allumer le PC.

Workflow : `.github/workflows/agent.yml`.

Secrets à configurer une fois sur GitHub (`Settings → Secrets and variables → Actions`) :
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY`

Pour lancer manuellement le workflow : aller dans l'onglet **Actions** du repo GitHub, sélectionner "Agent Annonces", cliquer sur "Run workflow".

Pour voir les logs en temps réel : onglet **Actions** → cliquer sur le run en cours.
