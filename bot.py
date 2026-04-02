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

# Таблица для reply кнопок меню
cursor.execute("""
CREATE TABLE IF NOT EXISTS menu_buttons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    content TEXT
)
""")

# Таблица для инлайн кнопок подписок
cursor.execute("""
CREATE TABLE IF NOT EXISTS subs_buttons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    url TEXT
)
""")

# Таблица для настроек
cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

# Таблица для динамической админ-панели
cursor.execute("""
CREATE TABLE IF NOT EXISTS admin_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    sort_order INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS admin_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER,
    name TEXT,
    action_type TEXT,
    action_target TEXT,
    sort_order INTEGER DEFAULT 0,
    FOREIGN KEY (section_id) REFERENCES admin_sections(id)
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

def get_dynamic_admin_keyboard():
    cursor.execute("SELECT id, name FROM admin_sections ORDER BY sort_order")
    sections = cursor.fetchall()
    buttons = []
    for section_id, section_name in sections:
        buttons.append([KeyboardButton(text=section_name)])
    buttons.append([KeyboardButton(text="Настройка админки")])
    buttons.append([KeyboardButton(text="Выйти")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_section_items_keyboard(section_id):
    cursor.execute("SELECT id, name FROM admin_items WHERE section_id=? ORDER BY sort_order", (section_id,))
    items = cursor.fetchall()
    buttons = []
    for item_id, item_name in items:
        buttons.append([KeyboardButton(text=item_name)])
    buttons.append([KeyboardButton(text="Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_settings_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить раздел")],
            [KeyboardButton(text="Удалить раздел")],
            [KeyboardButton(text="Переименовать раздел")],
            [KeyboardButton(text="Добавить пункт")],
            [KeyboardButton(text="Удалить пункт")],
            [KeyboardButton(text="Переименовать пункт")],
            [KeyboardButton(text="Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

class AdminStates(StatesGroup):
    # Динамическая админка
    waiting_new_section = State()
    waiting_delete_section = State()
    waiting_rename_section_old = State()
    waiting_rename_section_new = State()
    waiting_new_item_section = State()
    waiting_new_item_name = State()
    waiting_delete_item = State()
    waiting_rename_item_select = State()
    waiting_rename_item_new = State()
    # Reply кнопки
    waiting_reply_name = State()
    waiting_reply_content = State()
    waiting_reply_delete = State()
    waiting_reply_edit_name_old = State()
    waiting_reply_edit_name_new = State()
    waiting_reply_edit_content = State()
    # Инлайн кнопки
    waiting_subs_name = State()
    waiting_subs_url = State()
    waiting_subs_delete_id = State()
    waiting_subs_edit_id = State()
    waiting_subs_edit_name = State()
    waiting_subs_edit_url = State()
    # Тексты
    waiting_start_text = State()
    waiting_success_text = State()

# ========== Инициализация дефолтной админ-панели ==========
cursor.execute("SELECT COUNT(*) FROM admin_sections")
if cursor.fetchone()[0] == 0:
    # Создаем разделы
    sections = [
        ("Reply кнопки", 1),
        ("Инлайн кнопки", 2),
        ("Тексты", 3)
    ]
    for name, order in sections:
        cursor.execute("INSERT INTO admin_sections (name, sort_order) VALUES (?, ?)", (name, order))
    conn.commit()
    
    # Получаем ID разделов
    cursor.execute("SELECT id, name FROM admin_sections ORDER BY sort_order")
    sections_map = {name: id for id, name in cursor.fetchall()}
    
    # Пункты для Reply кнопки
    reply_items = [
        ("Добавить", "reply_add", "", 1),
        ("Удалить", "reply_delete", "", 2),
        ("Изменить название", "reply_rename", "", 3),
        ("Изменить текст", "reply_edit", "", 4)
    ]
    for name, action_type, action_target, order in reply_items:
        cursor.execute("INSERT INTO admin_items (section_id, name, action_type, action_target, sort_order) VALUES (?, ?, ?, ?, ?)",
                       (sections_map["Reply кнопки"], name, action_type, action_target, order))
    
    # Пункты для Инлайн кнопки
    inline_items = [
        ("Добавить", "inline_add", "", 1),
        ("Удалить", "inline_delete", "", 2),
        ("Изменить название", "inline_rename", "", 3),
        ("Изменить ссылку", "inline_edit", "", 4)
    ]
    for name, action_type, action_target, order in inline_items:
        cursor.execute("INSERT INTO admin_items (section_id, name, action_type, action_target, sort_order) VALUES (?, ?, ?, ?, ?)",
                       (sections_map["Инлайн кнопки"], name, action_type, action_target, order))
    
    # Пункты для Тексты
    text_items = [
        ("Приветствие", "text_start", "", 1),
        ("Успех", "text_success", "", 2)
    ]
    for name, action_type, action_target, order in text_items:
        cursor.execute("INSERT INTO admin_items (section_id, name, action_type, action_target, sort_order) VALUES (?, ?, ?, ?, ?)",
                       (sections_map["Тексты"], name, action_type, action_target, order))
    
    conn.commit()

# ========== Основные команды ==========
@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute("SELECT value FROM settings WHERE key='start_text'")
    start_text = cursor.fetchone()
    if not start_text:
        start_text = ("Добро пожаловать! Подпишитесь на каналы:",)
        cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("start_text", start_text[0]))
        conn.commit()
    else:
        start_text = start_text[0]
    await message.answer(start_text[0] if isinstance(start_text, tuple) else start_text, parse_mode="HTML", reply_markup=get_subs_keyboard())

@dp.callback_query(lambda call: call.data == "check_subs")
async def check_subs(call: types.CallbackQuery):
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    success_text = cursor.fetchone()
    if not success_text:
        success_text = ("Успешная регистрация",)
        cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("success_text", success_text[0]))
        conn.commit()
    else:
        success_text = success_text[0]
    await call.message.delete()
    await call.message.answer(success_text[0] if isinstance(success_text, tuple) else success_text, parse_mode="HTML", reply_markup=get_menu_keyboard())
    await call.answer()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    await message.answer("Админ-панель", reply_markup=get_dynamic_admin_keyboard())

# ========== Обработка динамической админ-панели ==========
@dp.message(lambda message: message.text == "Выйти")
async def exit_admin(message: types.Message):
    await message.answer("Выход", reply_markup=types.ReplyKeyboardRemove())

@dp.message(lambda message: message.text == "Настройка админки")
async def admin_settings(message: types.Message):
    await message.answer("Настройка админ-панели", reply_markup=get_admin_settings_keyboard())

@dp.message(lambda message: message.text == "Назад")
async def back_to_admin(message: types.Message):
    await message.answer("Назад", reply_markup=get_dynamic_admin_keyboard())

# ---------- Управление разделами ----------
@dp.message(lambda message: message.text == "Добавить раздел")
async def add_section_start(message: types.Message, state: FSMContext):
    await message.answer("Название раздела:")
    await state.set_state(AdminStates.waiting_new_section)

@dp.message(AdminStates.waiting_new_section)
async def add_section_save(message: types.Message, state: FSMContext):
    name = message.text
    cursor.execute("SELECT COUNT(*) FROM admin_sections")
    count = cursor.fetchone()[0]
    cursor.execute("INSERT INTO admin_sections (name, sort_order) VALUES (?, ?)", (name, count + 1))
    conn.commit()
    await message.answer(f"Раздел '{name}' добавлен", reply_markup=get_admin_settings_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Удалить раздел")
async def delete_section_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name FROM admin_sections")
    sections = cursor.fetchall()
    if not sections:
        await message.answer("Нет разделов")
        return
    text = "Разделы:\n"
    for id, name in sections:
        text += f"{id}. {name}\n"
    text += "\nВведите ID для удаления:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_delete_section)

@dp.message(AdminStates.waiting_delete_section)
async def delete_section_save(message: types.Message, state: FSMContext):
    try:
        section_id = int(message.text)
        cursor.execute("DELETE FROM admin_items WHERE section_id=?", (section_id,))
        cursor.execute("DELETE FROM admin_sections WHERE id=?", (section_id,))
        conn.commit()
        await message.answer("Раздел удален", reply_markup=get_admin_settings_keyboard())
    except ValueError:
        await message.answer("Ошибка")
    await state.clear()

@dp.message(lambda message: message.text == "Переименовать раздел")
async def rename_section_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name FROM admin_sections")
    sections = cursor.fetchall()
    if not sections:
        await message.answer("Нет разделов")
        return
    text = "Разделы:\n"
    for id, name in sections:
        text += f"{id}. {name}\n"
    text += "\nВведите ID для переименования:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_rename_section_old)

@dp.message(AdminStates.waiting_rename_section_old)
async def rename_section_select(message: types.Message, state: FSMContext):
    try:
        section_id = int(message.text)
        cursor.execute("SELECT name FROM admin_sections WHERE id=?", (section_id,))
        row = cursor.fetchone()
        if row:
            await state.update_data(section_id=section_id)
            await message.answer("Новое название:")
            await state.set_state(AdminStates.waiting_rename_section_new)
        else:
            await message.answer("Не найден")
    except ValueError:
        await message.answer("Ошибка")

@dp.message(AdminStates.waiting_rename_section_new)
async def rename_section_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    section_id = data["section_id"]
    new_name = message.text
    cursor.execute("UPDATE admin_sections SET name=? WHERE id=?", (new_name, section_id))
    conn.commit()
    await message.answer("Переименовано", reply_markup=get_admin_settings_keyboard())
    await state.clear()

# ---------- Управление пунктами ----------
@dp.message(lambda message: message.text == "Добавить пункт")
async def add_item_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name FROM admin_sections")
    sections = cursor.fetchall()
    if not sections:
        await message.answer("Нет разделов")
        return
    text = "Разделы:\n"
    for id, name in sections:
        text += f"{id}. {name}\n"
    text += "\nВведите ID раздела:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_new_item_section)

@dp.message(AdminStates.waiting_new_item_section)
async def add_item_section(message: types.Message, state: FSMContext):
    try:
        section_id = int(message.text)
        cursor.execute("SELECT name FROM admin_sections WHERE id=?", (section_id,))
        if cursor.fetchone():
            await state.update_data(section_id=section_id)
            await message.answer("Название пункта:")
            await state.set_state(AdminStates.waiting_new_item_name)
        else:
            await message.answer("Не найден")
    except ValueError:
        await message.answer("Ошибка")

@dp.message(AdminStates.waiting_new_item_name)
async def add_item_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    section_id = data["section_id"]
    name = message.text
    cursor.execute("SELECT COUNT(*) FROM admin_items WHERE section_id=?", (section_id,))
    count = cursor.fetchone()[0]
    cursor.execute("INSERT INTO admin_items (section_id, name, action_type, action_target, sort_order) VALUES (?, ?, ?, ?, ?)",
                   (section_id, name, "custom", "", count + 1))
    conn.commit()
    await message.answer(f"Пункт '{name}' добавлен", reply_markup=get_admin_settings_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Удалить пункт")
async def delete_item_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name FROM admin_items")
    items = cursor.fetchall()
    if not items:
        await message.answer("Нет пунктов")
        return
    text = "Пункты:\n"
    for id, name in items:
        text += f"{id}. {name}\n"
    text += "\nВведите ID для удаления:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_delete_item)

@dp.message(AdminStates.waiting_delete_item)
async def delete_item_save(message: types.Message, state: FSMContext):
    try:
        item_id = int(message.text)
        cursor.execute("DELETE FROM admin_items WHERE id=?", (item_id,))
        conn.commit()
        await message.answer("Пункт удален", reply_markup=get_admin_settings_keyboard())
    except ValueError:
        await message.answer("Ошибка")
    await state.clear()

@dp.message(lambda message: message.text == "Переименовать пункт")
async def rename_item_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name FROM admin_items")
    items = cursor.fetchall()
    if not items:
        await message.answer("Нет пунктов")
        return
    text = "Пункты:\n"
    for id, name in items:
        text += f"{id}. {name}\n"
    text += "\nВведите ID для переименования:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_rename_item_select)

@dp.message(AdminStates.waiting_rename_item_select)
async def rename_item_select(message: types.Message, state: FSMContext):
    try:
        item_id = int(message.text)
        cursor.execute("SELECT name FROM admin_items WHERE id=?", (item_id,))
        if cursor.fetchone():
            await state.update_data(item_id=item_id)
            await message.answer("Новое название:")
            await state.set_state(AdminStates.waiting_rename_item_new)
        else:
            await message.answer("Не найден")
    except ValueError:
        await message.answer("Ошибка")

@dp.message(AdminStates.waiting_rename_item_new)
async def rename_item_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data["item_id"]
    new_name = message.text
    cursor.execute("UPDATE admin_items SET name=? WHERE id=?", (new_name, item_id))
    conn.commit()
    await message.answer("Переименовано", reply_markup=get_admin_settings_keyboard())
    await state.clear()

# ========== Обработка нажатий на разделы ==========
@dp.message(lambda message: True)
async def handle_admin_sections(message: types.Message):
    # Проверяем, есть ли такой раздел
    cursor.execute("SELECT id FROM admin_sections WHERE name=?", (message.text,))
    section = cursor.fetchone()
    if section:
        section_id = section[0]
        await message.answer(message.text, reply_markup=get_section_items_keyboard(section_id))
        return
    
    # Проверяем, есть ли такой пункт в текущем контексте
    cursor.execute("SELECT action_type, action_target FROM admin_items WHERE name=?", (message.text,))
    item = cursor.fetchone()
    if item:
        action_type, action_target = item
        await handle_admin_action(message, action_type)
        return
    
    # Обработка кнопок меню пользователя
    cursor.execute("SELECT content FROM menu_buttons WHERE name=?", (message.text,))
    row = cursor.fetchone()
    if row:
        await message.answer(row[0], parse_mode="HTML")

async def handle_admin_action(message: types.Message, action_type: str):
    if action_type == "reply_add":
        await add_reply_start(message, AdminStates())
    elif action_type == "reply_delete":
        await delete_reply_start(message, AdminStates())
    elif action_type == "reply_rename":
        await edit_reply_name_start(message, AdminStates())
    elif action_type == "reply_edit":
        await edit_reply_content_start(message, AdminStates())
    elif action_type == "inline_add":
        await add_inline_start(message, AdminStates())
    elif action_type == "inline_delete":
        await delete_inline_start(message, AdminStates())
    elif action_type == "inline_rename":
        await edit_inline_name_start(message, AdminStates())
    elif action_type == "inline_edit":
        await edit_inline_url_start(message, AdminStates())
    elif action_type == "text_start":
        await edit_start_text_start(message, AdminStates())
    elif action_type == "text_success":
        await edit_success_text_start(message, AdminStates())
    else:
        await message.answer("Действие не настроено")

# ========== Reply кнопки ==========
async def add_reply_start(message: types.Message, state: FSMContext):
    await message.answer("Название:")
    await state.set_state(AdminStates.waiting_reply_name)

@dp.message(AdminStates.waiting_reply_name)
async def add_reply_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Текст:")
    await state.set_state(AdminStates.waiting_reply_content)

@dp.message(AdminStates.waiting_reply_content)
async def add_reply_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    content = message.html_text
    cursor.execute("INSERT INTO menu_buttons (name, content) VALUES (?, ?)", (name, content))
    conn.commit()
    await message.answer(f"Добавлено: {name}")
    await state.clear()

async def delete_reply_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=row[0])] for row in buttons] + [[KeyboardButton(text="Назад")]],
        resize_keyboard=True
    )
    await message.answer("Выберите:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_reply_delete)

@dp.message(AdminStates.waiting_reply_delete)
async def delete_reply(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.answer("Назад")
        await state.clear()
        return
    cursor.execute("DELETE FROM menu_buttons WHERE name=?", (message.text,))
    conn.commit()
    await message.answer(f"Удалено: {message.text}")
    await state.clear()

async def edit_reply_name_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=row[0])] for row in buttons] + [[KeyboardButton(text="Назад")]],
        resize_keyboard=True
    )
    await message.answer("Выберите:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_reply_edit_name_old)

@dp.message(AdminStates.waiting_reply_edit_name_old)
async def edit_reply_name_old(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.answer("Назад")
        await state.clear()
        return
    await state.update_data(old_name=message.text)
    await message.answer("Новое название:")
    await state.set_state(AdminStates.waiting_reply_edit_name_new)

@dp.message(AdminStates.waiting_reply_edit_name_new)
async def edit_reply_name_new(message: types.Message, state: FSMContext):
    data = await state.get_data()
    old_name = data["old_name"]
    new_name = message.text
    cursor.execute("UPDATE menu_buttons SET name=? WHERE name=?", (new_name, old_name))
    conn.commit()
    await message.answer(f"Переименовано: {old_name} -> {new_name}")
    await state.clear()

async def edit_reply_content_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=row[0])] for row in buttons] + [[KeyboardButton(text="Назад")]],
        resize_keyboard=True
    )
    await message.answer("Выберите:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_reply_edit_content)

@dp.message(AdminStates.waiting_reply_edit_content)
async def edit_reply_content(message: types.Message, state: FSMContext):
    if message.text == "Назад":
        await message.answer("Назад")
        await state.clear()
        return
    await state.update_data(edit_name=message.text)
    await message.answer("Новый текст:")
    await state.set_state(AdminStates.waiting_reply_edit_content)

@dp.message(AdminStates.waiting_reply_edit_content)
async def edit_reply_content_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["edit_name"]
    content = message.html_text
    cursor.execute("UPDATE menu_buttons SET content=? WHERE name=?", (content, name))
    conn.commit()
    await message.answer(f"Изменено: {name}")
    await state.clear()

# ========== Инлайн кнопки ==========
async def add_inline_start(message: types.Message, state: FSMContext):
    await message.answer("Название:")
    await state.set_state(AdminStates.waiting_subs_name)

@dp.message(AdminStates.waiting_subs_name)
async def add_inline_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Ссылка (@username или полная):")
    await state.set_state(AdminStates.waiting_subs_url)

@dp.message(AdminStates.waiting_subs_url)
async def add_inline_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    url = normalize_url(message.text)
    cursor.execute("INSERT INTO subs_buttons (name, url) VALUES (?, ?)", (name, url))
    conn.commit()
    await message.answer(f"Добавлено: {name}")
    await state.clear()

async def delete_inline_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name FROM subs_buttons ORDER BY id")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок")
        return
    text = "Список:\n"
    for id, name in buttons:
        text += f"{id}. {name}\n"
    text += "\nID для удаления:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_subs_delete_id)

@dp.message(AdminStates.waiting_subs_delete_id)
async def delete_inline(message: types.Message, state: FSMContext):
    try:
        btn_id = int(message.text)
        cursor.execute("DELETE FROM subs_buttons WHERE id=?", (btn_id,))
        conn.commit()
        await message.answer("Удалено")
    except ValueError:
        await message.answer("Ошибка")
    await state.clear()

async def edit_inline_name_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name FROM subs_buttons ORDER BY id")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок")
        return
    text = "Список:\n"
    for id, name in buttons:
        text += f"{id}. {name}\n"
    text += "\nID для изменения:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_subs_edit_id)

@dp.message(AdminStates.waiting_subs_edit_id)
async def edit_inline_name_select(message: types.Message, state: FSMContext):
    try:
        btn_id = int(message.text)
        cursor.execute("SELECT name FROM subs_buttons WHERE id=?", (btn_id,))
        row = cursor.fetchone()
        if row:
            await state.update_data(edit_id=btn_id)
            await message.answer("Новое название:")
            await state.set_state(AdminStates.waiting_subs_edit_name)
        else:
            await message.answer("Не найден")
    except ValueError:
        await message.answer("Ошибка")

@dp.message(AdminStates.waiting_subs_edit_name)
async def edit_inline_name_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["edit_id"]
    new_name = message.text
    cursor.execute("UPDATE subs_buttons SET name=? WHERE id=?", (new_name, btn_id))
    conn.commit()
    await message.answer("Изменено")
    await state.clear()

async def edit_inline_url_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name, url FROM subs_buttons ORDER BY id")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок")
        return
    text = "Список:\n"
    for id, name, url in buttons:
        text += f"{id}. {name} -> {url}\n"
    text += "\nID для изменения:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_subs_edit_url)

@dp.message(AdminStates.waiting_subs_edit_url)
async def edit_inline_url_select(message: types.Message, state: FSMContext):
    try:
        btn_id = int(message.text)
        cursor.execute("SELECT name FROM subs_buttons WHERE id=?", (btn_id,))
        row = cursor.fetchone()
        if row:
            await state.update_data(edit_id=btn_id)
            await message.answer("Новая ссылка (@username или полная):")
            await state.set_state(AdminStates.waiting_subs_edit_url)
        else:
            await message.answer("Не найден")
    except ValueError:
        await message.answer("Ошибка")

@dp.message(AdminStates.waiting_subs_edit_url)
async def edit_inline_url_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["edit_id"]
    new_url = normalize_url(message.text)
    cursor.execute("UPDATE subs_buttons SET url=? WHERE id=?", (new_url, btn_id))
    conn.commit()
    await message.answer("Изменено")
    await state.clear()

# ========== Тексты ==========
async def edit_start_text_start(message: types.Message, state: FSMContext):
    await message.answer("Новый текст:")
    await state.set_state(AdminStates.waiting_start_text)

@dp.message(AdminStates.waiting_start_text)
async def edit_start_text_save(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='start_text'", (message.html_text,))
    conn.commit()
    await message.answer("Сохранено")
    await state.clear()

async def edit_success_text_start(message: types.Message, state: FSMContext):
    await message.answer("Новый текст:")
    await state.set_state(AdminStates.waiting_success_text)

@dp.message(AdminStates.waiting_success_text)
async def edit_success_text_save(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='success_text'", (message.html_text,))
    conn.commit()
    await message.answer("Сохранено")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
