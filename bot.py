import asyncio
import os #ha
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CAPCHA_EMOJIS = ["🐍", "🐷", "🐥", "🦄", "🦊", "🦋", "🧊", "🔮"]

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS menu_buttons (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            content TEXT
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
            value TEXT
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
            registered_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    try:
        await conn.execute("ALTER TABLE users ADD COLUMN capcha_passed BOOLEAN DEFAULT FALSE")
    except Exception:
        pass
    
    # Добавляем колонку chat_id если её нет
    try:
        await conn.execute("ALTER TABLE subs_buttons ADD COLUMN chat_id TEXT")
    except Exception:
        pass
    
    await conn.close()

async def get_conn():
    return await asyncpg.connect(DATABASE_URL)

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

def is_bot_link(url: str) -> bool:
    if "t.me/" in url:
        username = url.split("t.me/")[-1]
        if username.startswith("bot") or "bot" in username.lower():
            return True
    return False

async def init_defaults():
    conn = await get_conn()
    
    await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", 
                       "start_text", "<blockquote>👋 Добро пожаловать в Krot Free\n\n🌟Мы предоставляем вам бесплатную информацию, которую вы нигде больше не найдете.\n\n🤖Проект полностью бесплатен, мы просим вас подписаться на наших спонсоров, после чего вы получите полный доступ к меню и всей информации!</blockquote>")
    
    await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", 
                       "success_text", "<blockquote><b>✅ ДОСТУП ОТКРЫТ</b>\n\nРегистрация прошла успешно!\n\n🐭 Krot Free полностью разблокирован и готов к работе, вам доступны все мануалы.\n\n👇 Что делать дальше?\n• Вам открылось меню, в котором вы можете выбрать интересную для себя сферу\n• Переходите на любую из кнопок на клавиатуре и начинайте изучать.</blockquote>")
    
    await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", 
                       "error_text", "<blockquote><b>❌ Ошибка</b>\n<i>• Вы не подписались на все каналы</i>\n<i>• Подпишитесь и нажмите \"Проверить\" снова</i></blockquote>")
    
    system_defaults = {
        "Название:": "<blockquote><b>📝 Введите название кнопки</b>\n<i>• Например: Мой канал</i>\n<i>• Максимум 50 символов</i></blockquote>",
        "Ссылка:": "<blockquote><b>🔗 Введите ссылку-приглашение</b>\n<i>• Ссылка для кнопки (пользователь перейдет по ней)</i>\n<i>• Для публичного канала: https://t.me/username</i>\n<i>• Для приватной группы: https://t.me/joinchat/xxxxx</i></blockquote>",
        "CHAT ID:": "<blockquote><b>🆔 Введите CHAT ID</b>\n<i>• Для публичного канала: @username</i>\n<i>• Для приватной группы: числовой ID (пример: -1001234567890)</i>\n<i>• Получить через @userinfobot</i></blockquote>",
        "Новое название:": "<blockquote><b>✏️ Введите новое название</b></blockquote>",
        "Новая ссылка:": "<blockquote><b>🔗 Введите новую ссылку-приглашение</b></blockquote>",
        "Новый CHAT ID:": "<blockquote><b>🆔 Введите новый CHAT ID</b></blockquote>",
        "Добавлено: {name}": "<blockquote><b>✅ Добавлено:</b> {name}\n<i>• Кнопка появится в меню подписок</i></blockquote>",
        "Удалено: {name}": "<blockquote><b>❌ Удалено:</b> {name}\n<i>• Кнопка удалена из меню</i></blockquote>",
        "Изменено: {name}": "<blockquote><b>✏️ Изменено:</b> {name}\n<i>• Изменения вступят в силу сразу</i></blockquote>",
        "Нет кнопок": "<blockquote><b>📭 Нет кнопок</b>\n<i>• Добавьте кнопку через меню</i></blockquote>",
        "Ошибка": "<blockquote><b>⚠️ Ошибка</b>\n<i>• Проверьте введенные данные</i></blockquote>",
        "Выберите:": "<blockquote><b>🔢 Выберите ID кнопки</b></blockquote>",
        "Введите ID:": "<blockquote><b>🔢 Введите ID</b></blockquote>"
    }
    
    for key, value in system_defaults.items():
        await conn.execute("INSERT INTO system_messages (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", key, value)
    
    count = await conn.fetchval("SELECT COUNT(*) FROM menu_buttons")
    if count == 0:
        for i in range(1, 6):
            await conn.execute("INSERT INTO menu_buttons (name, content) VALUES ($1, $2)", str(i), f"<blockquote>📄 Текст для кнопки {i}</blockquote>")
    
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
        [InlineKeyboardButton(text="📋 Reply кнопки", callback_data="admin_reply"), InlineKeyboardButton(text="🔗 Инлайн кнопки", callback_data="admin_inline")],
        [InlineKeyboardButton(text="📝 Тексты", callback_data="admin_texts")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data="admin_exit")]
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
    keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data="reply_add"), InlineKeyboardButton(text="➖ Удалить", callback_data="reply_delete")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
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
    keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data="inline_add"), InlineKeyboardButton(text="➖ Удалить", callback_data="inline_delete")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_texts_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Приветствие", callback_data="text_start")],
        [InlineKeyboardButton(text="✅ Успешная регистрация", callback_data="text_success")],
        [InlineKeyboardButton(text="❌ Ошибка подписок", callback_data="text_error")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")]
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
        
        if chat_id.startswith("@") and "bot" in chat_id.lower():
            continue
        
        try:
            if chat_id.lstrip('-').isdigit():
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
    
    if user and user["capcha_passed"]:
        start_text = await conn.fetchval("SELECT value FROM settings WHERE key='start_text'")
        await conn.close()
        await message.answer(start_text, parse_mode="HTML", reply_markup=await get_subs_keyboard())
    else:
        await conn.close()
        correct_emoji = random.choice(CAPCHA_EMOJIS)
        keyboard = get_capcha_keyboard(correct_emoji)
        
        await state.set_state(CapchaStates.waiting_capcha)
        await state.update_data(correct_emoji=correct_emoji)
        
        capcha_text = f"<blockquote><b>🔐 Проверка</b>\n<i>• Выберите смайл: {correct_emoji}</i>\n<i>• Нажмите на кнопку с этим смайлом</i>\n<i>• Это защита от ботов</i></blockquote>"
        
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
        await call.message.edit_text(f"<blockquote><b>❌ Неправильно!</b>\n<i>• Выберите смайл: {new_correct_emoji}</i>\n<i>• Попробуйте еще раз</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    
    await call.answer()

@dp.callback_query(lambda call: call.data == "check_subs")
async def check_subs(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    subscribed = await check_subscriptions(user_id)
    
    if not subscribed:
        await call.answer("❌ Вы не подписались на все каналы! Подпишитесь и нажмите снова.", show_alert=True)
        return
    
    conn = await get_conn()
    success_text = await conn.fetchval("SELECT value FROM settings WHERE key='success_text'")
    await conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛟 Поддержка", url="https://t.me/KrotProb")]
    ])
    
    await call.message.delete()
    await call.message.answer("🔑", reply_markup=await get_menu_keyboard())
    await asyncio.sleep(1)
    await call.message.answer(success_text, parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    await message.answer("<blockquote><b>🔐 Админ панель открыта</b>\n<i>• Выберите действие из меню ниже</i></blockquote>", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.callback_query(lambda call: call.data == "admin_reply")
async def admin_reply(call: types.CallbackQuery):
    await call.message.edit_text("<blockquote><b>📋 Управление reply кнопками</b>\n<i>• Выберите кнопку для редактирования</i></blockquote>", parse_mode="HTML", reply_markup=await get_reply_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_inline")
async def admin_inline(call: types.CallbackQuery):
    await call.message.edit_text("<blockquote><b>🔗 Управление инлайн кнопками</b>\n<i>• Выберите кнопку для редактирования</i></blockquote>", parse_mode="HTML", reply_markup=await get_inline_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_texts")
async def admin_texts(call: types.CallbackQuery):
    await call.message.edit_text("<blockquote><b>📝 Редактирование текстов</b>\n<i>• Выберите текст для изменения</i></blockquote>", parse_mode="HTML", reply_markup=get_texts_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_exit")
async def admin_exit(call: types.CallbackQuery):
    await call.message.delete()
    await call.answer()

# ========== Reply кнопки ==========
@dp.callback_query(lambda call: call.data.startswith("reply_edit_"))
async def reply_edit_select(call: types.CallbackQuery, state: FSMContext):
    btn_id = int(call.data.split("_")[2])
    conn = await get_conn()
    row = await conn.fetchrow("SELECT name, content FROM menu_buttons WHERE id=$1", btn_id)
    await conn.close()
    await state.update_data(waiting_reply_edit_id=btn_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data="reply_change_name"), InlineKeyboardButton(text="📝 Изменить текст", callback_data="reply_change_text")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply")]
    ])
    await call.message.edit_text(f"<blockquote><b>📋 Редактирование кнопки</b>\n\n<b>• Текущее название:</b> <code>{row['name']}</code>\n<b>• Текущий текст:</b> <code>{row['content']}</code>\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_name")
async def reply_change_name(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новое название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_edit_name)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_text")
async def reply_change_text(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новый текст:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_edit_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_reply_edit")
async def back_to_reply_edit(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    btn_id = data.get("waiting_reply_edit_id")
    if btn_id:
        conn = await get_conn()
        row = await conn.fetchrow("SELECT name, content FROM menu_buttons WHERE id=$1", btn_id)
        await conn.close()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data="reply_change_name"), InlineKeyboardButton(text="📝 Изменить текст", callback_data="reply_change_text")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply")]
        ])
        await call.message.edit_text(f"<blockquote><b>📋 Редактирование кнопки</b>\n\n<b>• Текущее название:</b> <code>{row['name']}</code>\n<b>• Текущий текст:</b> <code>{row['content']}</code>\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(None)
    await call.answer()

@dp.message(EditStates.waiting_reply_edit_name)
async def reply_save_edit_name(message: types.Message, state: FSMContext):
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
    data = await state.get_data()
    btn_id = data["waiting_reply_edit_id"]
    new_text = f"<blockquote>{message.html_text}</blockquote>"
    conn = await get_conn()
    await conn.execute("UPDATE menu_buttons SET content=$1 WHERE id=$2", new_text, btn_id)
    await conn.close()
    await message.answer((await get_system_message("Изменено: {name}")).replace("{name}", "текст"), parse_mode="HTML")
    await state.clear()
    await admin_reply(message)

@dp.callback_query(lambda call: call.data == "reply_add")
async def reply_add_start(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_add_name)
    await call.answer()

@dp.message(EditStates.waiting_reply_add_name)
async def reply_add_name(message: types.Message, state: FSMContext):
    await state.update_data(waiting_reply_add_name=message.text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply_add")]
    ])
    await message.answer(await get_system_message("Текст:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_add_text)

@dp.callback_query(lambda call: call.data == "back_to_reply_add")
async def back_to_reply_add(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_reply_add_name)
    await call.answer()

@dp.message(EditStates.waiting_reply_add_text)
async def reply_add_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["waiting_reply_add_name"]
    text = f"<blockquote>{message.html_text}</blockquote>"
    conn = await get_conn()
    await conn.execute("INSERT INTO menu_buttons (name, content) VALUES ($1, $2)", name, text)
    await conn.close()
    await message.answer((await get_system_message("Добавлено: {name}")).replace("{name}", name), parse_mode="HTML")
    await state.clear()
    await admin_reply(message)

@dp.callback_query(lambda call: call.data == "reply_delete")
async def reply_delete_start(call: types.CallbackQuery, state: FSMContext):
    conn = await get_conn()
    rows = await conn.fetch("SELECT id, name FROM menu_buttons ORDER BY id")
    await conn.close()
    if not rows:
        await call.message.edit_text(await get_system_message("Нет кнопок"), parse_mode="HTML")
        await call.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply")]
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

# ========== Инлайн кнопки ==========
@dp.callback_query(lambda call: call.data.startswith("inline_edit_"))
async def inline_edit_select(call: types.CallbackQuery, state: FSMContext):
    btn_id = int(call.data.split("_")[2])
    conn = await get_conn()
    row = await conn.fetchrow("SELECT name, url, chat_id FROM subs_buttons WHERE id=$1", btn_id)
    await conn.close()
    await state.update_data(waiting_inline_edit_id=btn_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data="inline_change_name"), InlineKeyboardButton(text="🔗 Изменить ссылку", callback_data="inline_change_url")],
        [InlineKeyboardButton(text="🆔 Изменить CHAT ID", callback_data="inline_change_chat_id")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline")]
    ])
    
    display_chat_id = row["chat_id"] if row["chat_id"] else "не указан"
    
    await call.message.edit_text(f"<blockquote><b>🔗 Редактирование кнопки</b>\n\n<b>• Название:</b> <code>{row['name']}</code>\n<b>• Ссылка:</b> <code>{row['url']}</code>\n<b>• CHAT ID:</b> <code>{display_chat_id}</code>\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_name")
async def inline_change_name(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новое название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_edit_name)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_url")
async def inline_change_url(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новая ссылка:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_edit_url)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_chat_id")
async def inline_change_chat_id(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline_edit")]
    ])
    await call.message.edit_text(await get_system_message("Новый CHAT ID:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_edit_chat_id)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_inline_edit")
async def back_to_inline_edit(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    btn_id = data.get("waiting_inline_edit_id")
    if btn_id:
        conn = await get_conn()
        row = await conn.fetchrow("SELECT name, url, chat_id FROM subs_buttons WHERE id=$1", btn_id)
        await conn.close()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data="inline_change_name"), InlineKeyboardButton(text="🔗 Изменить ссылку", callback_data="inline_change_url")],
            [InlineKeyboardButton(text="🆔 Изменить CHAT ID", callback_data="inline_change_chat_id")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline")]
        ])
        display_chat_id = row["chat_id"] if row["chat_id"] else "не указан"
        await call.message.edit_text(f"<blockquote><b>🔗 Редактирование кнопки</b>\n\n<b>• Название:</b> <code>{row['name']}</code>\n<b>• Ссылка:</b> <code>{row['url']}</code>\n<b>• CHAT ID:</b> <code>{display_chat_id}</code>\n\n<i>• Что хотите изменить?</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(None)
    await call.answer()

@dp.message(EditStates.waiting_inline_edit_name)
async def inline_save_edit_name(message: types.Message, state: FSMContext):
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_name)
    await call.answer()

@dp.message(EditStates.waiting_inline_add_name)
async def inline_add_name(message: types.Message, state: FSMContext):
    await state.update_data(waiting_inline_add_name=message.text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline_add_url")]
    ])
    await message.answer(await get_system_message("Ссылка:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_url)

@dp.callback_query(lambda call: call.data == "back_to_inline_add_url")
async def back_to_inline_add_url(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_name)
    await call.answer()

@dp.message(EditStates.waiting_inline_add_url)
async def inline_add_url(message: types.Message, state: FSMContext):
    await state.update_data(waiting_inline_add_url=message.text.strip())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline_add_chat_id")]
    ])
    await message.answer(await get_system_message("CHAT ID:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_chat_id)

@dp.callback_query(lambda call: call.data == "back_to_inline_add_chat_id")
async def back_to_inline_add_chat_id(call: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline")]
    ])
    await call.message.edit_text(await get_system_message("Название:"), parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_inline_add_name)
    await call.answer()

@dp.message(EditStates.waiting_inline_add_chat_id)
async def inline_add_chat_id(message: types.Message, state: FSMContext):
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
    conn = await get_conn()
    rows = await conn.fetch("SELECT id, name FROM subs_buttons ORDER BY id")
    await conn.close()
    if not rows:
        await call.message.edit_text(await get_system_message("Нет кнопок"), parse_mode="HTML")
        await call.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline")]
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

# ========== Тексты ==========
@dp.callback_query(lambda call: call.data == "text_start")
async def edit_start_text(call: types.CallbackQuery, state: FSMContext):
    conn = await get_conn()
    current = await conn.fetchval("SELECT value FROM settings WHERE key='start_text'")
    await conn.close()
    await state.update_data(text_key="start_text")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_texts")]
    ])
    await call.message.edit_text(f"<blockquote><b>📝 Текущий текст приветствия</b>\n<code>{current}</code>\n\n<i>• Введите новый текст</i>\n<i>• Поддерживается HTML-форматирование</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_success")
async def edit_success_text(call: types.CallbackQuery, state: FSMContext):
    conn = await get_conn()
    current = await conn.fetchval("SELECT value FROM settings WHERE key='success_text'")
    await conn.close()
    await state.update_data(text_key="success_text")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_texts")]
    ])
    await call.message.edit_text(f"<blockquote><b>✅ Текущий текст успеха</b>\n<code>{current}</code>\n\n<i>• Введите новый текст</i>\n<i>• Поддерживается HTML-форматирование</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_error")
async def edit_error_text(call: types.CallbackQuery, state: FSMContext):
    conn = await get_conn()
    current = await conn.fetchval("SELECT value FROM settings WHERE key='error_text'")
    await conn.close()
    await state.update_data(text_key="error_text")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_texts")]
    ])
    await call.message.edit_text(f"<blockquote><b>❌ Текущий текст ошибки</b>\n<code>{current}</code>\n\n<i>• Введите новый текст</i>\n<i>• Поддерживается HTML-форматирование</i></blockquote>", parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_texts")
async def back_to_texts(call: types.CallbackQuery):
    await call.message.edit_text("<blockquote><b>📝 Редактирование текстов</b>\n<i>• Выберите текст для изменения</i></blockquote>", parse_mode="HTML", reply_markup=get_texts_keyboard())
    await call.answer()

@dp.message(EditStates.waiting_text)
async def save_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text_key = data["text_key"]
    new_text = f"<blockquote>{message.html_text}</blockquote>"
    conn = await get_conn()
    await conn.execute("UPDATE settings SET value=$1 WHERE key=$2", new_text, text_key)
    await conn.close()
    await message.answer("<blockquote><b>✅ Сохранено</b></blockquote>", parse_mode="HTML")
    await state.clear()
    await admin_texts(message)

# ========== Назад ==========
@dp.callback_query(lambda call: call.data == "back_to_reply")
async def back_to_reply(call: types.CallbackQuery):
    await call.message.edit_text("<blockquote><b>📋 Управление reply кнопками</b>\n<i>• Выберите кнопку для редактирования</i></blockquote>", parse_mode="HTML", reply_markup=await get_reply_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_inline")
async def back_to_inline(call: types.CallbackQuery):
    await call.message.edit_text("<blockquote><b>🔗 Управление инлайн кнопками</b>\n<i>• Выберите кнопку для редактирования</i></blockquote>", parse_mode="HTML", reply_markup=await get_inline_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_admin")
async def back_to_admin_callback(call: types.CallbackQuery):
    await call.message.edit_text("<blockquote><b>🔐 Админ панель открыта</b>\n<i>• Выберите действие из меню ниже</i></blockquote>", parse_mode="HTML", reply_markup=get_admin_keyboard())
    await call.answer()

# ========== Кнопки пользователя ==========
@dp.message(lambda message: True)
async def handle_menu_buttons(message: types.Message):
    conn = await get_conn()
    row = await conn.fetchrow("SELECT content FROM menu_buttons WHERE name=$1", message.text)
    await conn.close()
    if row:
        await message.answer(row["content"], parse_mode="HTML")

async def main():
    await init_db()
    await init_defaults()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
