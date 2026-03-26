from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.enums import ReadinessStatus, WeaponType


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Профиль")],
            [KeyboardButton("Перчаточная"), KeyboardButton("Мои бои")],
            [KeyboardButton("Почта"), KeyboardButton("Написать админу")],
            [KeyboardButton("Статистика")],
        ],
        resize_keyboard=True,
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Почта")],
            [KeyboardButton("Предложения")],
            [KeyboardButton("Спорные бои")],
            [KeyboardButton("Пользователи"), KeyboardButton("Матчи")],
            [KeyboardButton("События"), KeyboardButton("В меню")],
        ],
        resize_keyboard=True,
    )


def profile_keyboard(is_registered: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton("В меню")]]
    if is_registered:
        rows.insert(0, [KeyboardButton("Изменить профиль"), KeyboardButton("Статусы оружия")])
    else:
        rows.insert(0, [KeyboardButton("Зарегистрироваться")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def invitations_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Бросить перчатку")],
            [KeyboardButton("Брошенные мне перчатки"), KeyboardButton("Брошенные перчатки")],
            [KeyboardButton("Принять перчатку"), KeyboardButton("Вернуть перчатку")],
            [KeyboardButton("В меню")],
        ],
        resize_keyboard=True,
    )


def matches_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Список боёв")],
            [KeyboardButton("Предложить результат")],
            [KeyboardButton("Подтвердить результат"), KeyboardButton("Оспорить результат")],
            [KeyboardButton("В меню")],
        ],
        resize_keyboard=True,
    )


def mail_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Отправить голубя"), KeyboardButton("Входящие")],
            [KeyboardButton("В меню")],
        ],
        resize_keyboard=True,
    )


def result_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Моя победа"), KeyboardButton("Победа соперника")],
            [KeyboardButton("Ничья")],
            [KeyboardButton("Отмена")],
        ],
        resize_keyboard=True,
    )


def complaint_context_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Без боя")],
            [KeyboardButton("Отмена")],
        ],
        resize_keyboard=True,
    )


def admin_resolve_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Победа A"), KeyboardButton("Победа B")],
            [KeyboardButton("Ничья")],
            [KeyboardButton("Отмена")],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("Отмена")]], resize_keyboard=True)


def weapons_keyboard(include_done: bool = True) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("Рапира"), KeyboardButton("Сабля")],
        [KeyboardButton("Длинный меч"), KeyboardButton("Рапира и дага")],
        [KeyboardButton("Меч и баклер")],
    ]
    if include_done:
        rows.append([KeyboardButton("Готово")])
    rows.append([KeyboardButton("Отмена")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def readiness_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Не готов"), KeyboardButton("Готов")],
            [KeyboardButton("Готов сегодня"), KeyboardButton("Готов в ближайшие дни")],
            [KeyboardButton("Ищу активно")],
            [KeyboardButton("Отмена")],
        ],
        resize_keyboard=True,
    )


def search_mode_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("По городу"), KeyboardButton("По моему клубу")],
            [KeyboardButton("По конкретному клубу")],
            [KeyboardButton("По ФИО")],
            [KeyboardButton("Отмена")],
        ],
        resize_keyboard=True,
    )


def invitation_actions_inline(invitation_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Принять перчатку", callback_data=f"inv:accept:{invitation_id}"),
                InlineKeyboardButton("Вернуть перчатку", callback_data=f"inv:decline:{invitation_id}"),
            ]
        ]
    )


def outgoing_invitation_actions_inline(invitation_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Забрать перчатку", callback_data=f"inv:cancel:{invitation_id}")]]
    )


def search_result_actions_inline(weapon_type: str, telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Бросить перчатку", callback_data=f"srch:invite:{weapon_type}:{telegram_id}")]]
    )


def mail_actions_inline(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Удалить", callback_data=f"mail:delete:{message_id}")]])


def admin_disputed_match_actions_inline(match_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Решить спорный бой", callback_data=f"admin:resolve_pick:{match_id}")]]
    )


def admin_resolve_inline(match_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Победа A", callback_data=f"admin:resolve:a:{match_id}"),
                InlineKeyboardButton("Победа B", callback_data=f"admin:resolve:b:{match_id}"),
            ],
            [InlineKeyboardButton("Ничья", callback_data=f"admin:resolve:draw:{match_id}")],
        ]
    )


def match_actions_inline(match_id: int, can_propose: bool, can_confirm: bool) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if can_propose:
        rows.append(
            [
                InlineKeyboardButton("Моя победа", callback_data=f"match:propose:self:{match_id}"),
                InlineKeyboardButton("Победа соперника", callback_data=f"match:propose:other:{match_id}"),
            ]
        )
        rows.append([InlineKeyboardButton("Ничья", callback_data=f"match:propose:draw:{match_id}")])
    if can_confirm:
        rows.append(
            [
                InlineKeyboardButton("Подтвердить", callback_data=f"match:confirm:{match_id}"),
                InlineKeyboardButton("Оспорить", callback_data=f"match:dispute:{match_id}"),
            ]
        )
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


def menu_keyboard_for_role(is_admin: bool) -> ReplyKeyboardMarkup:
    return admin_menu_keyboard() if is_admin else main_menu_keyboard()


WEAPON_LABELS = {
    "Рапира": WeaponType.FOIL.value,
    "Сабля": WeaponType.SABRE.value,
    "Длинный меч": WeaponType.LONGSWORD.value,
    "Рапира и дага": WeaponType.RAPIER_DAGGER.value,
    "Меч и баклер": WeaponType.SWORD_BUCKLER.value,
}
WEAPON_TITLES = {value: key for key, value in WEAPON_LABELS.items()}

READINESS_LABELS = {
    "Не готов": ReadinessStatus.NOT_READY.value,
    "Готов": ReadinessStatus.READY.value,
    "Готов сегодня": ReadinessStatus.READY_TODAY.value,
    "Готов в ближайшие дни": ReadinessStatus.READY_SOON.value,
    "Ищу активно": ReadinessStatus.ACTIVELY_LOOKING.value,
}
READINESS_TITLES = {value: key for key, value in READINESS_LABELS.items()}
