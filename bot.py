import asyncio
import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

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
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Reply кнопки"), KeyboardButton(text="Инлайн кнопки")],
            [KeyboardButton(text="Тексты"), KeyboardButton(text="Настройки")],
            [KeyboardButton(text="Выйти")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_settings_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Системные сообщения")],
            [KeyboardButton(text="Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_reply_edit_keyboard(buttons):
    keyboard = []
    row = []
    for i, (btn_id, name) in enumerate(buttons):
        row.append(InlineKeyboardButton(text=name, callback_data=f"reply_edit_{btn_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_reply_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_inline_edit_keyboard(buttons):
    keyboard = []
    row = []
    for i, (btn_id, name) in enumerate(buttons):
        row.append(InlineKeyboardButton(text=name, callback_data=f"inline_edit_{btn_id}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_inline_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_texts_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="Приветствие", callback_data="text_start")],
        [InlineKeyboardButton(text="Успешная регистрация", callback_data="text_success")],
        [InlineKeyboardButton(text="Ошибка подписок", callback_data="text_error")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_texts_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_system_keyboard():
    system_keys = [
        "Название:", "Текст:", "Ссылка:",
        "Новый текст:", "Новое название:", "Новая ссылка:",
        "Добавлено: {name}", "Удалено: {name}", "Изменено: {name}",
        "Нет кнопок", "Ошибка", "Выберите:",
        "Введите ID:"
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
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_system_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

class EditStates(StatesGroup):
    waiting_reply_name = State()
    waiting_reply_text = State()
    waiting_inline_name = State()
    waiting_inline_url = State()
    waiting_text = State()
    waiting_system = State()

# Дефолтные значения
def init_defaults():
    cursor.execute("SELECT COUNT(*) FROM menu_buttons")
    if cursor.fetchone()[0] == 0:
        default_buttons = [
            ("Сплит и вб части", "Текст для сплит и вб части"),
            ("Ворк чернуха", "Текст для ворк чернуха"),
            ("Американский ютуб", "Текст для американский ютуб"),
            ("Введение каналов(Админ)", "Текст для введение каналов"),
            ("Трафик(УБТ)", "Текст для трафик"),
            ("Для начинающих", "Текст для начинающих"),
            ("Поддержка 🆘", "Текст для поддержки")
        ]
        for name, content in default_buttons:
            cursor.execute("INSERT INTO menu_buttons (name, content) VALUES (?, ?)", (name, content))
    
    cursor.execute("SELECT COUNT(*) FROM subs_buttons")
    if cursor.fetchone()[0] == 0:
        default_subs = [
            ("Канал 1", "https://t.me/example1"),
            ("Канал 2", "https://t.me/example2"),
            ("Канал 3", "https://t.me/example3"),
            ("Канал 4", "https://t.me/example4"),
            ("Канал 5", "https://t.me/example5")
        ]
        for name, url in default_subs:
            cursor.execute("INSERT INTO subs_buttons (name, url) VALUES (?, ?)", (name, url))
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("start_text", "Добро пожаловать! Подпишитесь на каналы:"))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("success_text", "Успешная регистрация"))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("error_text", "Вы не подписались на все каналы!"))
    
    system_defaults = {
        "Название:": "Название:",
        "Текст:": "Текст:",
        "Ссылка:": "Ссылка (@username или полная):",
        "Новый текст:": "Новый текст:",
        "Новое название:": "Новое название:",
        "Новая ссылка:": "Новая ссылка:",
        "Добавлено: {name}": "Добавлено: {name}",
        "Удалено: {name}": "Удалено: {name}",
        "Изменено: {name}": "Изменено: {name}",
        "Нет кнопок": "Нет кнопок",
        "Ошибка": "Ошибка",
        "Выберите:": "Выберите:",
        "Введите ID:": "Введите ID:"
    }
    for key, value in system_defaults.items():
        cursor.execute("INSERT OR IGNORE INTO system_messages (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()

init_defaults()

# ========== Основные команды ==========
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
    await message.answer("Админ-панель", reply_markup=get_admin_keyboard())

@dp.message(lambda message: message.text == "Выйти")
async def exit_admin(message: types.Message):
    await message.answer("Выход", reply_markup=types.ReplyKeyboardRemove())

# ========== Reply кнопки ==========
@dp.message(lambda message: message.text == "Reply кнопки")
async def reply_buttons_menu(message: types.Message):
    cursor.execute("SELECT id, name FROM menu_buttons ORDER BY id")
    buttons = cursor.fetchall()
    await message.answer("Выберите reply кнопку:", reply_markup=get_reply_edit_keyboard(buttons))

@dp.callback_query(lambda call: call.data.startswith("reply_edit_"))
async def reply_edit_select(call: types.CallbackQuery, state: FSMContext):
    btn_id = int(call.data.split("_")[2])
    cursor.execute("SELECT name, content FROM menu_buttons WHERE id=?", (btn_id,))
    name, content = cursor.fetchone()
    await state.update_data(btn_id=btn_id, btn_name=name)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить название", callback_data="reply_change_name")],
        [InlineKeyboardButton(text="Изменить текст", callback_data="reply_change_text")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_reply_menu")]
    ])
    await call.message.edit_text(f"Текущее название: {name}\n\nТекущий текст: {content}\n\nЧто меняем?", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_name")
async def reply_change_name(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите новое название:")
    await state.set_state(EditStates.waiting_reply_name)
    await call.answer()

@dp.callback_query(lambda call: call.data == "reply_change_text")
async def reply_change_text(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите новый текст (можно с форматированием):")
    await state.set_state(EditStates.waiting_reply_text)
    await call.answer()

@dp.message(EditStates.waiting_reply_name)
async def reply_save_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["btn_id"]
    new_name = message.text
    cursor.execute("UPDATE menu_buttons SET name=? WHERE id=?", (new_name, btn_id))
    conn.commit()
    await message.answer(f"Название изменено на: {new_name}")
    await state.clear()
    await reply_buttons_menu(message)

@dp.message(EditStates.waiting_reply_text)
async def reply_save_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["btn_id"]
    new_text = message.html_text
    cursor.execute("UPDATE menu_buttons SET content=? WHERE id=?", (new_text, btn_id))
    conn.commit()
    await message.answer("Текст изменен")
    await state.clear()
    await reply_buttons_menu(message)

# ========== Инлайн кнопки ==========
@dp.message(lambda message: message.text == "Инлайн кнопки")
async def inline_buttons_menu(message: types.Message):
    cursor.execute("SELECT id, name FROM subs_buttons ORDER BY id")
    buttons = cursor.fetchall()
    await message.answer("Выберите инлайн кнопку:", reply_markup=get_inline_edit_keyboard(buttons))

@dp.callback_query(lambda call: call.data.startswith("inline_edit_"))
async def inline_edit_select(call: types.CallbackQuery, state: FSMContext):
    btn_id = int(call.data.split("_")[2])
    cursor.execute("SELECT name, url FROM subs_buttons WHERE id=?", (btn_id,))
    name, url = cursor.fetchone()
    await state.update_data(btn_id=btn_id, btn_name=name)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить название", callback_data="inline_change_name")],
        [InlineKeyboardButton(text="Изменить ссылку", callback_data="inline_change_url")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_inline_menu")]
    ])
    await call.message.edit_text(f"Текущее название: {name}\n\nТекущая ссылка: {url}\n\nЧто меняем?", reply_markup=keyboard)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_name")
async def inline_change_name(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите новое название:")
    await state.set_state(EditStates.waiting_inline_name)
    await call.answer()

@dp.callback_query(lambda call: call.data == "inline_change_url")
async def inline_change_url(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите новую ссылку (@username или полную):")
    await state.set_state(EditStates.waiting_inline_url)
    await call.answer()

@dp.message(EditStates.waiting_inline_name)
async def inline_save_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["btn_id"]
    new_name = message.text
    cursor.execute("UPDATE subs_buttons SET name=? WHERE id=?", (new_name, btn_id))
    conn.commit()
    await message.answer(f"Название изменено на: {new_name}")
    await state.clear()
    await inline_buttons_menu(message)

@dp.message(EditStates.waiting_inline_url)
async def inline_save_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["btn_id"]
    new_url = normalize_url(message.text)
    cursor.execute("UPDATE subs_buttons SET url=? WHERE id=?", (new_url, btn_id))
    conn.commit()
    await message.answer(f"Ссылка изменена на: {new_url}")
    await state.clear()
    await inline_buttons_menu(message)

# ========== Тексты ==========
@dp.message(lambda message: message.text == "Тексты")
async def texts_menu(message: types.Message):
    await message.answer("Выберите текст для редактирования:", reply_markup=get_texts_keyboard())

@dp.callback_query(lambda call: call.data == "text_start")
async def edit_start_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='start_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="start_text")
    await call.message.edit_text(f"Текущий текст:\n{current}\n\nВведите новый текст (можно с форматированием):")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_success")
async def edit_success_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="success_text")
    await call.message.edit_text(f"Текущий текст:\n{current}\n\nВведите новый текст (можно с форматированием):")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_error")
async def edit_error_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='error_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="error_text")
    await call.message.edit_text(f"Текущий текст:\n{current}\n\nВведите новый текст (можно с форматированием):")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.message(EditStates.waiting_text)
async def save_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text_key = data["text_key"]
    new_text = message.html_text
    cursor.execute("UPDATE settings SET value=? WHERE key=?", (new_text, text_key))
    conn.commit()
    await message.answer("Текст сохранен")
    await state.clear()

# ========== Настройки ==========
@dp.message(lambda message: message.text == "Настройки")
async def settings_menu(message: types.Message):
    await message.answer("Настройки", reply_markup=get_settings_keyboard())

@dp.message(lambda message: message.text == "Системные сообщения")
async def system_messages_menu(message: types.Message):
    await message.answer("Выберите системное сообщение для редактирования:", reply_markup=get_system_keyboard())

@dp.callback_query(lambda call: call.data.startswith("system_"))
async def edit_system_message(call: types.CallbackQuery, state: FSMContext):
    key_raw = call.data.replace("system_", "").replace("_", " ").replace("name", "{name}")
    # Восстанавливаем оригинальный ключ
    if "Добавлено" in key_raw:
        key = "Добавлено: {name}"
    elif "Удалено" in key_raw:
        key = "Удалено: {name}"
    elif "Изменено" in key_raw:
        key = "Изменено: {name}"
    elif "Название" in key_raw:
        key = "Название:"
    elif "Текст" in key_raw and "Новый" not in key_raw:
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
    current = cursor.fetchone()
    if current:
        await state.update_data(system_key=key)
        await call.message.edit_text(f"Текущее сообщение:\n{current[0]}\n\nВведите новое:")
        await state.set_state(EditStates.waiting_system)
    await call.answer()

@dp.message(EditStates.waiting_system)
async def save_system_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    system_key = data["system_key"]
    new_text = message.text
    cursor.execute("UPDATE system_messages SET value=? WHERE key=?", (new_text, system_key))
    conn.commit()
    await message.answer("Сохранено")
    await state.clear()

# ========== Назад ==========
@dp.callback_query(lambda call: call.data == "back_to_reply_menu")
async def back_to_reply(call: types.CallbackQuery):
    await call.message.delete()
    await reply_buttons_menu(call.message)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_inline_menu")
async def back_to_inline(call: types.CallbackQuery):
    await call.message.delete()
    await inline_buttons_menu(call.message)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_texts_menu")
async def back_to_texts(call: types.CallbackQuery):
    await call.message.delete()
    await texts_menu(call.message)
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_system_menu")
async def back_to_system(call: types.CallbackQuery):
    await call.message.delete()
    await system_messages_menu(call.message)
    await call.answer()

@dp.message(lambda message: message.text == "Назад")
async def back_to_admin(message: types.Message):
    await message.answer("Админ-панель", reply_markup=get_admin_keyboard())

# ========== Обработка кнопок пользователя ==========
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
