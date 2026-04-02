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
CREATE TABLE IF NOT EXISTS subs_links (
    id INTEGER PRIMARY KEY,
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

# Добавляем дефолтные кнопки если пусто
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

# Дефолтные ссылки подписок
for i in range(1, 6):
    cursor.execute("INSERT OR IGNORE INTO subs_links (id, url) VALUES (?, ?)", (i, f"https://t.me/example{i}"))
conn.commit()

# Дефолтный текст start
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("start_text", "Добро пожаловать! Подпишитесь на каналы:"))
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("success_text", "Успешная регистрация"))
conn.commit()

def get_menu_keyboard():
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = [KeyboardButton(text=row[0]) for row in cursor.fetchall()]
    # Разбиваем по 2 кнопки в ряд
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_subs_keyboard():
    cursor.execute("SELECT id, url FROM subs_links ORDER BY id")
    rows = cursor.fetchall()
    buttons = []
    for id, url in rows:
        buttons.append([InlineKeyboardButton(text=f"Канал {id}", url=url)])
    buttons.append([InlineKeyboardButton(text="✅ Проверить подписки", callback_data="check_subs")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить кнопку")],
            [KeyboardButton(text="Удалить кнопку")],
            [KeyboardButton(text="Изменить текст кнопки")],
            [KeyboardButton(text="Изменить ссылки подписок")],
            [KeyboardButton(text="Изменить текст /start")],
            [KeyboardButton(text="Изменить текст успеха")],
            [KeyboardButton(text="Выйти из админки")]
        ],
        resize_keyboard=True
    )
    return keyboard

class AdminStates(StatesGroup):
    waiting_button_name = State()
    waiting_button_content = State()
    waiting_delete_name = State()
    waiting_edit_name = State()
    waiting_edit_content = State()
    waiting_subs_link_id = State()
    waiting_subs_link_url = State()
    waiting_start_text = State()
    waiting_success_text = State()

@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute("SELECT value FROM settings WHERE key='start_text'")
    start_text = cursor.fetchone()[0]
    await message.answer(start_text, reply_markup=get_subs_keyboard())

@dp.callback_query(lambda call: call.data == "check_subs")
async def check_subs(call: types.CallbackQuery):
    # Заглушка проверки - всегда успешно
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    success_text = cursor.fetchone()[0]
    await call.message.delete()
    await call.message.answer(success_text, reply_markup=get_menu_keyboard())
    await call.answer()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    await message.answer("Админ-панель. Выберите действие:", reply_markup=get_admin_keyboard())

@dp.message(lambda message: message.text == "Выйти из админки")
async def exit_admin(message: types.Message):
    await message.answer("Вы вышли из админ-панели.", reply_markup=types.ReplyKeyboardRemove())

@dp.message(lambda message: message.text == "Добавить кнопку")
async def add_button_start(message: types.Message, state: FSMContext):
    await message.answer("Введите название новой кнопки:")
    await state.set_state(AdminStates.waiting_button_name)

@dp.message(AdminStates.waiting_button_name)
async def add_button_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите текст/контент для этой кнопки:")
    await state.set_state(AdminStates.waiting_button_content)

@dp.message(AdminStates.waiting_button_content)
async def add_button_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    content = message.text
    try:
        cursor.execute("INSERT INTO menu_buttons (name, content) VALUES (?, ?)", (name, content))
        conn.commit()
        await message.answer(f"Кнопка '{name}' добавлена!")
    except sqlite3.IntegrityError:
        await message.answer(f"Кнопка с именем '{name}' уже существует!")
    await state.clear()

@dp.message(lambda message: message.text == "Удалить кнопку")
async def delete_button_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок для удаления.")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=row[0])] for row in buttons] + [[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите кнопку для удаления:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_delete_name)

@dp.message(AdminStates.waiting_delete_name)
async def delete_button(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await message.answer("Отменено.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    cursor.execute("DELETE FROM menu_buttons WHERE name=?", (message.text,))
    conn.commit()
    await message.answer(f"Кнопка '{message.text}' удалена!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Изменить текст кнопки")
async def edit_button_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM menu_buttons")
    buttons = cursor.fetchall()
    if not buttons:
        await message.answer("Нет кнопок для изменения.")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=row[0])] for row in buttons] + [[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите кнопку для изменения:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_edit_name)

@dp.message(AdminStates.waiting_edit_name)
async def edit_button_select(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await message.answer("Отменено.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    await state.update_data(edit_name=message.text)
    await message.answer("Введите новый текст для этой кнопки:")
    await state.set_state(AdminStates.waiting_edit_content)

@dp.message(AdminStates.waiting_edit_content)
async def edit_button_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data["edit_name"]
    content = message.text
    cursor.execute("UPDATE menu_buttons SET content=? WHERE name=?", (content, name))
    conn.commit()
    await message.answer(f"Текст кнопки '{name}' обновлен!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Изменить ссылки подписок")
async def edit_subs_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, url FROM subs_links ORDER BY id")
    links = cursor.fetchall()
    text = "Текущие ссылки:\n"
    for id, url in links:
        text += f"{id}. {url}\n"
    text += "\nВведите номер ссылки (1-5):"
    await message.answer(text)
    await state.set_state(AdminStates.waiting_subs_link_id)

@dp.message(AdminStates.waiting_subs_link_id)
async def edit_subs_id(message: types.Message, state: FSMContext):
    try:
        link_id = int(message.text)
        if 1 <= link_id <= 5:
            await state.update_data(link_id=link_id)
            await message.answer("Введите новую ссылку:")
            await state.set_state(AdminStates.waiting_subs_link_url)
        else:
            await message.answer("Введите число от 1 до 5")
    except ValueError:
        await message.answer("Введите число")

@dp.message(AdminStates.waiting_subs_link_url)
async def edit_subs_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    link_id = data["link_id"]
    url = message.text
    cursor.execute("UPDATE subs_links SET url=? WHERE id=?", (url, link_id))
    conn.commit()
    await message.answer(f"Ссылка {link_id} обновлена!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Изменить текст /start")
async def edit_start_text_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='start_text'")
    current = cursor.fetchone()[0]
    await message.answer(f"Текущий текст:\n{current}\n\nВведите новый текст для /start:")
    await state.set_state(AdminStates.waiting_start_text)

@dp.message(AdminStates.waiting_start_text)
async def edit_start_text_save(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='start_text'", (message.text,))
    conn.commit()
    await message.answer("Текст /start обновлен!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Изменить текст успеха")
async def edit_success_text_start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    current = cursor.fetchone()[0]
    await message.answer(f"Текущий текст:\n{current}\n\nВведите новый текст для 'Успешная регистрация':")
    await state.set_state(AdminStates.waiting_success_text)

@dp.message(AdminStates.waiting_success_text)
async def edit_success_text_save(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='success_text'", (message.text,))
    conn.commit()
    await message.answer("Текст успеха обновлен!", reply_markup=get_admin_keyboard())
    await state.clear()

# Обработка нажатий на кнопки меню
@dp.message(lambda message: True)
async def handle_menu_buttons(message: types.Message):
    cursor.execute("SELECT content FROM menu_buttons WHERE name=?", (message.text,))
    row = cursor.fetchone()
    if row:
        await message.answer(row[0])
    # Игнорируем другие сообщения

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
