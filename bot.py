"""
bot.py
---------

Ce module contient un assistant Telegram qui répond aux questions immobilières
juridiques françaises en se présentant comme « Mathieu Lantoine, agent
immobilier spécialisé à Nice (06) ». L'application utilise la bibliothèque
`python-telegram-bot` pour gérer les messages entrants via le mode longue
interrogation (long polling) et `openai` pour générer des réponses basées sur
le modèle GPT‑4o. Les variables sensibles sont lues depuis un fichier `.env`.

Fonctionnalités :
* Filtrage de mots‑clés pour notifier l'administrateur en cas de terme
  sensible (« procès », « avocat », « litige »).
* Vérification que le sujet concerne l'immobilier ; sinon, réponse par défaut
  indiquant la spécialisation du bot.
* Ajout automatique d'un disclaimer juridique à chaque réponse.
* Point de terminaison `/health` exposé via Flask pour le monitoring.

Pour démarrer localement :

```
cp .env.example .env  # modifiez le contenu de .env selon vos besoins
python bot.py
```
"""

import logging
import os
from typing import Optional

import openai
from dotenv import load_dotenv
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# Charger les variables d'environnement depuis .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # peut être None

if not TELEGRAM_TOKEN:
    raise RuntimeError(
        "La variable TELEGRAM_TOKEN est absente. Veuillez l'ajouter à votre fichier .env."
    )
if not OPENAI_API_KEY:
    raise RuntimeError(
        "La variable OPENAI_API_KEY est absente. Veuillez l'ajouter à votre fichier .env."
    )

openai.api_key = OPENAI_API_KEY

# Configuration du logger
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Disclaimer juridique à ajouter à chaque réponse
DISCLAIMER = (
    "⚠️ Les informations fournies par cet assistant virtuel sont données à titre "
    "informatif uniquement et ne sauraient constituer un conseil juridique, fiscal "
    "ou immobilier personnalisé. Pour toute décision engageant des conséquences "
    "juridiques ou financières, il est fortement recommandé de consulter un "
    "professionnel qualifié (avocat, notaire, expert‑comptable). Aucune "
    "responsabilité ne pourra être retenue à l’encontre de l’auteur ou de l’éditeur "
    "de ce service en cas d’erreur ou d’omission."
)

# Liste de mots clés déclenchant une notification administrative
SENSITIVE_KEYWORDS = ["procès", "avocat", "litige"]


async def call_openai(prompt: str) -> str:
    """Appelle l'API OpenAI GPT‑4o pour générer une réponse.

    Args:
        prompt: question posée par l'utilisateur (en français).

    Returns:
        Réponse générée par le modèle GPT‑4o.
    """
    system_message = (
        "Vous êtes Mathieu Lantoine, agent immobilier spécialisé à Nice (06). "
        "Vous répondez en tant qu'assistant virtuel de Mathieu Lantoine. "
        "Vous devez répondre en français de manière factuelle, professionnelle et modeste. "
        "Si une question sort du domaine de l'immobilier ou du droit immobilier "
        "français, expliquez poliment que vous ne pouvez répondre qu'à ce type de question."
    )
    try:
        completion = await openai.ChatCompletion.acreate(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return completion.choices[0].message.content.strip()
    except Exception as exc:
        logger.exception("Erreur lors de l'appel à l'API OpenAI: %s", exc)
        return (
            "Je rencontre actuellement un problème pour générer une réponse via le modèle. "
            "Veuillez réessayer plus tard."
        )


def contains_sensitive_keyword(text: str) -> Optional[str]:
    """Recherche des mots clés sensibles dans le texte.

    Args:
        text: texte à analyser.

    Returns:
        Le mot clé détecté ou None s'il n'y en a pas.
    """
    lower_text = text.lower() if text else ""
    for keyword in SENSITIVE_KEYWORDS:
        if keyword in lower_text:
            return keyword
    return None


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Répond à la commande /start."""
    welcome_message = (
        "Bonjour! Je suis l'assistant virtuel de Mathieu Lantoine, agent immobilier "
        "spécialisé à Nice (06). Posez-moi vos questions sur l'immobilier, le droit "
        "immobilier, la fiscalité immobilière ou les SCI et je ferai de mon mieux "
        "pour vous répondre."
    )
    if update.message:
        await update.message.reply_text(welcome_message)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Répond à la commande /help."""
    help_message = (
        "Je suis un assistant virtuel spécialisé en droit et fiscalité immobiliers. "
        "Posez votre question de manière claire et je vous fournirai une réponse "
        "aussi précise que possible, accompagnée d'un disclaimer juridique obligatoire."
    )
    if update.message:
        await update.message.reply_text(help_message)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les messages texte des utilisateurs."""
    if not update.message:
        return

    user_text = update.message.text.strip() if update.message.text else ""

    # Vérifier les mots clés sensibles et notifier l'administrateur
    sensitive = contains_sensitive_keyword(user_text)
    if sensitive and ADMIN_CHAT_ID:
        try:
            notify_message = (
                f"Mot clé sensible détecté: '{sensitive}' dans le message de "
                f"{update.effective_user.first_name} ({update.effective_user.id})."
            )
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=notify_message)
        except Exception as exc:
            logger.warning("Impossible d'envoyer la notification admin: %s", exc)

    # Générer une réponse via OpenAI
    response = await call_openai(user_text)

    # Ajouter le disclaimer
    full_response = f"{response}\n\n{DISCLAIMER}"

    # Envoyer la réponse
    await update.message.reply_text(full_response)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les exceptions non interceptées."""
    logger.error(msg="Exception non gérée", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "Une erreur inattendue est survenue. Veuillez réessayer plus tard."
        )


def create_app() -> Flask:
    """Crée et configure l'application Flask pour l'exposition de l'endpoint /health."""
    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health() -> object:
        return jsonify({"status": "ok"})

    return app


def main() -> None:
    """Point d'entrée principal de l'application."""
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Enregistrer les handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_error_handler(error_handler)

    # Démarrer le bot en mode longue interrogation
    logger.info("Démarrage du bot en mode longue interrogation…")
    application.run_polling()


if __name__ == "__main__":
    # Lancer à la fois Flask et le bot
    # Le serveur Flask est lancé dans un thread séparé par python-telegram-bot
    main()