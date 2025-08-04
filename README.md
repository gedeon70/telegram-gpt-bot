# Assistant immobilier virtuel (Telegram)

Ce projet fournit un assistant Telegram clé en main capable de répondre à des
questions juridiques françaises liées à l’immobilier, aux baux, à la fiscalité
immobilière et aux sociétés civiles immobilières (SCI). Le bot agit au nom de
**Mathieu Lantoine**, agent immobilier basé à Nice (06), et mentionne qu’il est
un assistant virtuel afin de rester transparent. Son comportement est conçu
pour être factuel, professionnel et modeste : en cas d’incertitude, il
reconnaît ne pas avoir l’information plutôt que de fournir des réponses
hasardeuses.

## Fonctionnalités

- **Réponses contextuelles via GPT‑4o** : le bot utilise l’API d’OpenAI pour
  générer des réponses basées sur vos questions immobilières françaises. Il
  reconnaît et filtre des messages qui ne sont pas liés à l’immobilier et répond
  avec un message expliquant sa spécialisation.
- **Détection de mots‑clés sensibles** : lorsque l’utilisateur mentionne des
  termes comme « procès », « avocat » ou « litige », le bot journalise ces
  occurrences et notifie l’administrateur via un message Telegram (voir la
  variable d’environnement `ADMIN_CHAT_ID`).
- **Stockage de clés via `.env`** : les variables sensibles (token du bot
  Telegram, clé API OpenAI et identifiant du chat administrateur) sont lues à
  partir d’un fichier `.env`. Un fichier `.env.example` est fourni pour montrer
  la structure attendue.
- **Serveur HTTP via Flask** : un serveur web minimal expose un point
  d’entrée `/health` pour le monitoring et lance le bot en mode longue
  interrogation (long polling). Ce fonctionnement est compatible avec des
  plateformes d’hébergement comme Render ou Railway.
- **Journalisation** : l’application journalise ses évènements dans la sortie
  standard. Vous pouvez rediriger ces logs vers un fichier ou une solution
  externe selon les besoins.

## Déploiement

### Pré‑requis

1. **Clés d’API** : vous devez disposer :
   - d’un **token Telegram** obtenu via [@BotFather](https://t.me/BotFather) ;
   - d’une **clé API OpenAI** (tarif GPT‑4o). Vous pouvez la générer dans
     [l’interface OpenAI](https://platform.openai.com/account/api-keys).
2. **Compte Render ou Railway** : créez un compte gratuit sur
   [Render](https://render.com/) ou [Railway](https://railway.app/). Le
   déploiement sur Render est documenté ci‑dessous.
3. **Git** : installez git localement pour cloner ce dépôt ou créez un nouveau
   dépôt dans votre propre compte GitHub et poussez les fichiers qui se trouvent
   dans ce répertoire.

### Déploiement sur Render

1. **Créer un dépôt Git** : initialisez un nouveau dépôt GitHub avec le contenu de ce
   projet et publiez‑le sur votre compte.
2. **Déployer via Render** :
   - Connectez‑vous à Render et sélectionnez l’option *“New +”* puis *“Web Service”*.
   - Choisissez le dépôt GitHub contenant ce code et autorisez Render à y accéder.
   - Configurez le service :
     - **Build Command** : `pip install -r requirements.txt`
     - **Start Command** : `python bot.py`
     - **Python Version** : `3.11` (ou la version disponible la plus récente).
     - **Environment** : ajoutez les variables d’environnement suivantes :
       - `TELEGRAM_TOKEN` : le token de votre bot Telegram.
       - `OPENAI_API_KEY` : votre clé API OpenAI.
       - `ADMIN_CHAT_ID` : l’identifiant Telegram du chat dans lequel vous souhaitez
         recevoir les notifications de mots clés sensibles. Vous pouvez le laisser vide
         pour désactiver les notifications.
   - Laissez la valeur par défaut de `Port` à `10000` (le port n’a pas
     d’importance puisque nous utilisons le mode long polling, mais Render
     exige un port exposé).
3. **Déployer** : lancez le déploiement. Render construira l’image et exécutera
   l’application. Sur la page du service, vous verrez les logs ainsi qu’une URL
   de déploiement. Bien que l’URL ne soit pas utilisée par Telegram (puisque
   nous utilisons le long polling), elle vous permet de vérifier que
   l’application démarre correctement.

### Déploiement sur Railway

Le processus est similaire à Render : créez un nouveau projet, liez le dépôt
GitHub et définissez les variables d’environnement. Railway propose également
un plan gratuit adapté à ce type d’application.

## Utilisation

Une fois le bot déployé et les webhooks configurés, trouvez le bot sur
Telegram (via l’alias que vous avez défini avec @BotFather) et commencez à
discuter. Posez vos questions relatives à l’immobilier et au droit immobilier
français et il vous répondra en ajoutant le disclaimer juridique suivant à
chaque message :

```
⚠️ Les informations fournies par cet assistant virtuel sont données à titre informatif uniquement et ne sauraient constituer un conseil juridique, fiscal ou immobilier personnalisé. Pour toute décision engageant des conséquences juridiques ou financières, il est fortement recommandé de consulter un professionnel qualifié (avocat, notaire, expert‑comptable). Aucune responsabilité ne pourra être retenue à l’encontre de l’auteur ou de l’éditeur de ce service en cas d’erreur ou d’omission.
```

## Tests locaux

Pour exécuter l’application localement :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # puis remplissez les valeurs
python bot.py
```

Le bot démarrera en mode long polling. Envoyez‑lui des messages via Telegram
pour tester.

## Structure des fichiers

- `bot.py` : script principal qui initialise le bot, configure les handlers
  Telegram et démarre le serveur.
- `requirements.txt` : liste des dépendances Python.
- `.env.example` : modèle de variables d’environnement à remplir.
- `README.md` : ce guide.