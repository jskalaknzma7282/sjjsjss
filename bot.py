import asyncio
import os
import sqlite3
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS menu_buttons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    content TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS subs_buttons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    url TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS system_messages (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
conn.commit()

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

def init_defaults():
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("start_text", "<b>Добро пожаловать!</b>\n<i>Подпишитесь на каналы:</i>"))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("success_text", "<b>Успешная регистрация</b>"))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("error_text", "<b>Ошибка</b>\n<i>Вы не подписались на все каналы</i>"))
    
    system_defaults = {
        "Название:": "<b>Название:</b>",
        "Текст:": "<b>Текст:</b>",
        "Ссылка:": "<b>Ссылка</b> <i>(@username или полная)</i>:",
        "Новый текст:": "<b>Новый текст:</b>",
        "Новое название:": "<b>Новое название:</b>",
        "Новая ссылка:": "<b>Новая ссылка</b> <i>(@username или полная)</i>:",
        "Добавлено: {name}": "<b>Добавлено:</b> {name}",
        "Удалено: {name}": "<b>Удалено:</b> {name}",
        "Изменено: {name}": "<b>Изменено:</b> {name}",
        "Нет кнопок": "<b>Нет кнопок</b>",
        "Ошибка": "<b>Ошибка</b>",
        "Выберите:": "<b>Выберите:</b>",
        "Введите ID:": "<b>Введите ID:</b>"
    }
    for key, value in system_defaults.items():
        cursor.execute("INSERT OR IGNORE INTO system_messages (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

init_defaults()

def get_system_message(key: str) -> str:
    cursor.execute("SELECT value FROM system_messages WHERE key=?", (key,))
    row = cursor.fetchone()
    return row[0] if row else key

def get_menu_keyboard():
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = [KeyboardButton(text=row[0]) for row in cursor.fetchall()]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_subs_keyboard():
    cursor.execute("SELECT id, name, url FROM subs_buttons ORDER BY id")
    rows = cursor.fetchall()
    buttons = []
    for id, name, url in rows:
        buttons.append([InlineKeyboardButton(text=name, url=url)])
    buttons.append([InlineKeyboardButton(text="Проверить", callback_data="check_subs")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Reply кнопки"), KeyboardButton(text="Инлайн кнопки")],
            [KeyboardButton(text="Тексты"), KeyboardButton(text="Настройки")],
            [KeyboardButton(text="Выйти")]
        ],
        resize_keyboard=True
    )

def get_settings_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Системные сообщения")], [KeyboardButton(text="Назад")]],
        resize_keyboard=True
    )

def get_reply_list_keyboard():
    cursor.execute("SELECT id, name FROM menu_buttons ORDER BY id")
    buttons = cursor.fetchall()
    keyboard = []
    row = []
    for btn_id, name in buttons:
        row.append(InlineKeyboardButton(text=name, callback_data=f"reply_edit_{btn_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="+ Добавить", callback_data="reply_add"), InlineKeyboardButton(text="- Удалить", callback_data="reply_delete")])
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_inline_list_keyboard():
    cursor.execute("SELECT id, name FROM subs_buttons ORDER BY id")
    buttons = cursor.fetchall()
    keyboard = []
    row = []
    for btn_id, name in buttons:
        row.append(InlineKeyboardButton(text=name, callback_data=f"inline_edit_{btn_id}"))
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

def get_system_keyboard():
    system_keys = [
        "Название:", "Текст:", "Ссылка:",
        "Новый текст:", "Новое название:", "Новая ссылка:",
        "Добавлено: {name}", "Удалено: {name}", "Изменено: {name}",
        "Нет кнопок", "Ошибка", "Выберите:", "Введите ID:"
    ]
    keyboard = []
    row = []
    for key in system_keys:
        row.append(InlineKeyboardButton(text=key[:30], callback_data=f"system_{key.replace(' ', '_').replace('{', '').replace('}', '')}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

class EditStates(StatesGroup):
    waiting_reply_add_name = State()
    waiting_reply_add_text = State()
    waiting_reply_delete_id = State()
    waiting_reply_edit_name = State()
    waiting_reply_edit_text = State()
    waiting_reply_edit_id = State()
    waiting_inline_add_name = State()
    waiting_inline_add_url = State()
    waiting_inline_delete_id = State()
    waiting_inline_edit_name = State()
    waiting_inline_edit_url = State()
    waiting_inline_edit_id = State()
    waiting_text = State()
    waiting_system = State()

@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute("SELECT value FROM settings WHERE key='start_text'")
    start_text = cursor.fetchone()[0]
    await message.answer(start_text, parse_mode="HTML", reply_markup=get_subs_keyboard())

@dp.callback_query(lambda call: call.data == "check_subs")
async def check_subs(call: types.CallbackQuery):
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    success_text = cursor.fetchone()[0]
    await call.message.delete()
    await call.message.answer(success_text, parse_mode="HTML", reply_markup=get_menu_keyboard())
    await call.answer()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    await message.answer("<b>Админ-панель</b>", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.message(lambda message: message.text == "Выйти")
async def exit_admin(message: types.Message):
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    success_text = cursor.fetchone()[0]
    await message.answer(success_text, parse_mode="HTML", reply_markup=get_menu_keyboard())

@dp.message(lambda message: message.text == "Reply кнопки")
async def reply_buttons_menu(message: types.Message):
    await message.answer("<b>Reply кнопки</b>", parse_mode="HTML", reply_markup=get_reply_list_keyboard())

@dp.message(lambda message: message.text == "Инлайн кнопки")
async def inline_buttons_menu(message: types.Message):
    await message.answer("<b>Инлайн кнопки</b>", parse_mode="HTML", reply_markup=get_inline_list_keyboard())

@dp.message(lambda message: message.text == "Тексты")
async def texts_menu(message: types.Message):
    await message.answer("<b>Тексты</b>", parse_mode="HTML", reply_markup=get_texts_keyboard())

@dp.message(lambda message: message.text == "Настройки")
async def settings_menu(message: types.Message):
    await message.answer("<b>Настройки</b>", parse_mode="HTML", reply_markup=get_settings_keyboard())

@dp.message(lambda message: message.text == "Системные сообщения")
async def system_messages_menu(message: types.Message):
    await message.answer("<b>Системные сообщения</b>", parse_mode="HTML", reply_markup=get_system_keyboard())

@dp.message(lambda message: message.text == "Назад")
async def back_to_admin(message: types.Message):
    await message.answer("<b>Админ-панель</b>", parse_mode="HTML", reply_markup=get_admin_keyboard())

# ========== Reply кнопки - редактирование ==========
@dp.callback_query(lambda call: call.data.startswith("reply_edit_"))
async def reply_edit_select(call: types.CallbackQuery, state: FSMContext):
    btn_id = int(call.data.split("_")[2])
    cursor.execute("SELECT name, content FROM menu_buttons WHERE id=?", (btn_id,))
    name, content = cursor.fetchone()
    await state.update_data(waiting_reply_edit_id=btn_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить название", callback_data="reply_change_name")],
        [InlineKeyboardButton(text="Изменить текст", callback_data="reply_change_text")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply")]
    ])
    await call.message.edit_text(f"<b>Текущее название:</b> <code>{name}</code>\n\n<b>Текущий текст:</b> <code>{content}</code>\n\n<i>Что меняем?</i>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_name")
async def reply_change_name(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(get_system_message("Новое название:"), parse_mode="HTML")
    await state.set_state(EditStates.waiting_reply_edit_name)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_text")
async def reply_change_text(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(get_system_message("Новый текст:"), parse_mode="HTML")
    await state.set_state(EditStates.waiting_reply_edit_text)
    await call.answer()

@dp.message(EditStates.waiting_reply_edit_name)
async def reply_save_edit_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["waiting_reply_edit_id"]
    new_name = message.text
    cursor.execute("UPDATE menu_buttons SET name=? WHERE id=?", (new_name, btn_id))
    conn.commit()
    await message.answer(get_system_message("Изменено: {name}").replace("{name}", new_name), parse_mode="HTML")
    await state.clear()
    await reply_buttons_menu(message)

@dp.message(EditStates.waiting_reply_edit_text)
async def reply_save_edit_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["waiting_reply_edit_id"]
    new_text = message.html_text
    cursor.execute("UPDATE menu_buttons SET content=? WHERE id=?", (new_text, btn_id))
    conn.commit()
    await message.answer(get_system_message("Изменено: {name}").replace("{name}", "текст"), parse_mode="HTML")
    await state.clear()
    await reply_buttons_menu(message)

# ========== Reply кнопки - добавление ==========
@dp.callback_query(lambda call: call.data == "reply_add")
async def reply_add_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(get_system_message("Название:"), parse_mode="HTML")
    await state.set_state(EditStates.waiting_reply_add_name)
    await call.answer()

@dp.message(EditStates.waiting_reply_add_name)
async def reply_add_name(message: types.Message, state: FSMContext):
    await state.update_data(waiting_reply_add_name=message.text)
    await message.answer(get_system_message("Текст:"), parse_mode="HTML")
    await state.set_state(EditStates.waiting_reply_add_text)

@dp.message(EditStates.waiting_reply_add_text)
async def reply_add_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["waiting_reply_add_name"]
    text = message.html_text
    cursor.execute("INSERT INTO menu_buttons (name, content) VALUES (?, ?)", (name, text))
    conn.commit()
    await message.answer(get_system_message("Добавлено: {name}").replace("{name}", name), parse_mode="HTML")
    await state.clear()
    await reply_buttons_menu(message)

# ========== Reply кнопки - удаление ==========
@dp.callback_query(lambda call: call.data == "reply_delete")
async def reply_delete_start(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT id, name FROM menu_buttons ORDER BY id")
    buttons = cursor.fetchall()
    if not buttons:
        await call.message.edit_text(get_system_message("Нет кнопок"), parse_mode="HTML")
        await call.answer()
        return
    text = get_system_message("Выберите:") + "\n\n"
    for btn_id, name in buttons:
        text += f"{btn_id}. {name}\n"
    text += f"\n{get_system_message('Введите ID:')}"
    await call.message.edit_text(text, parse_mode="HTML")
    await state.set_state(EditStates.waiting_reply_delete_id)
    await call.answer()

@dp.message(EditStates.waiting_reply_delete_id)
async def reply_delete_save(message: types.Message, state: FSMContext):
    try:
        btn_id = int(message.text)
        cursor.execute("SELECT name FROM menu_buttons WHERE id=?", (btn_id,))
        row = cursor.fetchone()
        if row:
            name = row[0]
            cursor.execute("DELETE FROM menu_buttons WHERE id=?", (btn_id,))
            conn.commit()
            await message.answer(get_system_message("Удалено: {name}").replace("{name}", name), parse_mode="HTML")
        else:
            await message.answer(get_system_message("Ошибка"), parse_mode="HTML")
    except ValueError:
        await message.answer(get_system_message("Ошибка"), parse_mode="HTML")
    await state.clear()
    await reply_buttons_menu(message)

# ========== Инлайн кнопки - редактирование ==========
@dp.callback_query(lambda call: call.data.startswith("inline_edit_"))
async def inline_edit_select(call: types.CallbackQuery, state: FSMContext):
    btn_id = int(call.data.split("_")[2])
    cursor.execute("SELECT name, url FROM subs_buttons WHERE id=?", (btn_id,))
    name, url = cursor.fetchone()
    await state.update_data(waiting_inline_edit_id=btn_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить название", callback_data="inline_change_name")],
        [InlineKeyboardButton(text="Изменить ссылку", callback_data="inline_change_url")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline")]
    ])
    await call.message.edit_text(f"<b>Текущее название:</b> <code>{name}</code>\n\n<b>Текущая ссылка:</b> <code>{url}</code>\n\n<i>Что меняем?</i>", parse_mode="HTML", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_name")
async def inline_change_name(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(get_system_message("Новое название:"), parse_mode="HTML")
    await state.set_state(EditStates.waiting_inline_edit_name)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_url")
async def inline_change_url(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(get_system_message("Новая ссылка:"), parse_mode="HTML")
    await state.set_state(EditStates.waiting_inline_edit_url)
    await call.answer()

@dp.message(EditStates.waiting_inline_edit_name)
async def inline_save_edit_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["waiting_inline_edit_id"]
    new_name = message.text
    cursor.execute("UPDATE subs_buttons SET name=? WHERE id=?", (new_name, btn_id))
    conn.commit()
    await message.answer(get_system_message("Изменено: {name}").replace("{name}", new_name), parse_mode="HTML")
    await state.clear()
    await inline_buttons_menu(message)

@dp.message(EditStates.waiting_inline_edit_url)
async def inline_save_edit_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["waiting_inline_edit_id"]
    new_url = normalize_url(message.text)
    cursor.execute("UPDATE subs_buttons SET url=? WHERE id=?", (new_url, btn_id))
    conn.commit()
    await message.answer(get_system_message("Изменено: {name}").replace("{name}", "ссылка"), parse_mode="HTML")
    await state.clear()
    await inline_buttons_menu(message)

# ========== Инлайн кнопки - добавление ==========
@dp.callback_query(lambda call: call.data == "inline_add")
async def inline_add_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(get_system_message("Название:"), parse_mode="HTML")
    await state.set_state(EditStates.waiting_inline_add_name)
    await call.answer()

@dp.message(EditStates.waiting_inline_add_name)
async def inline_add_name(message: types.Message, state: FSMContext):
    await state.update_data(waiting_inline_add_name=message.text)
    await message.answer(get_system_message("Ссылка:"), parse_mode="HTML")
    await state.set_state(EditStates.waiting_inline_add_url)

@dp.message(EditStates.waiting_inline_add_url)
async def inline_add_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["waiting_inline_add_name"]
    url = normalize_url(message.text)
    cursor.execute("INSERT INTO subs_buttons (name, url) VALUES (?, ?)", (name, url))
    conn.commit()
    await message.answer(get_system_message("Добавлено: {name}").replace("{name}", name), parse_mode="HTML")
    await state.clear()
    await inline_buttons_menu(message)

# ========== Инлайн кнопки - удаление ==========
@dp.callback_query(lambda call: call.data == "inline_delete")
async def inline_delete_start(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT id, name FROM subs_buttons ORDER BY id")
    buttons = cursor.fetchall()
    if not buttons:
        await call.message.edit_text(get_system_message("Нет кнопок"), parse_mode="HTML")
        await call.answer()
        return
    text = get_system_message("Выберите:") + "\n\n"
    for btn_id, name in buttons:
        text += f"{btn_id}. {name}\n"
    text += f"\n{get_system_message('Введите ID:')}"
    await call.message.edit_text(text, parse_mode="HTML")
    await state.set_state(EditStates.waiting_inline_delete_id)
    await call.answer()

@dp.message(EditStates.waiting_inline_delete_id)
async def inline_delete_save(message: types.Message, state: FSMContext):
    try:
        btn_id = int(message.text)
        cursor.execute("SELECT name FROM subs_buttons WHERE id=?", (btn_id,))
        row = cursor.fetchone()
        if row:
            name = row[0]
            cursor.execute("DELETE FROM subs_buttons WHERE id=?", (btn_id,))
            conn.commit()
            await message.answer(get_system_message("Удалено: {name}").replace("{name}", name), parse_mode="HTML")
        else:
            await message.answer(get_system_message("Ошибка"), parse_mode="HTML")
    except ValueError:
        await message.answer(get_system_message("Ошибка"), parse_mode="HTML")
    await state.clear()
    await inline_buttons_menu(message)

# ========== Тексты ==========
@dp.callback_query(lambda call: call.data == "text_start")
async def edit_start_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='start_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="start_text")
    await call.message.edit_text(f"<b>Текущий текст:</b>\n<code>{current}</code>\n\n<i>Введите новый текст</i>", parse_mode="HTML")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_success")
async def edit_success_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="success_text")
    await call.message.edit_text(f"<b>Текущий текст:</b>\n<code>{current}</code>\n\n<i>Введите новый текст</i>", parse_mode="HTML")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_error")
async def edit_error_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='error_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="error_text")
    await call.message.edit_text(f"<b>Текущий текст:</b>\n<code>{current}</code>\n\n<i>Введите новый текст</i>", parse_mode="HTML")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.message(EditStates.waiting_text)
async def save_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text_key = data["text_key"]
    new_text = message.html_text
    cursor.execute("UPDATE settings SET value=? WHERE key=?", (new_text, text_key))
    conn.commit()
    await message.answer("<b>Сохранено</b>", parse_mode="HTML")
    await state.clear()
    await texts_menu(message)

# ========== Системные сообщения ==========
@dp.callback_query(lambda call: call.data.startswith("system_"))
async def edit_system_message(call: types.CallbackQuery, state: FSMContext):
    key_raw = call.data.replace("system_", "").replace("_", " ").replace("name", "{name}")
    if "Добавлено" in key_raw:
        key = "Добавлено: {name}"
    elif "Удалено" in key_raw:
        key = "Удалено: {name}"
    elif "Изменено" in key_raw:
        key = "Изменено: {name}"
    elif "Название" in key_raw and "Новое" not in key_raw:
        key = "Название:"
    elif "Текст" in key_raw and "Новый" not in key_raw and "Новое" not in key_raw:
        key = "Текст:"
    elif "Ссылка" in key_raw and "Новая" not in key_raw:
        key = "Ссылка:"
    elif "Новый текст" in key_raw:
        key = "Новый текст:"
    elif "Новое название" in key_raw:
        key = "Новое название:"
    elif "Новая ссылка" in key_raw:
        key = "Новая ссылка:"
    elif "Нет кнопок" in key_raw:
        key = "Нет кнопок"
    elif "Ошибка" in key_raw:
        key = "Ошибка"
    elif "Выберите" in key_raw:
        key = "Выберите:"
    elif "Введите ID" in key_raw:
        key = "Введите ID:"
    else:
        key = key_raw
    cursor.execute("SELECT value FROM system_messages WHERE key=?", (key,))
    current = cursor.fetchone()[0]
    await state.update_data(system_key=key)
    await call.message.edit_text(f"<b>Текущее сообщение:</b>\n<code>{current}</code>\n\n<i>Введите новое</i>", parse_mode="HTML")
    await state.set_state(EditStates.waiting_system)
    await call.answer()

@dp.message(EditStates.waiting_system)
async def save_system_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    system_key = data["system_key"]
    new_text = message.html_text
    cursor.execute("UPDATE system_messages SET value=? WHERE key=?", (new_text, system_key))
    conn.commit()
    await message.answer("<b>Сохранено</b>", parse_mode="HTML")
    await state.clear()
    await system_messages_menu(message)

# ========== Назад (удаляет сообщение) ==========
@dp.callback_query(lambda call: call.data == "back_to_reply")
async def back_to_reply(call: types.CallbackQuery):
    await call.message.delete()
    await reply_buttons_menu(call.message)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_inline")
async def back_to_inline(call: types.CallbackQuery):
    await call.message.delete()
    await inline_buttons_menu(call.message)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_admin")
async def back_to_admin_callback(call: types.CallbackQuery):
    await call.message.delete()
    await admin_panel(call.message)
    await call.answer()

# ========== Кнопки пользователя ==========
@dp.message(lambda message: True)
async def handle_menu_buttons(message: types.Message):
    cursor.execute("SELECT content FROM menu_buttons WHERE name=?", (message.text,))
    row = cursor.fetchone()
    if row:
        await message.answer(row[0], parse_mode="HTML")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
