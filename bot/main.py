from __future__ import annotations

import logging

from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ConversationHandler, Defaults, MessageHandler, filters

from bot.config import get_settings
from bot.db import engine
from bot.handlers.admin import (
    ASK_ADMIN_MATCH_ID,
    ASK_ADMIN_RESOLUTION,
    admin_callback,
    admin_cancel,
    admin_complaints,
    admin_disputed_matches,
    admin_events,
    admin_matches,
    admin_panel,
    admin_ping,
    admin_resolve_match_id,
    admin_resolve_outcome,
    admin_resolve_start,
    admin_suggestions,
    admin_users,
)
from bot.handlers.common import help_command, seed_info, start
from bot.handlers.errors import log_error
from bot.handlers.feedback import (
    ASK_COMPLAINT_CONTEXT,
    ASK_COMPLAINT_TEXT,
    ASK_SUGGESTION_TEXT,
    cancel_feedback,
    complaint_context_input,
    complaint_start,
    complaint_text_input,
    suggestion_start,
    suggestion_text_input,
)
from bot.handlers.mail import (
    ASK_MAIL_CLUB,
    ASK_MAIL_MODE,
    ASK_MAIL_QUERY,
    ASK_MAIL_RECIPIENT,
    ASK_MAIL_TEXT,
    cancel_mail,
    incoming_mail,
    mail_callback,
    mail_choose_mode,
    mail_club_input,
    mail_entry,
    mail_query_input,
    mail_recipient_input,
    mail_text_input,
    send_pigeon_start,
)
from bot.handlers.invitations import (
    ASK_INVITE_ACCEPT_ID,
    ASK_INVITE_DECLINE_ID,
    accept_invitation_input,
    accept_invitation_start,
    cancel_invitations,
    decline_invitation_input,
    decline_invitation_start,
    incoming_invitations,
    invitation_callback,
    invitations_entry,
    outgoing_invitations,
)
from bot.handlers.matches import (
    ASK_CONFIRM_ID,
    ASK_DISPUTE_ID,
    ASK_MATCH_ID,
    ASK_MATCH_NOTE,
    ASK_MATCH_OUTCOME,
    cancel_matches,
    confirm_result_input,
    confirm_result_start,
    dispute_result_input,
    dispute_result_start,
    match_callback,
    matches_entry,
    propose_result_match_id,
    propose_result_note,
    propose_result_outcome,
    propose_result_start,
)
from bot.handlers.profile import (
    ASK_CITY,
    ASK_CLUB,
    ASK_FULL_NAME,
    ASK_STATUS_EDIT,
    ASK_WEAPONS,
    ASK_WEAPON_STATUS,
    ask_city,
    ask_club,
    ask_weapons,
    cancel_profile,
    collect_status_edit,
    collect_weapon_statuses,
    collect_weapons,
    edit_statuses_start,
    profile_entry,
    register_start,
)
from bot.handlers.search import (
    ASK_SEARCH_CLUB,
    ASK_SEARCH_MODE,
    ASK_SEARCH_QUERY,
    ASK_SEARCH_WEAPON,
    cancel_search,
    choose_mode,
    choose_weapon,
    club_input,
    query_input,
    search_callback,
    search_entry,
)
from bot.handlers.stats import (
    ASK_TOP_SCOPE,
    ASK_TOP_VALUE,
    ASK_TOP_WEAPON,
    cancel_stats,
    stats_entry,
    top_scope_input,
    top_start,
    top_value_input,
    top_weapon_input,
)
from bot.jobs.scheduler import register_jobs
from bot.models import Base


logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)


def build_application() -> Application:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured. Copy .env.example to .env and set BOT_TOKEN.")

    Base.metadata.create_all(bind=engine)
    application = Application.builder().token(settings.bot_token).defaults(Defaults(parse_mode=ParseMode.HTML)).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("seedinfo", seed_info))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("adminping", admin_ping))

    profile_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Профиль$"), profile_entry),
            MessageHandler(filters.Regex("^Зарегистрироваться$"), register_start),
            MessageHandler(filters.Regex("^Изменить профиль$"), register_start),
            MessageHandler(filters.Regex("^Статусы оружия$"), edit_statuses_start),
        ],
        states={
            ASK_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_city)],
            ASK_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_club)],
            ASK_CLUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_weapons)],
            ASK_WEAPONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_weapons)],
            ASK_WEAPON_STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_weapon_statuses)],
            ASK_STATUS_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_status_edit)],
        },
        fallbacks=[MessageHandler(filters.Regex("^Отмена$"), cancel_profile)],
    )

    search_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Бросить перчатку$"), search_entry)],
        states={
            ASK_SEARCH_WEAPON: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_weapon)],
            ASK_SEARCH_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_mode)],
            ASK_SEARCH_CLUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, club_input)],
            ASK_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, query_input)],
        },
        fallbacks=[MessageHandler(filters.Regex("^Отмена$"), cancel_search)],
    )

    invitation_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Перчаточная$"), invitations_entry),
            MessageHandler(filters.Regex("^Брошенные мне перчатки$"), incoming_invitations),
            MessageHandler(filters.Regex("^Брошенные перчатки$"), outgoing_invitations),
            MessageHandler(filters.Regex("^Принять перчатку$"), accept_invitation_start),
            MessageHandler(filters.Regex("^Вернуть перчатку$"), decline_invitation_start),
        ],
        states={
            ASK_INVITE_ACCEPT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, accept_invitation_input)],
            ASK_INVITE_DECLINE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, decline_invitation_input)],
        },
        fallbacks=[MessageHandler(filters.Regex("^Отмена$"), cancel_invitations)],
    )

    match_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Мои бои$"), matches_entry),
            MessageHandler(filters.Regex("^Список боёв$"), matches_entry),
            MessageHandler(filters.Regex("^Предложить результат$"), propose_result_start),
            MessageHandler(filters.Regex("^Подтвердить результат$"), confirm_result_start),
            MessageHandler(filters.Regex("^Оспорить результат$"), dispute_result_start),
        ],
        states={
            ASK_MATCH_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, propose_result_match_id)],
            ASK_MATCH_OUTCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, propose_result_outcome)],
            ASK_MATCH_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, propose_result_note)],
            ASK_CONFIRM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_result_input)],
            ASK_DISPUTE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, dispute_result_input)],
        },
        fallbacks=[MessageHandler(filters.Regex("^Отмена$"), cancel_matches)],
    )

    feedback_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Написать админу$"), suggestion_start),
        ],
        states={
            ASK_COMPLAINT_CONTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, complaint_context_input)],
            ASK_COMPLAINT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, complaint_text_input)],
            ASK_SUGGESTION_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, suggestion_text_input)],
        },
        fallbacks=[MessageHandler(filters.Regex("^Отмена$"), cancel_feedback)],
    )

    mail_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Почта$"), mail_entry),
            MessageHandler(filters.Regex("^Отправить голубя$"), send_pigeon_start),
            MessageHandler(filters.Regex("^Входящие$"), incoming_mail),
        ],
        states={
            ASK_MAIL_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, mail_choose_mode)],
            ASK_MAIL_CLUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, mail_club_input)],
            ASK_MAIL_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, mail_query_input)],
            ASK_MAIL_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, mail_recipient_input)],
            ASK_MAIL_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, mail_text_input)],
        },
        fallbacks=[MessageHandler(filters.Regex("^Отмена$"), cancel_mail)],
    )

    stats_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Статистика$"), stats_entry),
            MessageHandler(filters.Regex("^Посмотреть топ$"), top_start),
        ],
        states={
            ASK_TOP_WEAPON: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_weapon_input)],
            ASK_TOP_SCOPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_scope_input)],
            ASK_TOP_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_value_input)],
        },
        fallbacks=[MessageHandler(filters.Regex("^Отмена$"), cancel_stats)],
    )

    admin_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Решить спорный бой$"), admin_resolve_start)],
        states={
            ASK_ADMIN_MATCH_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_resolve_match_id)],
            ASK_ADMIN_RESOLUTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_resolve_outcome)],
        },
        fallbacks=[MessageHandler(filters.Regex("^Отмена$"), admin_cancel)],
    )

    application.add_handler(profile_conversation)
    application.add_handler(search_conversation)
    application.add_handler(invitation_conversation)
    application.add_handler(match_conversation)
    application.add_handler(feedback_conversation)
    application.add_handler(mail_conversation)
    application.add_handler(stats_conversation)
    application.add_handler(admin_conversation)

    application.add_handler(CallbackQueryHandler(invitation_callback, pattern=r"^inv:"))
    application.add_handler(CallbackQueryHandler(match_callback, pattern=r"^match:"))
    application.add_handler(CallbackQueryHandler(search_callback, pattern=r"^srch:"))
    application.add_handler(CallbackQueryHandler(mail_callback, pattern=r"^mail:"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))

    application.add_handler(MessageHandler(filters.Regex("^Жалобы$"), admin_complaints))
    application.add_handler(MessageHandler(filters.Regex("^Предложения$"), admin_suggestions))
    application.add_handler(MessageHandler(filters.Regex("^Спорные бои$"), admin_disputed_matches))
    application.add_handler(MessageHandler(filters.Regex("^Пользователи$"), admin_users))
    application.add_handler(MessageHandler(filters.Regex("^Матчи$"), admin_matches))
    application.add_handler(MessageHandler(filters.Regex("^События$"), admin_events))
    application.add_handler(MessageHandler(filters.Regex("^В меню$"), start))

    application.add_error_handler(log_error)
    register_jobs(application)
    return application


def main() -> None:
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
