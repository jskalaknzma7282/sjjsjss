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

# База данных
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
conn.commit()

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
    conn.commit()

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
    conn.commit()

cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("start_text", "Добро пожаловать! Подпишитесь на каналы:"))
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("success_text", "Успешная регистрация"))
conn.commit()

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
    buttons.append([InlineKeyboardButton(text="✅ Проверить подписки", callback_data="check_subs")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard():
    admin_buttons = [
        "Добавить reply кнопку", "Удалить reply кнопку",
        "Изменить текст reply кнопки", "Добавить инлайн кнопку подписки",
        "Удалить инлайн кнопку подписки", "Изменить инлайн кнопку подписки",
        "Изменить текст /start", "Изменить текст успеха",
        "Выйти из админки"
    ]
    buttons = [[KeyboardButton(text=btn) for btn in admin_buttons[i:i+2]] for i in range(0, len(admin_buttons), 2)]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

class AdminStates(StatesGroup):
    waiting_reply_name = State()
    waiting_reply_content = State()
    waiting_reply_delete = State()
    waiting_reply_edit_name = State()
    waiting_reply_edit_content = State()
    waiting_subs_name = State()
    waiting_subs_url = State()
    waiting_subs_delete_id = State()
    waiting_subs_edit_id = State()
    waiting_subs_edit_name = State()
    waiting_subs_edit_url = State()
    waiting_start_text = State()
    waiting_success_text = State()

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
    await message.answer("Админ-панель. Выберите действие:", reply_markup=get_admin_keyboard())

@dp.message(lambda message: message.text == "Выйти из админки")
async def exit_admin(message: types.Message):
    await message.answer("Вы вышли из админ-панели.", reply_markup=types.ReplyKeyboardRemove())

# ========== Управление REPLY кнопками ==========
@dp.message(lambda message: message.text == "Добавить reply кнопку")
async def add_reply_start(message: types.Message, state: FSMContext):
    await message.answer("Введите название новой reply кнопки:")
    await state.set_state(AdminStates.waiting_reply_name)

@dp.message(AdminStates.waiting_reply_name)
async def add_reply_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите текст (можно с форматированием через меню Telegram):")
    await state.set_state(AdminStates.waiting_reply_content)

@dp.message(AdminStates.waiting_reply_content)
async def add_reply_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    content = message.html_text  # Сохраняем форматирование
    try:
        cursor.execute("INSERT INTO menu_buttons (name, content) VALUES (?, ?)", (name, content))
        conn.commit()
        await message.answer(f"Reply кнопка '{name}' добавлена!")
    except sqlite3.IntegrityError:
        await message.answer(f"Кнопка с именем '{name}' уже существует!")
    await state.clear()

@dp.message(lambda message: message.text == "Удалить reply кнопку")
async def delete_reply_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок для удаления.")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=row[0])] for row in buttons] + [[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите reply кнопку для удаления:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_reply_delete)

@dp.message(AdminStates.waiting_reply_delete)
async def delete_reply(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await message.answer("Отменено.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    cursor.execute("DELETE FROM menu_buttons WHERE name=?", (message.text,))
    conn.commit()
    await message.answer(f"Reply кнопка '{message.text}' удалена!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Изменить текст reply кнопки")
async def edit_reply_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок для изменения.")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=row[0])] for row in buttons] + [[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите reply кнопку для изменения:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_reply_edit_name)

@dp.message(AdminStates.waiting_reply_edit_name)
async def edit_reply_select(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await message.answer("Отменено.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    await state.update_data(edit_name=message.text)
    await message.answer("Введите новый текст (можно с форматированием через меню Telegram):")
    await state.set_state(AdminStates.waiting_reply_edit_content)

@dp.message(AdminStates.waiting_reply_edit_content)
async def edit_reply_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["edit_name"]
    content = message.html_text  # Сохраняем форматирование
    cursor.execute("UPDATE menu_buttons SET content=? WHERE name=?", (content, name))
    conn.commit()
    await message.answer(f"Текст reply кнопки '{name}' обновлен!", reply_markup=get_admin_keyboard())
    await state.clear()

# ========== Управление INLINE кнопками подписок ==========
@dp.message(lambda message: message.text == "Добавить инлайн кнопку подписки")
async def add_subs_start(message: types.Message, state: FSMContext):
    await message.answer("Введите название инлайн кнопки (например: Канал 1):")
    await state.set_state(AdminStates.waiting_subs_name)

@dp.message(AdminStates.waiting_subs_name)
async def add_subs_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите ссылку на канал/чат/бота:")
    await state.set_state(AdminStates.waiting_subs_url)

@dp.message(AdminStates.waiting_subs_url)
async def add_subs_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    url = message.text
    cursor.execute("INSERT INTO subs_buttons (name, url) VALUES (?, ?)", (name, url))
    conn.commit()
    await message.answer(f"Инлайн кнопка '{name}' добавлена!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Удалить инлайн кнопку подписки")
async def delete_subs_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name FROM subs_buttons ORDER BY id")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок для удаления.")
        return
    text = "Список инлайн кнопок:\n"
    for id, name in buttons:
        text += f"{id}. {name}\n"
    text += "\nВведите ID кнопки для удаления:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_subs_delete_id)

@dp.message(AdminStates.waiting_subs_delete_id)
async def delete_subs(message: types.Message, state: FSMContext):
    try:
        btn_id = int(message.text)
        cursor.execute("DELETE FROM subs_buttons WHERE id=?", (btn_id,))
        conn.commit()
        await message.answer(f"Инлайн кнопка с ID {btn_id} удалена!", reply_markup=get_admin_keyboard())
    except ValueError:
        await message.answer("Введите число (ID кнопки)")
    await state.clear()

@dp.message(lambda message: message.text == "Изменить инлайн кнопку подписки")
async def edit_subs_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, name, url FROM subs_buttons ORDER BY id")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок для изменения.")
        return
    text = "Список инлайн кнопок:\n"
    for id, name, url in buttons:
        text += f"{id}. {name} -> {url}\n"
    text += "\nВведите ID кнопки для изменения:"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_subs_edit_id)

@dp.message(AdminStates.waiting_subs_edit_id)
async def edit_subs_select(message: types.Message, state: FSMContext):
    try:
        btn_id = int(message.text)
        cursor.execute("SELECT name FROM subs_buttons WHERE id=?", (btn_id,))
        row = cursor.fetchone()
        if row:
            await state.update_data(edit_id=btn_id)
            await message.answer(f"Редактируем '{row[0]}'. Введите новое название:")
            await state.set_state(AdminStates.waiting_subs_edit_name)
        else:
            await message.answer("ID не найден")
    except ValueError:
        await message.answer("Введите число")

@dp.message(AdminStates.waiting_subs_edit_name)
async def edit_subs_new_name(message: types.Message, state: FSMContext):
    await state.update_data(edit_name=message.text)
    await message.answer("Введите новую ссылку:")
    await state.set_state(AdminStates.waiting_subs_edit_url)

@dp.message(AdminStates.waiting_subs_edit_url)
async def edit_subs_new_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["edit_id"]
    new_name = data["edit_name"]
    new_url = message.text
    cursor.execute("UPDATE subs_buttons SET name=?, url=? WHERE id=?", (new_name, new_url, btn_id))
    conn.commit()
    await message.answer(f"Инлайн кнопка обновлена!", reply_markup=get_admin_keyboard())
    await state.clear()

# ========== Управление текстами ==========
@dp.message(lambda message: message.text == "Изменить текст /start")
async def edit_start_text_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='start_text'")
    current = cursor.fetchone()[0]
    await message.answer(f"Текущий текст:\n{current}\n\nВведите новый текст (можно с форматированием через меню Telegram):")
    await state.set_state(AdminStates.waiting_start_text)

@dp.message(AdminStates.waiting_start_text)
async def edit_start_text_save(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='start_text'", (message.html_text,))  # Сохраняем форматирование
    conn.commit()
    await message.answer("Текст /start обновлен!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Изменить текст успеха")
async def edit_success_text_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    current = cursor.fetchone()[0]
    await message.answer(f"Текущий текст:\n{current}\n\nВведите новый текст (можно с форматированием через меню Telegram):")
    await state.set_state(AdminStates.waiting_success_text)

@dp.message(AdminStates.waiting_success_text)
async def edit_success_text_save(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='success_text'", (message.html_text,))  # Сохраняем форматирование
    conn.commit()
    await message.answer("Текст успеха обновлен!", reply_markup=get_admin_keyboard())
    await state.clear()

# Обработка нажатий на reply кнопки меню (с HTML-форматированием)
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
