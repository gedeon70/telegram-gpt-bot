"""
bot.py
---------

Ce module définit un assistant Telegram qui répond aux questions
immobilières juridiques françaises en se présentant comme « Mathieu
Lantoine ». Il utilise la bibliothèque `python‑telegram‑bot` pour gérer
les messages via une boucle de longue interrogation (long polling) et
la bibliothèque `openai` pour interroger le modèle GPT‑4o. Les
variables sensibles sont lues depuis un fichier `.env`.

Fonctionnalités :
    • Filtrage de mots clés sensibles (comme « procès », « avocat »,
      « litige »), avec notification facultative de l’administrateur ;
    • Vérification que les questions concernent l’immobilier, sinon
      réponse polie indiquant la spécialisation de l’assistant ;
    • Ajout systématique d’un disclaimer juridique à toutes les réponses ;
    • Exposition d’un endpoint `/health` via Flask permettant à Render de
      vérifier que le service est actif.

Pour démarrer localement :

"""
# Après avoir chargé TELEGRAM_TOKEN, OPENAI_API_KEY et ADMIN_CHAT_ID :
# Définir le modèle et les paramètres OpenAI avec des valeurs par défaut
# économiques. Ces valeurs peuvent être remplacées via les variables
# d'environnement OPENAI_MODEL et OPENAI_MAX_TOKENS.

OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
try:
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "400"))
except ValueError:
    OPENAI_MAX_TOKENS = 400

import logging
import os
import threading
from typing import Optional

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

# Déterminer si nous utilisons la nouvelle interface OpenAI (>= 1.0) ou l’ancienne.
# openai.AsyncOpenAI n’est disponible qu’à partir de la version 1.0.
async_openai_available = False
try:
    from openai import AsyncOpenAI  # type: ignore
    async_openai_available = True
except ImportError:
    import openai  # type: ignore
    AsyncOpenAI = None  # type: ignore

# Charger les variables d’environnement depuis .env
load_dotenv()

TELEGRAM_TOKEN: Optional[str] = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID: Optional[str] = os.getenv("ADMIN_CHAT_ID")  # peut être None

if not TELEGRAM_TOKEN:
    raise RuntimeError(
        "La variable TELEGRAM_TOKEN est absente. Veuillez l'ajouter à votre fichier .env."
    )
if not OPENAI_API_KEY:
    raise RuntimeError(
        "La variable OPENAI_API_KEY est absente. Veuillez l'ajouter à votre fichier .env."
    )

# Instancier le client OpenAI en fonction de la version disponible.
if async_openai_available:
    # Client asynchrone pour les versions récentes du SDK
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)  # type: ignore[name-defined]
else:
    # Pour les versions < 1.0, initialiser la clé API globale
    import openai  # type: ignore
    openai.api_key = OPENAI_API_KEY  # type: ignore[attr-defined]
    openai_client = None  # placeholder pour éviter un NameError

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
    """Appelle l’API OpenAI pour générer une réponse en détectant la bonne interface.

    La fonction crée un message système définissant le rôle de l’assistant,
    puis utilise soit la nouvelle API (>= 1.0) via AsyncOpenAI, soit l’ancienne
    API (ChatCompletion.acreate) pour les versions < 1.0. En cas d’erreur,
    elle renvoie un message par défaut et journalise l’exception.
    """
    system_message = (
        "Vous êtes Mathieu Lantoine, agent immobilier spécialisé à Nice (06). "
        "Vous répondez en tant qu'assistant virtuel de Mathieu Lantoine. "
        "Vous devez répondre en français de manière factuelle, professionnelle et modeste. "
        "Si une question sort du domaine de l'immobilier ou du droit immobilier français, "
        "expliquez poliment que vous ne pouvez répondre qu'à ce type de question."
    )
    try:
        if async_openai_available:
            # Nouvelle interface (>= 1.0)
            response = await openai_client.chat.completions.create(  # type: ignore[union-attr]
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=OPENAI_MAX_TOKENS,
            )
            return response.choices[0].message.content.strip()
        else:
            # Ancienne interface (< 1.0)
            import openai  # type: ignore
            completion = await openai.ChatCompletion.acreate(  # type: ignore[attr-defined]
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=OPENAI_MAX_TOKENS,
            )
            return completion.choices[0].message.content.strip()
    except Exception as exc:
        logger.exception("Erreur lors de l'appel à l'API OpenAI: %s", exc)
        return (
            "Je rencontre actuellement un problème pour générer une réponse via le modèle. "
            "Veuillez réessayer plus tard."
        )


def contains_sensitive_keyword(text: str) -> Optional[str]:
    """Recherche des mots clés sensibles dans le texte."""
    lower_text = text.lower() if text else ""
    for keyword in SENSITIVE_KEYWORDS:
        if keyword in lower_text:
            return keyword
    return None


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Répond à la commande /start."""
    welcome_message = (
        "Bonjour ! Je suis l'assistant virtuel de Mathieu Lantoine, agent immobilier "
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

    # Vérifier les mots clés sensibles et notifier l’administrateur
    sensitive = contains_sensitive_keyword(user_text)
    if sensitive and ADMIN_CHAT_ID:
        try:
            notify_message = (
                f"Mot clé sensible détecté : '{sensitive}' dans le message de "
                f"{update.effective_user.first_name} ({update.effective_user.id})."
            )
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=notify_message)
        except Exception as exc:
            logger.warning("Impossible d'envoyer la notification admin : %s", exc)

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
    """Crée et configure l’application Flask pour l’endpoint /health."""
    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health() -> object:
        return jsonify({"status": "ok"})

    return app


def main() -> None:
    """Lance à la fois le serveur Flask et le bot Telegram.

    Flask s’exécute dans un thread séparé pour exposer l’endpoint /health,
    tandis que le bot fonctionne en mode longue interrogation (polling).
    """
    flask_app = create_app()

    def run_flask() -> None:
        port_str = os.environ.get("PORT", "10000")
        try:
            port = int(port_str)
        except ValueError:
            port = 10000
        flask_app.run(host="0.0.0.0", port=port, threaded=True)

    # Démarrer Flask en arrière-plan
    threading.Thread(target=run_flask, daemon=True).start()

    # Construire l’application Telegram
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Enregistrer les handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
    )
    application.add_error_handler(error_handler)

    # Démarrer le bot en mode longue interrogation
    logger.info("Démarrage du bot en mode longue interrogation…")
    application.run_polling()


if __name__ == "__main__":
    main()
