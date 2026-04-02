import asyncio
import os
import random
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/db")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CAPCHA_EMOJIS = ["🐍", "🐷", "🐥", "🦄", "🦊", "🦋", "🧊", "🔮"]

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS menu_buttons (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            content TEXT,
            inline_button_text TEXT,
            inline_button_url TEXT,
            photo_id TEXT,
            format_type TEXT DEFAULT 'plain'
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS subs_buttons (
            id SERIAL PRIMARY KEY,
            name TEXT,
            url TEXT,
            chat_id TEXT
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            photo_id TEXT,
            format_type TEXT DEFAULT 'plain'
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS system_messages (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            capcha_passed BOOLEAN DEFAULT FALSE,
            registered_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    try:
        await conn.execute("ALTER TABLE menu_buttons ADD COLUMN IF NOT EXISTS inline_button_text TEXT")
    except Exception:
        pass
    
    try:
        await conn.execute("ALTER TABLE menu_buttons ADD COLUMN IF NOT EXISTS inline_button_url TEXT")
    except Exception:
        pass
    
    try:
        await conn.execute("ALTER TABLE menu_buttons ADD COLUMN IF NOT EXISTS photo_id TEXT")
    except Exception:
        pass
    
    try:
        await conn.execute("ALTER TABLE menu_buttons ADD COLUMN IF NOT EXISTS format_type TEXT DEFAULT 'plain'")
    except Exception:
        pass
    
    try:
        await conn.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS photo_id TEXT")
    except Exception:
        pass
    
    try:
        await conn.execute("ALTER TABLE settings ADD COLUMN IF NOT EXISTS format_type TEXT DEFAULT 'plain'")
    except Exception:
        pass
    
    try:
        await conn.execute("ALTER TABLE subs_buttons ADD COLUMN IF NOT EXISTS chat_id TEXT")
    except Exception:
        pass
    
    try:
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS capcha_passed BOOLEAN DEFAULT FALSE")
    except Exception:
        pass
    
    await conn.close()

async def get_conn():
    return await asyncpg.connect(DATABASE_URL)

def is_bot_link(chat_id: str) -> bool:
    if chat_id and chat_id.startswith("@"):
        username = chat_id[1:].lower()
        return username.startswith("bot") or "bot" in username
    return False

def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("@"):
        username = url[1:]
    else:
        username = url
    username = username.strip().lower()
    return f"https://t.me/{username}"

async def init_defaults():
    conn = await get_conn()
    
    await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", 
                       "start_text", "👋 Добро пожаловать в Krot Free\n\n🌟Мы предоставляем вам бесплатную информацию, которую вы нигде больше не найдете.\n\n🤖Проект полностью бесплатен, мы просим вас подписаться на наших спонсоров, после чего вы получите полный доступ к меню и всей информации!")
    
    await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", 
                       "success_text", "<b>✅ ДОСТУП ОТКРЫТ</b>\n\nРегистрация прошла успешно!\n\n🐭 Krot Free полностью разблокирован и готов к работе, вам доступны все мануалы.\n\n👇 Что делать дальше?\n• Вам открылось меню, в котором вы можете выбрать интересную для себя сферу\n• Переходите на любую из кнопок на клавиатуре и начинайте изучать.")
    
    await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", 
                       "error_text", "<b>❌ Ошибка</b>\n<i>• Вы не подписались на все каналы</i>\n<i>• Подпишитесь и нажмите \"Проверить\" снова</i>")
    
    system_defaults = {
        "Название:": "<blockquote><b>Введите название кнопки</b>\n<i>• Например: Мой канал</i>\n<i>• Максимум 50 символов</i></blockquote>",
        "Ссылка:": "<blockquote><b>Введите ссылку-приглашение</b>\n<i>• Ссылка для кнопки (пользователь перейдет по ней)</i></blockquote>",
        "CHAT ID:": "<blockquote><b>Введите CHAT ID</b>\n<i>• Для публичного канала: @username</i>\n<i>• Для приватной группы: числовой ID (пример: -1001234567890)</i>\n<i>• Получить через @userinfobot</i></blockquote>",
        "Новое название:": "<blockquote><b>Введите новое название</b></blockquote>",
        "Новая ссылка:": "<blockquote><b>Введите новую ссылку-приглашение</b></blockquote>",
        "Новый CHAT ID:": "<blockquote><b>Введите новый CHAT ID</b></blockquote>",
        "Текст кнопки:": "<blockquote><b>Введите текст инлайн-кнопки</b>\n<i>• Например: Перейти к трафику</i>\n<i>• Оставьте пустым, чтобы удалить кнопку</i></blockquote>",
        "URL кнопки:": "<blockquote><b>Введите ссылку для инлайн-кнопки</b>\n<i>• https://t.me/example</i>\n<i>• Или @username</i></blockquote>",
        "Добавлено: {name}": "<blockquote><b>Добавлено:</b> {name}\n<i>• Кнопка появится в меню подписок</i></blockquote>",
        "Удалено: {name}": "<blockquote><b>Удалено:</b> {name}\n<i>• Кнопка удалена из меню</i></blockquote>",
        "Изменено: {name}": "<blockquote><b>Изменено:</b> {name}\n<i>• Изменения вступят в силу сразу</i></blockquote>",
        "Нет кнопок": "<blockquote><b>Нет кнопок</b>\n<i>• Добавьте кнопку через меню</i></blockquote>",
        "Ошибка": "<blockquote><b>Ошибка</b>\n<i>• Проверьте введенные данные</i></blockquote>",
        "Выберите:": "<blockquote><b>Выберите ID кнопки</b></blockquote>",
        "Введите ID:": "<blockquote><b>Введите ID</b></blockquote>",
        "Фото:": "<blockquote><b>Отправьте фото</b>\n<i>• Просто отправьте картинку в этот чат</i>\n<i>• Бот сам сохранит её</i></blockquote>"
    }
    
    for key, value in system_defaults.items():
        await conn.execute("INSERT INTO system_messages (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", key, value)
    
    count = await conn.fetchval("SELECT COUNT(*) FROM menu_buttons")
    if count == 0:
        for i in range(1, 6):
            await conn.execute("INSERT INTO menu_buttons (name, content) VALUES ($1, $2)", str(i), f"Текст для кнопки {i}")
    
    await conn.close()

async def get_system_message(key: str) -> str:
    conn = await get_conn()
    row = await conn.fetchval("SELECT value FROM system_messages WHERE key=$1", key)
    await conn.close()
    return row if row else key

async def get_menu_keyboard():
    conn = await get_conn()
    rows = await conn.fetch("SELECT name FROM menu_buttons ORDER BY id")
    await conn.close()
    buttons = [KeyboardButton(text=row["name"]) for row in rows]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def get_subs_keyboard():
    conn = await get_conn()
    rows = await conn.fetch("SELECT id, name, url FROM subs_buttons ORDER BY id")
    await conn.close()
    buttons = []
    row = []
    for r in rows:
        row.append(InlineKeyboardButton(text=r["name"], url=r["url"]))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="✅ Проверить", callback_data="check_subs")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Тексты", callback_data="admin_texts")],
        [InlineKeyboardButton(text="Reply кнопки", callback_data="admin_reply"), InlineKeyboardButton(text="Инлайн кнопки", callback_data="admin_inline")],
        [InlineKeyboardButton(text="Выйти", callback_data="admin_exit")]
    ])

async def get_reply_list_keyboard():
    conn = await get_conn()
    rows = await conn.fetch("SELECT id, name FROM menu_buttons ORDER BY id")
    await conn.close()
    keyboard = []
    row = []
    for r in rows:
        row.append(InlineKeyboardButton(text=r["name"], callback_data=f"reply_edit_{r['id']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="+ Добавить", callback_data="reply_add"), InlineKeyboardButton(text="- Удалить", callback_data="reply_delete")])
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def get_inline_list_keyboard():
    conn = await get_conn()
    rows = await conn.fetch("SELECT id, name FROM subs_buttons ORDER BY id")
    await conn.close()
    keyboard = []
    row = []
    for r in rows:
        row.append(InlineKeyboardButton(text=r["name"], callback_data=f"inline_edit_{r['id']}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="+ Добавить", callback_data="inline_add"), InlineKeyboardButton(text="- Удалить", callback_data="inline_delete")])
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_texts_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Приветствие", callback_data="text_start")],
        [InlineKeyboardButton(text="Успешная регистрация", callback_data="text_success")],
        [InlineKeyboardButton(text="Ошибка подписок", callback_data="text_error")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_admin")]
    ])

def get_capcha_keyboard(correct_emoji):
    emojis = CAPCHA_EMOJIS.copy()
    random.shuffle(emojis)
    keyboard = [
        [InlineKeyboardButton(text=emojis[0], callback_data=f"capcha_{emojis[0]}"), InlineKeyboardButton(text=emojis[1], callback_data=f"capcha_{emojis[1]}"), InlineKeyboardButton(text=emojis[2], callback_data=f"capcha_{emojis[2]}"), InlineKeyboardButton(text=emojis[3], callback_data=f"capcha_{emojis[3]}")],
        [InlineKeyboardButton(text=emojis[4], callback_data=f"capcha_{emojis[4]}"), InlineKeyboardButton(text=emojis[5], callback_data=f"capcha_{emojis[5]}"), InlineKeyboardButton(text=emojis[6], callback_data=f"capcha_{emojis[6]}"), InlineKeyboardButton(text=emojis[7], callback_data=f"capcha_{emojis[7]}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

class CapchaStates(StatesGroup):
    waiting_capcha = State()

class EditStates(StatesGroup):
    waiting_reply_add_name = State()
    waiting_reply_add_text = State()
    waiting_reply_delete_id = State()
    waiting_reply_edit_name = State()
    waiting_reply_edit_text = State()
    waiting_reply_edit_id = State()
    waiting_reply_inline_text = State()
    waiting_reply_inline_url = State()
    waiting_reply_photo = State()
    waiting_reply_format = State()
    waiting_text_photo = State()
    waiting_text_format = State()
    waiting_text_key = State()
    waiting_inline_add_name = State()
    waiting_inline_add_url = State()
    waiting_inline_add_chat_id = State()
    waiting_inline_delete_id = State()
    waiting_inline_edit_name = State()
    waiting_inline_edit_url = State()
    waiting_inline_edit_chat_id = State()
    waiting_inline_edit_id = State()
    waiting_text = State()
    waiting_system = State()

async def check_subscriptions(user_id: int) -> bool:
    conn = await get_conn()
    rows = await conn.fetch("SELECT chat_id FROM subs_buttons ORDER BY id")
    await conn.close()
    
    for row in rows:
        chat_id = row["chat_id"]
        if not chat_id:
            continue
        
        if is_bot_link(chat_id):
            continue
        
        try:
            if str(chat_id).lstrip('-').isdigit():
                chat_member = await bot.get_chat_member(chat_id=int(chat_id), user_id=user_id)
            else:
                chat_member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            
            if chat_member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logging.error(f"Ошибка проверки: {e}")
            return False
    
    return True

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    conn = await get_conn()
    user = await conn.fetchrow("SELECT capcha_passed FROM users WHERE user_id=$1", user_id)
    subscribed = await check_subscriptions(user_id)
    
    if user and user["capcha_passed"] and subscribed:
        success_text = await conn.fetchval("SELECT value FROM settings WHERE key='success_text'")
        success_photo = await conn.fetchval("SELECT photo_id FROM settings WHERE key='success_text'")
        success_format = await conn.fetchval("SELECT format_type FROM settings WHERE key='success_text'")
        await conn.close()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Поддержка", url="https://t.me/KrotProb")]
        ])
        
        await message.answer("🔑", reply_markup=await get_menu_keyboard())
        
        content = success_text
        if success_format == "quote":
            if not (content.startswith("<blockquote>") and content.endswith("</blockquote>")):
                content = f"<blockquote>{content}</blockquote>"
        
        if success_photo:
            await message.answer_photo(photo=success_photo, caption=content, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(content, parse_mode="HTML", reply_markup=keyboard)
        return
    
    if user and user["capcha_passed"] and not subscribed:
        start_text = await conn.fetchval("SELECT value FROM settings WHERE key='start_text'")
        await conn.close()
        await message.answer(start_text, parse_mode="HTML", reply_markup=await get_subs_keyboard())
        return
    
    await conn.close()
    correct_emoji = random.choice(CAPCHA_EMOJIS)
    keyboard = get_capcha_keyboard(correct_emoji)
    
    await state.set_state(CapchaStates.waiting_capcha)
    await state.update_data(correct_emoji=correct_emoji)
    
    capcha_text = f"<blockquote><b>Проверка</b>\n<i>• Выберите смайл: {correct_emoji}</i>\n<i>• Нажмите на кнопку с этим смайлом</i>\n<i>• Это защита от ботов</i></blockquote>"
    
    await message.answer(capcha_text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(lambda call: call.data.startswith("capcha_"), CapchaStates.waiting_capcha)
async def check_capcha(call: types.CallbackQuery, state: FSMContext):
    selected_emoji = call.data.split("_")[1]
    data = await state.get_data()
    correct_emoji = data.get("correct_emoji")
    
    if selected_emoji == correct_emoji:
        conn = await get_conn()
        await conn.execute("INSERT INTO users (user_id, capcha_passed) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET capcha_passed=$2", 
                          call.from_user.id, True)
        start_text = await conn.fetchval("SELECT value FROM settings WHERE key='start_text'")
        await conn.close()
        
        await call.message.delete()
        await call.message.answer(start_text, parse_mode="HTML", reply_markup=await get_subs_keyboard())
        await state.clear()
    else:
        new_correct_emoji = random.choice(CAPCHA_EMOJIS)
        keyboard = get_capcha_keyboard(new_correct_emoji)
        await state.update_data(correct_emoji=new_correct_emoji)
        await call.message.edit_text(f"<blockquote><b>Неправильно!</b>\n<i>• Выберите смайл: {new_correct_emoji}</i>\n<i>• Попробуйте еще раз</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    
    await call.answer()

@dp.callback_query(lambda call: call.data == "check_subs")
async def check_subs(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    subscribed = await check_subscriptions(user_id)
    
    if not subscribed:
        await call.answer("❌ Вы не подписались на все каналы! Подпишитесь и нажмите снова.", show_alert=True)
        return
    
    conn = await get_conn()
    user = await conn.fetchrow("SELECT capcha_passed FROM users WHERE user_id=$1", user_id)
    
    if not user or not user["capcha_passed"]:
        await conn.execute("UPDATE users SET capcha_passed=$1 WHERE user_id=$2", True, user_id)
    
    success_text = await conn.fetchval("SELECT value FROM settings WHERE key='success_text'")
    success_photo = await conn.fetchval("SELECT photo_id FROM settings WHERE key='success_text'")
    success_format = await conn.fetchval("SELECT format_type FROM settings WHERE key='success_text'")
    await conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Поддержка", url="https://t.me/KrotProb")]
    ])
    
    await call.message.delete()
    await call.message.answer("🔑", reply_markup=await get_menu_keyboard())
    
    content = success_text
    if success_format == "quote":
        if not (content.startswith("<blockquote>") and content.endswith("</blockquote>")):
            content = f"<blockquote>{content}</blockquote>"
    
    if success_photo:
        await call.message.answer_photo(photo=success_photo, caption=content, parse_mode="HTML", reply_markup=keyboard)
    else:
        await call.message.answer(content, parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("<blockquote><b>Админ панель открыта</b>\n<i>• Выберите действие из меню ниже</i></blockquote>", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.callback_query(lambda call: call.data == "admin_reply")
async def admin_reply(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    await call.message.edit_text("<blockquote><b>Управление reply кнопками</b>\n<i>• Выберите кнопку для редактирования</i></blockquote>", parse_mode="HTML", reply_markup=await get_reply_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_inline")
async def admin_inline(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    await call.message.edit_text("<blockquote><b>Управление инлайн кнопками</b>\n<i>• Выберите кнопку для редактирования</i></blockquote>", parse_mode="HTML", reply_markup=await get_inline_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_texts")
async def admin_texts(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    await call.message.edit_text("<blockquote><b>Редактирование текстов</b>\n<i>• Выберите текст для изменения</i></blockquote>", parse_mode="HTML", reply_markup=get_texts_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_exit")
async def admin_exit(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    await call.message.delete()
    await call.answer()

@dp.callback_query(lambda call: call.data.startswith("reply_edit_"))
async def reply_edit_select(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    btn_id = int(call.data.split("_")[2])
    conn = await get_conn()
    row = await conn.fetchrow("SELECT id, name, content, inline_button_text, inline_button_url, photo_id, format_type FROM menu_buttons WHERE id=$1", btn_id)
    await conn.close()
    await state.update_data(waiting_reply_edit_id=btn_id)
    
    inline_info = ""
    if row["inline_button_text"] and row["inline_button_url"]:
        inline_info = f"\n<b>• Инлайн-кнопка:</b> {row['inline_button_text']} -> {row['inline_button_url']}"
    
    photo_info = "\n<b>• Фото:</b> есть" if row["photo_id"] else "\n<b>• Фото:</b> нет"
    
    format_display = "Обычный"
    if row["format_type"] == "quote":
        format_display = "Цитата"
    elif row["format_type"] == "custom":
        format_display = "Свой формат"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить название", callback_data="reply_change_name"), InlineKeyboardButton(text="Изменить текст", callback_data="reply_change_text")],
        [InlineKeyboardButton(text=f"Формат: {format_display}", callback_data="reply_change_format")],
        [InlineKeyboardButton(text="Изменить фото", callback_data="reply_change_photo")],
        [InlineKeyboardButton(text="Добавить инлайн-кнопку", callback_data="reply_add_inline")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply")]
    ])
    
    if row["inline_button_text"] and row["inline_button_url"]:
        keyboard.inline_keyboard.insert(4, [InlineKeyboardButton(text="Удалить инлайн-кнопку", callback_data="reply_remove_inline")])
    
    if row["photo_id"]:
        keyboard.inline_keyboard.insert(3, [InlineKeyboardButton(text="Удалить фото", callback_data="reply_remove_photo")])
    
    await call.message.edit_text(f"<blockquote><b>Редактирование кнопки</b>\n\n<b>• Текущее название:</b> <code>{row['name']}</code>\n<b>• Текущий текст:</b> <code>{row['content']}</code>\n<b>• Формат:</b> {format_display}{photo_info}{inline_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_format")
async def reply_change_format(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обычный текст", callback_data="reply_format_plain")],
        [InlineKeyboardButton(text="Цитата", callback_data="reply_format_quote")],
        [InlineKeyboardButton(text="Свой формат (HTML)", callback_data="reply_format_custom")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply_edit")]
    ])
    await call.message.edit_text("<blockquote><b>Выберите формат отправки</b>\n<i>• Обычный текст — без оформления</i>\n<i>• Цитата — текст в blockquote</i>\n<i>• Свой формат — используйте HTML-теги или форматирование через Telegram</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data.startswith("reply_format_"))
async def reply_save_format(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    format_type = call.data.split("_")[2]
    data = await state.get_data()
    btn_id = data.get("waiting_reply_edit_id")
    if btn_id:
        conn = await get_conn()
        await conn.execute("UPDATE menu_buttons SET format_type=$1 WHERE id=$2", format_type, btn_id)
        await conn.close()
        await call.answer(f"Формат изменен")
        await reply_edit_select(call, state)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_photo")
async def reply_change_photo(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply_edit")]
    ])
    await call.message.edit_text(await get_system_message("Фото:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_photo)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_remove_photo")
async def reply_remove_photo(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    data = await state.get_data()
    btn_id = data.get("waiting_reply_edit_id")
    if btn_id:
        conn = await get_conn()
        await conn.execute("UPDATE menu_buttons SET photo_id=NULL WHERE id=$1", btn_id)
        await conn.close()
        await call.answer("Фото удалено")
        await reply_edit_select(call, state)
    await call.answer()

@dp.message(EditStates.waiting_reply_photo)
async def reply_save_photo(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.photo:
        photo_id = message.photo[-1].file_id
        data = await state.get_data()
        btn_id = data.get("waiting_reply_edit_id")
        if btn_id:
            conn = await get_conn()
            await conn.execute("UPDATE menu_buttons SET photo_id=$1 WHERE id=$2", photo_id, btn_id)
            await conn.close()
            await message.answer("<blockquote><b>Фото сохранено</b></blockquote>", parse_mode="HTML")
    else:
        await message.answer("<blockquote><b>Ошибка</b>\n<i>• Отправьте фото</i></blockquote>", parse_mode="HTML")
    await state.clear()
    await reply_edit_select(message, state)

@dp.callback_query(lambda call: call.data == "reply_add_inline")
async def reply_add_inline(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply_edit")]
    ])
    await call.message.edit_text(await get_system_message("Текст кнопки:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_inline_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_remove_inline")
async def reply_remove_inline(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    data = await state.get_data()
    btn_id = data.get("waiting_reply_edit_id")
    if btn_id:
        conn = await get_conn()
        await conn.execute("UPDATE menu_buttons SET inline_button_text=NULL, inline_button_url=NULL WHERE id=$1", btn_id)
        await conn.close()
        await call.answer("Инлайн-кнопка удалена")
        await reply_edit_select(call, state)
    await call.answer()

@dp.message(EditStates.waiting_reply_inline_text)
async def reply_inline_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(waiting_reply_inline_text=message.text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply_edit")]
    ])
    await message.answer(await get_system_message("URL кнопки:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_inline_url)

@dp.message(EditStates.waiting_reply_inline_url)
async def reply_inline_url(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    btn_id = data.get("waiting_reply_edit_id")
    inline_text = data.get("waiting_reply_inline_text")
    inline_url = normalize_url(message.text)
    
    if btn_id:
        conn = await get_conn()
        await conn.execute("UPDATE menu_buttons SET inline_button_text=$1, inline_button_url=$2 WHERE id=$3", inline_text, inline_url, btn_id)
        await conn.close()
        await message.answer("<blockquote><b>Инлайн-кнопка добавлена/изменена</b></blockquote>", parse_mode="HTML")
    await state.clear()
    await reply_edit_select(message, state)

@dp.callback_query(lambda call: call.data == "reply_change_name")
async def reply_change_name(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новое название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_edit_name)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_text")
async def reply_change_text(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новый текст:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_edit_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_reply_edit")
async def back_to_reply_edit(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    data = await state.get_data()
    btn_id = data.get("waiting_reply_edit_id")
    if btn_id:
        conn = await get_conn()
        row = await conn.fetchrow("SELECT id, name, content, inline_button_text, inline_button_url, photo_id, format_type FROM menu_buttons WHERE id=$1", btn_id)
        await conn.close()
        
        inline_info = ""
        if row["inline_button_text"] and row["inline_button_url"]:
            inline_info = f"\n<b>• Инлайн-кнопка:</b> {row['inline_button_text']} -> {row['inline_button_url']}"
        
        photo_info = "\n<b>• Фото:</b> есть" if row["photo_id"] else "\n<b>• Фото:</b> нет"
        
        format_display = "Обычный"
        if row["format_type"] == "quote":
            format_display = "Цитата"
        elif row["format_type"] == "custom":
            format_display = "Свой формат"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Изменить название", callback_data="reply_change_name"), InlineKeyboardButton(text="Изменить текст", callback_data="reply_change_text")],
            [InlineKeyboardButton(text=f"Формат: {format_display}", callback_data="reply_change_format")],
            [InlineKeyboardButton(text="Изменить фото", callback_data="reply_change_photo")],
            [InlineKeyboardButton(text="Добавить инлайн-кнопку", callback_data="reply_add_inline")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_reply")]
        ])
        
        if row["inline_button_text"] and row["inline_button_url"]:
            keyboard.inline_keyboard.insert(4, [InlineKeyboardButton(text="Удалить инлайн-кнопку", callback_data="reply_remove_inline")])
        
        if row["photo_id"]:
            keyboard.inline_keyboard.insert(3, [InlineKeyboardButton(text="Удалить фото", callback_data="reply_remove_photo")])
        
        await call.message.edit_text(f"<blockquote><b>Редактирование кнопки</b>\n\n<b>• Текущее название:</b> <code>{row['name']}</code>\n<b>• Текущий текст:</b> <code>{row['content']}</code>\n<b>• Формат:</b> {format_display}{photo_info}{inline_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(None)
    await call.answer()

@dp.message(EditStates.waiting_reply_edit_name)
async def reply_save_edit_name(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    btn_id = data["waiting_reply_edit_id"]
    new_name = message.text
    conn = await get_conn()
    await conn.execute("UPDATE menu_buttons SET name=$1 WHERE id=$2", new_name, btn_id)
    await conn.close()
    await message.answer((await get_system_message("Изменено: {name}")).replace("{name}", new_name), parse_mode="HTML")
    await state.clear()
    await admin_reply(message)

@dp.message(EditStates.waiting_reply_edit_text)
async def reply_save_edit_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    btn_id = data["waiting_reply_edit_id"]
    new_text = message.html_text
    conn = await get_conn()
    await conn.execute("UPDATE menu_buttons SET content=$1 WHERE id=$2", new_text, btn_id)
    await conn.close()
    await message.answer((await get_system_message("Изменено: {name}")).replace("{name}", "текст"), parse_mode="HTML")
    await state.clear()
    await admin_reply(message)

@dp.callback_query(lambda call: call.data == "reply_add")
async def reply_add_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_add_name)
    await call.answer()

@dp.message(EditStates.waiting_reply_add_name)
async def reply_add_name(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(waiting_reply_add_name=message.text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply_add")]
    ])
    await message.answer(await get_system_message("Текст:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_add_text)

@dp.callback_query(lambda call: call.data == "back_to_reply_add")
async def back_to_reply_add(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_add_name)
    await call.answer()

@dp.message(EditStates.waiting_reply_add_text)
async def reply_add_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    name = data["waiting_reply_add_name"]
    text = message.html_text
    conn = await get_conn()
    await conn.execute("INSERT INTO menu_buttons (name, content) VALUES ($1, $2)", name, text)
    await conn.close()
    await message.answer((await get_system_message("Добавлено: {name}")).replace("{name}", name), parse_mode="HTML")
    await state.clear()
    await admin_reply(message)

@dp.callback_query(lambda call: call.data == "reply_delete")
async def reply_delete_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    conn = await get_conn()
    rows = await conn.fetch("SELECT id, name FROM menu_buttons ORDER BY id")
    await conn.close()
    if not rows:
        await call.message.edit_text(await get_system_message("Нет кнопок"), parse_mode="HTML")
        await call.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply")]
    ])
    
    text = (await get_system_message("Выберите:")) + "\n\n"
    for r in rows:
        text += f"{r['id']}. {r['name']}\n"
    text += f"\n{await get_system_message('Введите ID:')}"
    
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_delete_id)
    await call.answer()

@dp.message(EditStates.waiting_reply_delete_id)
async def reply_delete_save(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        btn_id = int(message.text)
        conn = await get_conn()
        row = await conn.fetchrow("SELECT name FROM menu_buttons WHERE id=$1", btn_id)
        if row:
            name = row["name"]
            await conn.execute("DELETE FROM menu_buttons WHERE id=$1", btn_id)
            await message.answer((await get_system_message("Удалено: {name}")).replace("{name}", name), parse_mode="HTML")
        else:
            await message.answer(await get_system_message("Ошибка"), parse_mode="HTML")
        await conn.close()
        await reply_delete_start(message, state)
    except ValueError:
        await message.answer(await get_system_message("Ошибка"), parse_mode="HTML")
        await reply_delete_start(message, state)

@dp.callback_query(lambda call: call.data.startswith("inline_edit_"))
async def inline_edit_select(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    btn_id = int(call.data.split("_")[2])
    conn = await get_conn()
    row = await conn.fetchrow("SELECT name, url, chat_id FROM subs_buttons WHERE id=$1", btn_id)
    await conn.close()
    await state.update_data(waiting_inline_edit_id=btn_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить название", callback_data="inline_change_name"), InlineKeyboardButton(text="Изменить ссылку", callback_data="inline_change_url")],
        [InlineKeyboardButton(text="Изменить CHAT ID", callback_data="inline_change_chat_id")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline")]
    ])
    
    display_chat_id = row["chat_id"] if row["chat_id"] else "не указан"
    
    await call.message.edit_text(f"<blockquote><b>Редактирование кнопки</b>\n\n<b>• Название:</b> <code>{row['name']}</code>\n<b>• Ссылка:</b> <code>{row['url']}</code>\n<b>• CHAT ID:</b> <code>{display_chat_id}</code>\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_name")
async def inline_change_name(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новое название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_edit_name)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_url")
async def inline_change_url(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новая ссылка:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_edit_url)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_chat_id")
async def inline_change_chat_id(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новый CHAT ID:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_edit_chat_id)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_inline_edit")
async def back_to_inline_edit(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    data = await state.get_data()
    btn_id = data.get("waiting_inline_edit_id")
    if btn_id:
        conn = await get_conn()
        row = await conn.fetchrow("SELECT name, url, chat_id FROM subs_buttons WHERE id=$1", btn_id)
        await conn.close()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Изменить название", callback_data="inline_change_name"), InlineKeyboardButton(text="Изменить ссылку", callback_data="inline_change_url")],
            [InlineKeyboardButton(text="Изменить CHAT ID", callback_data="inline_change_chat_id")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_inline")]
        ])
        display_chat_id = row["chat_id"] if row["chat_id"] else "не указан"
        await call.message.edit_text(f"<blockquote><b>Редактирование кнопки</b>\n\n<b>• Название:</b> <code>{row['name']}</code>\n<b>• Ссылка:</b> <code>{row['url']}</code>\n<b>• CHAT ID:</b> <code>{display_chat_id}</code>\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(None)
    await call.answer()

@dp.message(EditStates.waiting_inline_edit_name)
async def inline_save_edit_name(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    btn_id = data["waiting_inline_edit_id"]
    new_name = message.text
    conn = await get_conn()
    await conn.execute("UPDATE subs_buttons SET name=$1 WHERE id=$2", new_name, btn_id)
    await conn.close()
    await message.answer((await get_system_message("Изменено: {name}")).replace("{name}", new_name), parse_mode="HTML")
    await state.clear()
    await admin_inline(message)

@dp.message(EditStates.waiting_inline_edit_url)
async def inline_save_edit_url(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    btn_id = data["waiting_inline_edit_id"]
    new_url = message.text.strip()
    conn = await get_conn()
    await conn.execute("UPDATE subs_buttons SET url=$1 WHERE id=$2", new_url, btn_id)
    await conn.close()
    await message.answer((await get_system_message("Изменено: {name}")).replace("{name}", "ссылка"), parse_mode="HTML")
    await state.clear()
    await admin_inline(message)

@dp.message(EditStates.waiting_inline_edit_chat_id)
async def inline_save_edit_chat_id(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    btn_id = data["waiting_inline_edit_id"]
    new_chat_id = message.text.strip()
    conn = await get_conn()
    await conn.execute("UPDATE subs_buttons SET chat_id=$1 WHERE id=$2", new_chat_id, btn_id)
    await conn.close()
    await message.answer((await get_system_message("Изменено: {name}")).replace("{name}", "CHAT ID"), parse_mode="HTML")
    await state.clear()
    await admin_inline(message)

@dp.callback_query(lambda call: call.data == "inline_add")
async def inline_add_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_name)
    await call.answer()

@dp.message(EditStates.waiting_inline_add_name)
async def inline_add_name(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(waiting_inline_add_name=message.text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline_add_url")]
    ])
    await message.answer(await get_system_message("Ссылка:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_url)

@dp.callback_query(lambda call: call.data == "back_to_inline_add_url")
async def back_to_inline_add_url(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_name)
    await call.answer()

@dp.message(EditStates.waiting_inline_add_url)
async def inline_add_url(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(waiting_inline_add_url=message.text.strip())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline_add_chat_id")]
    ])
    await message.answer(await get_system_message("CHAT ID:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_chat_id)

@dp.callback_query(lambda call: call.data == "back_to_inline_add_chat_id")
async def back_to_inline_add_chat_id(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_name)
    await call.answer()

@dp.message(EditStates.waiting_inline_add_chat_id)
async def inline_add_chat_id(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    name = data["waiting_inline_add_name"]
    url = data["waiting_inline_add_url"]
    chat_id = message.text.strip()
    conn = await get_conn()
    await conn.execute("INSERT INTO subs_buttons (name, url, chat_id) VALUES ($1, $2, $3)", name, url, chat_id)
    await conn.close()
    await message.answer((await get_system_message("Добавлено: {name}")).replace("{name}", name), parse_mode="HTML")
    await state.clear()
    await admin_inline(message)

@dp.callback_query(lambda call: call.data == "inline_delete")
async def inline_delete_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    conn = await get_conn()
    rows = await conn.fetch("SELECT id, name FROM subs_buttons ORDER BY id")
    await conn.close()
    if not rows:
        await call.message.edit_text(await get_system_message("Нет кнопок"), parse_mode="HTML")
        await call.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline")]
    ])
    
    text = (await get_system_message("Выберите:")) + "\n\n"
    for r in rows:
        text += f"{r['id']}. {r['name']}\n"
    text += f"\n{await get_system_message('Введите ID:')}"
    
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_delete_id)
    await call.answer()

@dp.message(EditStates.waiting_inline_delete_id)
async def inline_delete_save(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        btn_id = int(message.text)
        conn = await get_conn()
        row = await conn.fetchrow("SELECT name FROM subs_buttons WHERE id=$1", btn_id)
        if row:
            name = row["name"]
            await conn.execute("DELETE FROM subs_buttons WHERE id=$1", btn_id)
            await message.answer((await get_system_message("Удалено: {name}")).replace("{name}", name), parse_mode="HTML")
        else:
            await message.answer(await get_system_message("Ошибка"), parse_mode="HTML")
        await conn.close()
        await inline_delete_start(message, state)
    except ValueError:
        await message.answer(await get_system_message("Ошибка"), parse_mode="HTML")
        await inline_delete_start(message, state)

@dp.callback_query(lambda call: call.data == "text_start")
async def edit_start_text(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    conn = await get_conn()
    current = await conn.fetchval("SELECT value FROM settings WHERE key='start_text'")
    current_photo = await conn.fetchval("SELECT photo_id FROM settings WHERE key='start_text'")
    current_format = await conn.fetchval("SELECT format_type FROM settings WHERE key='start_text'")
    await conn.close()
    await state.update_data(text_key="start_text")
    
    format_display = "Обычный"
    if current_format == "quote":
        format_display = "Цитата"
    elif current_format == "custom":
        format_display = "Свой формат"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить текст", callback_data="text_change_text")],
        [InlineKeyboardButton(text=f"Формат: {format_display}", callback_data="text_change_format")],
        [InlineKeyboardButton(text="Изменить фото", callback_data="text_change_photo")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_texts")]
    ])
    
    if current_photo:
        keyboard.inline_keyboard.insert(2, [InlineKeyboardButton(text="Удалить фото", callback_data="text_remove_photo")])
    
    photo_info = "\n<b>• Фото:</b> есть" if current_photo else "\n<b>• Фото:</b> нет"
    
    await call.message.edit_text(f"<blockquote><b>Редактирование текста приветствия</b>\n\n<b>• Текущий текст:</b>\n<code>{current}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_success")
async def edit_success_text(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    conn = await get_conn()
    current = await conn.fetchval("SELECT value FROM settings WHERE key='success_text'")
    current_photo = await conn.fetchval("SELECT photo_id FROM settings WHERE key='success_text'")
    current_format = await conn.fetchval("SELECT format_type FROM settings WHERE key='success_text'")
    await conn.close()
    await state.update_data(text_key="success_text")
    
    format_display = "Обычный"
    if current_format == "quote":
        format_display = "Цитата"
    elif current_format == "custom":
        format_display = "Свой формат"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить текст", callback_data="text_change_text")],
        [InlineKeyboardButton(text=f"Формат: {format_display}", callback_data="text_change_format")],
        [InlineKeyboardButton(text="Изменить фото", callback_data="text_change_photo")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_texts")]
    ])
    
    if current_photo:
        keyboard.inline_keyboard.insert(2, [InlineKeyboardButton(text="Удалить фото", callback_data="text_remove_photo")])
    
    photo_info = "\n<b>• Фото:</b> есть" if current_photo else "\n<b>• Фото:</b> нет"
    
    await call.message.edit_text(f"<blockquote><b>Редактирование текста успеха</b>\n\n<b>• Текущий текст:</b>\n<code>{current}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_error")
async def edit_error_text(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    conn = await get_conn()
    current = await conn.fetchval("SELECT value FROM settings WHERE key='error_text'")
    current_photo = await conn.fetchval("SELECT photo_id FROM settings WHERE key='error_text'")
    current_format = await conn.fetchval("SELECT format_type FROM settings WHERE key='error_text'")
    await conn.close()
    await state.update_data(text_key="error_text")
    
    format_display = "Обычный"
    if current_format == "quote":
        format_display = "Цитата"
    elif current_format == "custom":
        format_display = "Свой формат"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить текст", callback_data="text_change_text")],
        [InlineKeyboardButton(text=f"Формат: {format_display}", callback_data="text_change_format")],
        [InlineKeyboardButton(text="Изменить фото", callback_data="text_change_photo")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_texts")]
    ])
    
    if current_photo:
        keyboard.inline_keyboard.insert(2, [InlineKeyboardButton(text="Удалить фото", callback_data="text_remove_photo")])
    
    photo_info = "\n<b>• Фото:</b> есть" if current_photo else "\n<b>• Фото:</b> нет"
    
    await call.message.edit_text(f"<blockquote><b>Редактирование текста ошибки</b>\n\n<b>• Текущий текст:</b>\n<code>{current}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_change_format")
async def text_change_format(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обычный текст", callback_data="text_format_plain")],
        [InlineKeyboardButton(text="Цитата", callback_data="text_format_quote")],
        [InlineKeyboardButton(text="Свой формат (HTML)", callback_data="text_format_custom")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_text_edit")]
    ])
    await call.message.edit_text("<blockquote><b>Выберите формат отправки</b>\n<i>• Обычный текст — без оформления</i>\n<i>• Цитата — текст в blockquote</i>\n<i>• Свой формат — используйте HTML-теги или форматирование через Telegram</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data.startswith("text_format_"))
async def text_save_format(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    format_type = call.data.split("_")[2]
    data = await state.get_data()
    text_key = data.get("text_key")
    if text_key:
        conn = await get_conn()
        await conn.execute("UPDATE settings SET format_type=$1 WHERE key=$2", format_type, text_key)
        await conn.close()
        await call.answer(f"Формат изменен")
        
        if text_key == "start_text":
            await edit_start_text(call, state)
        elif text_key == "success_text":
            await edit_success_text(call, state)
        else:
            await edit_error_text(call, state)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_change_text")
async def text_change_text(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_text_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новый текст:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_change_photo")
async def text_change_photo(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_text_edit")]
    ])
    await call.message.edit_text(await get_system_message("Фото:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_text_photo)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_remove_photo")
async def text_remove_photo(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    data = await state.get_data()
    text_key = data.get("text_key")
    if text_key:
        conn = await get_conn()
        await conn.execute("UPDATE settings SET photo_id=NULL WHERE key=$1", text_key)
        await conn.close()
        await call.answer("Фото удалено")
    
    if text_key == "start_text":
        await edit_start_text(call, state)
    elif text_key == "success_text":
        await edit_success_text(call, state)
    else:
        await edit_error_text(call, state)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_text_edit")
async def back_to_text_edit(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    data = await state.get_data()
    text_key = data.get("text_key")
    if text_key == "start_text":
        await edit_start_text(call, state)
    elif text_key == "success_text":
        await edit_success_text(call, state)
    else:
        await edit_error_text(call, state)
    await call.answer()

@dp.message(EditStates.waiting_text)
async def save_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    text_key = data["text_key"]
    new_text = message.html_text
    conn = await get_conn()
    await conn.execute("UPDATE settings SET value=$1 WHERE key=$2", new_text, text_key)
    
    current_photo = await conn.fetchval("SELECT photo_id FROM settings WHERE key=$1", text_key)
    current_format = await conn.fetchval("SELECT format_type FROM settings WHERE key=$1", text_key)
    
    format_display = "Обычный"
    if current_format == "quote":
        format_display = "Цитата"
    elif current_format == "custom":
        format_display = "Свой формат"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить текст", callback_data="text_change_text")],
        [InlineKeyboardButton(text=f"Формат: {format_display}", callback_data="text_change_format")],
        [InlineKeyboardButton(text="Изменить фото", callback_data="text_change_photo")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_texts")]
    ])
    
    if current_photo:
        keyboard.inline_keyboard.insert(2, [InlineKeyboardButton(text="Удалить фото", callback_data="text_remove_photo")])
    
    photo_info = "\n<b>• Фото:</b> есть" if current_photo else "\n<b>• Фото:</b> нет"
    
    if text_key == "start_text":
        await message.answer(f"<blockquote><b>Редактирование текста приветствия</b>\n\n<b>• Текущий текст:</b>\n<code>{new_text}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    elif text_key == "success_text":
        await message.answer(f"<blockquote><b>Редактирование текста успеха</b>\n\n<b>• Текущий текст:</b>\n<code>{new_text}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(f"<blockquote><b>Редактирование текста ошибки</b>\n\n<b>• Текущий текст:</b>\n<code>{new_text}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    
    await conn.close()
    await state.clear()

@dp.message(EditStates.waiting_text_photo)
async def save_text_photo(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.photo:
        photo_id = message.photo[-1].file_id
        data = await state.get_data()
        text_key = data["text_key"]
        conn = await get_conn()
        await conn.execute("UPDATE settings SET photo_id=$1 WHERE key=$2", photo_id, text_key)
        
        current_text = await conn.fetchval("SELECT value FROM settings WHERE key=$1", text_key)
        current_format = await conn.fetchval("SELECT format_type FROM settings WHERE key=$1", text_key)
        
        format_display = "Обычный"
        if current_format == "quote":
            format_display = "Цитата"
        elif current_format == "custom":
            format_display = "Свой формат"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Изменить текст", callback_data="text_change_text")],
            [InlineKeyboardButton(text=f"Формат: {format_display}", callback_data="text_change_format")],
            [InlineKeyboardButton(text="Изменить фото", callback_data="text_change_photo")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_texts")]
        ])
        keyboard.inline_keyboard.insert(2, [InlineKeyboardButton(text="Удалить фото", callback_data="text_remove_photo")])
        photo_info = "\n<b>• Фото:</b> есть"
        
        if text_key == "start_text":
            await message.answer(f"<blockquote><b>Редактирование текста приветствия</b>\n\n<b>• Текущий текст:</b>\n<code>{current_text}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
        elif text_key == "success_text":
            await message.answer(f"<blockquote><b>Редактирование текста успеха</b>\n\n<b>• Текущий текст:</b>\n<code>{current_text}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(f"<blockquote><b>Редактирование текста ошибки</b>\n\n<b>• Текущий текст:</b>\n<code>{current_text}</code>\n<b>• Формат:</b> {format_display}{photo_info}\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
        
        await conn.close()
        await message.answer("<blockquote><b>Фото сохранено</b></blockquote>", parse_mode="HTML")
    else:
        await message.answer("<blockquote><b>Ошибка</b>\n<i>• Отправьте фото</i></blockquote>", parse_mode="HTML")
    await state.clear()

@dp.callback_query(lambda call: call.data == "back_to_texts")
async def back_to_texts(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    await call.message.edit_text("<blockquote><b>Редактирование текстов</b>\n<i>• Выберите текст для изменения</i></blockquote>", parse_mode="HTML", reply_markup=get_texts_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_reply")
async def back_to_reply(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    await call.message.edit_text("<blockquote><b>Управление reply кнопками</b>\n<i>• Выберите кнопку для редактирования</i></blockquote>", parse_mode="HTML", reply_markup=await get_reply_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_inline")
async def back_to_inline(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    await call.message.edit_text("<blockquote><b>Управление инлайн кнопками</b>\n<i>• Выберите кнопку для редактирования</i></blockquote>", parse_mode="HTML", reply_markup=await get_inline_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_admin")
async def back_to_admin_callback(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Доступ запрещен", show_alert=True)
        return
    await call.message.edit_text("<blockquote><b>Админ панель открыта</b>\n<i>• Выберите действие из меню ниже</i></blockquote>", parse_mode="HTML", reply_markup=get_admin_keyboard())
    await call.answer()

@dp.message(lambda message: True)
async def handle_menu_buttons(message: types.Message):
    conn = await get_conn()
    row = await conn.fetchrow("SELECT content, inline_button_text, inline_button_url, photo_id, format_type FROM menu_buttons WHERE name=$1", message.text)
    await conn.close()
    if row:
        keyboard = None
        if row["inline_button_text"] and row["inline_button_url"]:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=row["inline_button_text"], url=row["inline_button_url"])]
            ])
        
        content = row["content"]
        format_type = row["format_type"] if row["format_type"] else "plain"
        
        if format_type == "quote":
            if not (content.startswith("<blockquote>") and content.endswith("</blockquote>")):
                content = f"<blockquote>{content}</blockquote>"
        elif format_type == "custom":
            pass
        else:
            if content.startswith("<blockquote>") and content.endswith("</blockquote>"):
                content = content[12:-13]
        
        if row["photo_id"]:
            await message.answer_photo(photo=row["photo_id"], caption=content, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(content, parse_mode="HTML", reply_markup=keyboard)

async def main():
    await init_db()
    await init_defaults()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
