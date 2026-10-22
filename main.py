import asyncio
import html
import logging
import os
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
DB_PATH = os.getenv("DB_PATH", "nebtron_support.db")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    ADMIN_ID = 0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("nebtron-support")

router = Router()


# --------------------------------------------------
# ТЕКСТЫ
# --------------------------------------------------

WELCOME = (
    "🌌 <b>NEBTRON SUPPORT</b>\n"
    "<i>Центр помощи NEBTRON VPN</i>\n\n"
    "Привет! Я помогу разобраться с подключением, "
    "подпиской и работой приложения.\n\n"
    "Выбери раздел ниже. Если решение не поможет, "
    "создай обращение — администратор получит его."
)

FAQ_TEXT = (
    "📚 <b>БАЗА ЗНАНИЙ</b>\n\n"
    "🔌 <b>VPN не подключается</b>\n"
    "1. Проверь, работает ли интернет без VPN.\n"
    "2. Закрой и снова открой VPN-приложение.\n"
    "3. Если доступны другие серверы, попробуй другой.\n"
    "4. Если ошибка осталась, создай обращение.\n\n"
    "🌌 <b>Mini App не открывается</b>\n"
    "1. Обнови Telegram и повторно открой приложение.\n"
    "2. Проверь интернет-соединение.\n"
    "3. Если видишь бесконечную загрузку, сообщи об этом поддержке.\n\n"
    "💳 <b>Не активировалась подписка</b>\n"
    "Проверь статус и срок действия подписки. "
    "Если покупка прошла, а доступ не появился, создай обращение.\n\n"
    "🐢 <b>Низкая скорость</b>\n"
    "Проверь качество интернета и попробуй другой доступный сервер.\n\n"
    "⚠️ <b>Важно:</b> не отправляй пароли, коды входа, "
    "платёжные данные или секретные ключи."
)

RULES_TEXT = (
    "📜 <b>ПРАВИЛА ПОДДЕРЖКИ</b>\n\n"
    "1. Описывай проблему спокойно и понятно.\n"
    "2. Указывай, что именно произошло и когда.\n"
    "3. При необходимости прикладывай скриншот ошибки.\n"
    "4. Не отправляй пароли, коды подтверждения, "
    "секретные ключи и платёжные данные.\n"
    "5. Не используй поддержку для спама.\n\n"
    "💙 Мы постараемся помочь разобраться с проблемой."
)

DIAGNOSE_TEXT = (
    "🧭 <b>ДИАГНОСТИКА</b>\n\n"
    "Выбери проблему. Я покажу первые шаги, "
    "которые помогут выяснить причину."
)


# --------------------------------------------------
# БАЗА ДАННЫХ
# --------------------------------------------------

def db_connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with db_connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                category TEXT NOT NULL,
                problem TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                admin_answer TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_seen TEXT NOT NULL
            )
        """)
        con.commit()


def save_user(user):
    if not user:
        return

    with db_connect() as con:
        con.execute("""
            INSERT INTO users (user_id, username, full_name, first_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
        """, (
            user.id,
            user.username,
            user.full_name,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ))
        con.commit()


def create_ticket(user, category, problem):
    with db_connect() as con:
        cur = con.execute("""
            INSERT INTO tickets (
                user_id, username, full_name, category,
                problem, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'open', ?)
        """, (
            user.id,
            user.username,
            user.full_name,
            category,
            problem,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ))
        con.commit()
        return cur.lastrowid


def get_ticket(ticket_id):
    with db_connect() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        return dict(row) if row else None


def set_ticket_answer(ticket_id, answer):
    with db_connect() as con:
        cur = con.execute("""
            UPDATE tickets
            SET admin_answer = ?, status = 'answered'
            WHERE id = ? AND status != 'closed'
        """, (answer, ticket_id))
        con.commit()
        return cur.rowcount > 0


def close_ticket(ticket_id):
    with db_connect() as con:
        cur = con.execute("""
            UPDATE tickets SET status = 'closed'
            WHERE id = ? AND status != 'closed'
        """, (ticket_id,))
        con.commit()
        return cur.rowcount > 0


def get_open_tickets(limit=10):
    with db_connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT id, user_id, category, status, created_at
            FROM tickets
            WHERE status != 'closed'
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]


# --------------------------------------------------
# КНОПКИ
# --------------------------------------------------

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🧭 Найти решение",
                callback_data="diagnose",
            )
        ],
        [
            InlineKeyboardButton(
                text="📚 FAQ",
                callback_data="faq",
            ),
            InlineKeyboardButton(
                text="📜 Правила",
                callback_data="rules",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🛠 Создать обращение",
                callback_data="new_ticket",
            )
        ],
        [
            InlineKeyboardButton(
                text="👨‍💻 Связь с поддержкой",
                callback_data="contact",
            )
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⬅️ Главное меню",
                callback_data="home",
            )
        ]
    ])


def diagnose_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔌 VPN не подключается",
                callback_data="diag_connect",
            )
        ],
        [
            InlineKeyboardButton(
                text="🌌 Не открывается Mini App",
                callback_data="diag_app",
            )
        ],
        [
            InlineKeyboardButton(
                text="💳 Проблема с подпиской",
                callback_data="diag_payment",
            )
        ],
        [
            InlineKeyboardButton(
                text="🐢 Низкая скорость",
                callback_data="diag_speed",
            )
        ],
        [
            InlineKeyboardButton(
                text="🛠 Ничего не помогло",
                callback_data="new_ticket",
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Главное меню",
                callback_data="home",
            )
        ],
    ])


def category_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔌 Подключение VPN",
                callback_data="cat_connect",
            )
        ],
        [
            InlineKeyboardButton(
                text="🌌 Mini App",
                callback_data="cat_app",
            )
        ],
        [
            InlineKeyboardButton(
                text="💳 Подписка или оплата",
                callback_data="cat_payment",
            )
        ],
        [
            InlineKeyboardButton(
                text="🐢 Скорость или сервер",
                callback_data="cat_speed",
            )
        ],
        [
            InlineKeyboardButton(
                text="❔ Другая проблема",
                callback_data="cat_other",
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Главное меню",
                callback_data="home",
            )
        ],
    ])


CATEGORIES = {
    "connect": "Подключение VPN",
    "app": "Mini App",
    "payment": "Подписка или оплата",
    "speed": "Скорость или сервер",
    "other": "Другая проблема",
}


# --------------------------------------------------
# СОСТОЯНИЯ
# --------------------------------------------------

class TicketForm(StatesGroup):
    waiting_problem = State()


# --------------------------------------------------
# СТАРТ И МЕНЮ
# --------------------------------------------------

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    save_user(message.from_user)

    await message.answer(
        WELCOME,
        reply_markup=main_keyboard(),
    )


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext):
    await state.clear()
    save_user(message.from_user)

    await message.answer(
        WELCOME,
        reply_markup=main_keyboard(),
    )


@router.callback_query(F.data == "home")
async def home(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(
        WELCOME,
        reply_markup=main_keyboard(),
    )
    await call.answer()


# --------------------------------------------------
# FAQ И ПРАВИЛА
# --------------------------------------------------

@router.callback_query(F.data == "faq")
async def faq(call: CallbackQuery):
    await call.message.answer(
        FAQ_TEXT,
        reply_markup=back_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data == "rules")
async def rules(call: CallbackQuery):
    await call.message.answer(
        RULES_TEXT,
        reply_markup=back_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data == "contact")
async def contact(call: CallbackQuery):
    await call.message.answer(
        "👨‍💻 <b>СВЯЗЬ С ПОДДЕРЖКОЙ</b>\n\n"
        "Нажми кнопку ниже, чтобы описать проблему. "
        "Я передам обращение администратору.\n\n"
        "После отправки ты получишь номер обращения.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Написать в поддержку",
                    callback_data="new_ticket",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data="home",
                )
            ],
        ]),
    )
    await call.answer()


# --------------------------------------------------
# ДИАГНОСТИКА
# --------------------------------------------------

@router.callback_query(F.data == "diagnose")
async def diagnose(call: CallbackQuery):
    await call.message.answer(
        DIAGNOSE_TEXT,
        reply_markup=diagnose_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("diag_"))
async def diagnose_choice(call: CallbackQuery):
    key = call.data.replace("diag_", "", 1)

    answers = {
        "connect": (
            "🔌 <b>VPN не подключается</b>\n\n"
            "1. Убедись, что интернет работает.\n"
            "2. Полностью перезапусти VPN-приложение.\n"
            "3. Проверь, не истёк ли доступ.\n"
            "4. Если есть другой сервер, попробуй его.\n\n"
            "Если проблема осталась, создай обращение."
        ),
        "app": (
            "🌌 <b>Mini App не открывается</b>\n\n"
            "1. Закрой Mini App и открой его из бота заново.\n"
            "2. Перезапусти Telegram.\n"
            "3. Проверь соединение с интернетом.\n"
            "4. Если загрузка бесконечная, укажи это в обращении.\n\n"
            "Если не помогло, создай обращение."
        ),
        "payment": (
            "💳 <b>Проблема с подпиской</b>\n\n"
            "1. Проверь статус подписки в приложении.\n"
            "2. Убедись, что выбрал правильный аккаунт.\n"
            "3. Если оплата прошла, но доступ не появился, "
            "создай обращение.\n\n"
            "Не отправляй данные банковской карты или коды."
        ),
        "speed": (
            "🐢 <b>Низкая скорость</b>\n\n"
            "1. Проверь скорость интернета без VPN.\n"
            "2. Попробуй другой доступный сервер.\n"
            "3. Повтори проверку в другое время.\n\n"
            "Если проблема сохраняется, создай обращение."
        ),
    }

    await call.message.answer(
        answers.get(key, "Выбери раздел диагностики."),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛠 Создать обращение",
                    callback_data="new_ticket",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧭 К диагностике",
                    callback_data="diagnose",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data="home",
                )
            ],
        ]),
    )
    await call.answer()


# --------------------------------------------------
# СОЗДАНИЕ ОБРАЩЕНИЯ
# --------------------------------------------------

@router.callback_query(F.data == "new_ticket")
async def new_ticket(call: CallbackQuery, state: FSMContext):
    await state.clear()

    await call.message.answer(
        "📝 <b>НОВОЕ ОБРАЩЕНИЕ</b>\n\n"
        "Сначала выбери категорию проблемы:",
        reply_markup=category_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat_"))
async def choose_category(call: CallbackQuery, state: FSMContext):
    key = call.data.replace("cat_", "", 1)
    category = CATEGORIES.get(key)

    if not category:
        await call.answer("Неизвестная категория.", show_alert=True)
        return

    await state.update_data(category=category)
    await state.set_state(TicketForm.waiting_problem)

    await call.message.answer(
        f"🛠 <b>Категория:</b> {html.escape(category)}\n\n"
        "Теперь опиши проблему своими словами.\n\n"
        "Полезно указать:\n"
        "• Что ты пытался сделать.\n"
        "• Что произошло вместо этого.\n"
        "• Текст ошибки, если он есть.\n"
        "• Когда проблема началась.\n\n"
        "Можно прикрепить скриншот следующим сообщением, "
        "но сначала отправь описание текстом.\n\n"
        "⚠️ Не присылай пароли, коды входа и секретные ключи.\n\n"
        "Для отмены напиши /cancel",
        reply_markup=back_keyboard(),
    )
    await call.answer()


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Обращение отменено. Если понадобится помощь, я здесь.",
        reply_markup=main_keyboard(),
    )


@router.message(TicketForm.waiting_problem)
async def receive_problem(
    message: Message,
    state: FSMContext,
    bot: Bot,
):
    if not message.from_user:
        return

    problem = (message.text or message.caption or "").strip()

    if not problem:
        await message.answer(
            "Пожалуйста, сначала отправь описание проблемы текстом."
        )
        return

    if len(problem) > 2500:
        await message.answer(
            "Описание слишком длинное. Сократи его до 2500 символов."
        )
        return

    data = await state.get_data()
    category = data.get("category", "Другая проблема")
    user = message.from_user

    save_user(user)
    ticket_id = create_ticket(user, category, problem)

    if not ADMIN_ID:
        await message.answer(
            f"⚠️ Обращение №{ticket_id} сохранено, но отправка "
            "администратору пока не настроена.\n\n"
            "Попробуй позже или сообщи владельцу сервиса "
            "о проблеме другим доступным способом.",
            reply_markup=main_keyboard(),
        )
        await state.clear()
        return

    username = (
        f"@{html.escape(user.username)}"
        if user.username
        else "не указан"
    )

    admin_text = (
        f"🆕 <b>ОБРАЩЕНИЕ №{ticket_id}</b>\n\n"
        f"📂 <b>Категория:</b> {html.escape(category)}\n"
        f"👤 <b>Пользователь:</b> {html.escape(user.full_name)}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        f"📅 <b>Создано:</b> "
        f"{datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}\n\n"
        f"💬 <b>Описание:</b>\n{html.escape(problem)}\n\n"
        f"Ответить: <code>/reply {ticket_id} текст ответа</code>\n"
        f"Закрыть: <code>/close {ticket_id}</code>"
    )

    try:
        await bot.send_message(ADMIN_ID, admin_text)

        await message.answer(
            f"✅ <b>Обращение №{ticket_id} создано!</b>\n\n"
            "Описание передано администратору. "
            "Когда он ответит, сообщение придёт сюда, в этот чат.\n\n"
            "Сохрани номер обращения на случай уточнений.",
            reply_markup=main_keyboard(),
        )

    except Exception:
        logger.exception("Не удалось уведомить администратора")
        await message.answer(
            f"⚠️ Обращение №{ticket_id} сохранено, "
            "но уведомление администратору не доставлено.\n\n"
            "Попробуй позже.",
            reply_markup=main_keyboard(),
        )

    await state.clear()


# --------------------------------------------------
# КОМАНДЫ АДМИНИСТРАТОРА
# --------------------------------------------------

def is_admin(message: Message) -> bool:
    return bool(
        message.from_user
        and ADMIN_ID > 0
        and message.from_user.id == ADMIN_ID
    )


@router.message(Command("tickets"))
async def tickets_command(message: Message):
    if not is_admin(message):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    tickets = get_open_tickets()

    if not tickets:
        await message.answer("📭 Открытых обращений нет.")
        return

    lines = ["📨 <b>ОТКРЫТЫЕ ОБРАЩЕНИЯ</b>\n"]

    for ticket in tickets:
        lines.append(
            f"№{ticket['id']} · {html.escape(ticket['category'])}\n"
            f"User ID: <code>{ticket['user_id']}</code>\n"
            f"Статус: {html.escape(ticket['status'])}\n"
            f"Создано: {html.escape(ticket['created_at'][:16])}\n"
        )

    lines.append(
        "\nОтвет: <code>/reply НОМЕР текст ответа</code>"
    )
    await message.answer("\n".join(lines))


@router.message(Command("reply"))
async def reply_command(message: Message, bot: Bot):
    if not is_admin(message):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer(
            "Формат команды:\n"
            "<code>/reply НОМЕР_ОБРАЩЕНИЯ текст ответа</code>\n\n"
            "Например:\n"
            "<code>/reply 12 Попробуйте открыть приложение заново.</code>"
        )
        return

    ticket_id = int(parts[1])
    answer = parts[2].strip()

    if not answer:
        await message.answer("Напиши текст ответа.")
        return

    if len(answer) > 3000:
        await message.answer("Ответ слишком длинный. Максимум 3000 символов.")
        return

    ticket = get_ticket(ticket_id)

    if not ticket:
        await message.answer("❌ Обращение с таким номером не найдено.")
        return

    if ticket["status"] == "closed":
        await message.answer("Это обращение уже закрыто.")
        return

    try:
        await bot.send_message(
            ticket["user_id"],
            f"👨‍💻 <b>Ответ поддержки NEBTRON VPN</b>\n"
            f"Обращение №{ticket_id}\n\n"
            f"{html.escape(answer)}",
        )

        set_ticket_answer(ticket_id, answer)
        await message.answer(
            f"✅ Ответ по обращению №{ticket_id} отправлен."
        )

    except Exception:
        logger.exception("Не удалось отправить ответ пользователю")
        await message.answer(
            "❌ Не удалось отправить ответ. Возможно, пользователь "
            "не запускал бота или заблокировал его."
        )


@router.message(Command("close"))
async def close_command(message: Message):
    if not is_admin(message):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split(maxsplit=1)

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            "Формат: <code>/close НОМЕР_ОБРАЩЕНИЯ</code>"
        )
        return

    ticket_id = int(parts[1])

    if close_ticket(ticket_id):
        await message.answer(f"🔒 Обращение №{ticket_id} закрыто.")
    else:
        await message.answer(
            "Обращение не найдено или уже закрыто."
        )


@router.message(Command("admin"))
async def admin_help(message: Message):
    if not is_admin(message):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    await message.answer(
        "🛡 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "/tickets — список открытых обращений\n"
        "/reply НОМЕР текст — ответ пользователю\n"
        "/close НОМЕР — закрыть обращение\n\n"
        "Обращения сохраняются в базе данных."
    )


# --------------------------------------------------
# ЗАПУСК
# --------------------------------------------------

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")

    if ADMIN_ID <= 0:
        raise RuntimeError("Не задан корректный ADMIN_ID.")

    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("NEBTRON SUPPORT запускается")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
