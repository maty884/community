
import asyncio
import logging
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

# -------------------- CONFIG --------------------

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "0").strip()

if not TOKEN:
    raise ValueError(
        "Не найден BOT_TOKEN. Проверь файл .env в папке community."
    )

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise ValueError("ADMIN_ID в файле .env должен быть числом.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# -------------------- BOT --------------------

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# -------------------- STATES --------------------

class UserForms(StatesGroup):
    contact_message = State()
    report_message = State()


# -------------------- KEYBOARD --------------------

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📋 Правила"),
            KeyboardButton(text="❓ FAQ"),
        ],
        [
            KeyboardButton(text="💬 Связаться с админом"),
            KeyboardButton(text="🚩 Сообщить о проблеме"),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выбери действие",
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❌ Отмена")],
    ],
    resize_keyboard=True,
)


# -------------------- START --------------------

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "Привет! 👋\n\n"
        "Я CommunityHelper — бот-помощник сообщества.\n\n"
        "Через меня можно узнать правила, посмотреть FAQ, "
        "написать администратору или сообщить о проблеме.",
        reply_markup=main_keyboard,
    )


# -------------------- USER ID --------------------

@dp.message(Command("myid"))
async def myid_handler(message: Message):
    await message.answer(
        f"Твой Telegram ID: {message.from_user.id}"
    )


# -------------------- RULES --------------------

@dp.message(F.text == "📋 Правила")
async def rules_handler(message: Message):
    await message.answer(
        "📋 Правила сообщества\n\n"
        "1. Уважай других участников.\n"
        "2. Не оскорбляй и не провоцируй конфликты.\n"
        "3. Не отправляй спам и рекламу без разрешения.\n"
        "4. Не публикуй чужие личные данные.\n"
        "5. Соблюдай правила Telegram.\n\n"
        "Администратор может дополнить эти правила."
    )


# -------------------- FAQ --------------------

@dp.message(F.text == "❓ FAQ")
async def faq_handler(message: Message):
    await message.answer(
        "❓ Часто задаваемые вопросы\n\n"
        "• Как связаться с администратором?\n"
        "Нажми «💬 Связаться с админом».\n\n"
        "• Как сообщить о проблеме?\n"
        "Нажми «🚩 Сообщить о проблеме».\n\n"
        "• Как отменить заполнение формы?\n"
        "Нажми «❌ Отмена» или отправь /cancel."
    )


# -------------------- CONTACT ADMIN --------------------

@dp.message(F.text == "💬 Связаться с админом")
async def contact_start(message: Message, state: FSMContext):
    await state.set_state(UserForms.contact_message)

    await message.answer(
        "💬 Напиши сообщение администратору одним сообщением.\n\n"
        "Чтобы отменить, нажми «❌ Отмена».",
        reply_markup=cancel_keyboard,
    )


@dp.message(UserForms.contact_message, F.text == "❌ Отмена")
async def contact_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Отменено.",
        reply_markup=main_keyboard,
    )


@dp.message(UserForms.contact_message)
async def contact_receive(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправь текстовое сообщение.")
        return

    if ADMIN_ID == 0:
        await state.clear()
        await message.answer(
            "Администратор ещё не настроен. Попробуй позже.",
            reply_markup=main_keyboard,
        )
        logging.warning("ADMIN_ID не задан в .env")
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else "нет username"

    try:
        await bot.send_message(
            ADMIN_ID,
            "💬 Новое обращение\n\n"
            f"От: {user.full_name}\n"
            f"Username: {username}\n"
            f"ID: {user.id}\n\n"
            f"Сообщение:\n{message.text}\n\n"
            f"Ответить: /reply {user.id} текст ответа",
        )
    except Exception:
        logging.exception("Не удалось отправить обращение администратору")
        await message.answer(
            "Не удалось доставить сообщение. "
            "Попробуй позже или свяжись с администратором другим способом.",
            reply_markup=main_keyboard,
        )
        await state.clear()
        return

    await state.clear()
    await message.answer(
        "✅ Сообщение отправлено администратору.",
        reply_markup=main_keyboard,
    )


# -------------------- REPORT PROBLEM --------------------

@dp.message(F.text == "🚩 Сообщить о проблеме")
async def report_start(message: Message, state: FSMContext):
    await state.set_state(UserForms.report_message)

    await message.answer(
        "🚩 Опиши проблему одним сообщением.\n\n"
        "Чтобы отменить, нажми «❌ Отмена».",
        reply_markup=cancel_keyboard,
    )


@dp.message(UserForms.report_message, F.text == "❌ Отмена")
async def report_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Отменено.",
        reply_markup=main_keyboard,
    )


@dp.message(UserForms.report_message)
async def report_receive(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, опиши проблему текстом.")
        return

    if ADMIN_ID == 0:
        await state.clear()
        await message.answer(
            "Администратор ещё не настроен. Попробуй позже.",
            reply_markup=main_keyboard,
        )
        logging.warning("ADMIN_ID не задан в .env")
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else "нет username"

    try:
        await bot.send_message(
            ADMIN_ID,
            "🚩 Жалоба или сообщение о проблеме\n\n"
            f"От: {user.full_name}\n"
            f"Username: {username}\n"
            f"ID: {user.id}\n\n"
            f"Описание:\n{message.text}\n\n"
            f"Ответить: /reply {user.id} текст ответа",
        )
    except Exception:
        logging.exception("Не удалось отправить жалобу администратору")
        await message.answer(
            "Не удалось отправить сообщение. Попробуй позже.",
            reply_markup=main_keyboard,
        )
        await state.clear()
        return

    await state.clear()
    await message.answer(
        "✅ Информация отправлена администратору.",
        reply_markup=main_keyboard,
    )


# -------------------- CANCEL COMMAND --------------------

@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=main_keyboard,
    )


# -------------------- ADMIN REPLY --------------------

@dp.message(Command("reply"))
async def admin_reply(message: Message):
    if message.from_user.id != ADMIN_ID or ADMIN_ID == 0:
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "Формат команды:\n/reply USER_ID текст ответа\n\n"
            "Пример:\n/reply 123456789 Привет! Чем помочь?"
        )
        return

    try:
        target_user_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID должен быть числом.")
        return

    reply_text = parts[2].strip()

    if not reply_text:
        await message.answer("Напиши текст ответа.")
        return

    try:
        await bot.send_message(
            target_user_id,
            f"📩 Ответ администратора:\n\n{reply_text}",
        )
    except Exception:
        logging.exception("Не удалось отправить ответ пользователю")
        await message.answer(
            "Не удалось отправить ответ. "
            "Возможно, пользователь не запускал бота или заблокировал его."
        )
        return

    await message.answer("✅ Ответ отправлен пользователю.")


# -------------------- UNKNOWN MESSAGE --------------------

@dp.message()
async def fallback_handler(message: Message):
    await message.answer(
        "Не понял команду. Выбери действие в меню "
        "или отправь /start.",
        reply_markup=main_keyboard,
    )


# -------------------- MAIN --------------------

async def main():
    try:
        logging.info("Запуск CommunityHelper...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
