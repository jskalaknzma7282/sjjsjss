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
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("start_text", "<blockquote>👋 Добро пожаловать в Krot Free\n\n🌟Мы предоставляем вам бесплатную информацию, которую вы нигде больше не найдете.\n\n🤖Проект полностью бесплатен, мы просим вас подписаться на наших спонсоров, после чего вы получите полный доступ к меню и всей информации!</blockquote>"))
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("success_text", "<blockquote><b>✅ ДОСТУП ОТКРЫТ</b>\n\nРегистрация прошла успешно!\n\n🐭 Krot Free полностью разблокирован и готов к работе, вам доступны все мануалы.\n\n👇 Что делать дальше?\n• Вам открылось меню, в котором вы можете выбрать интересную для себя сферу\n• Переходите на любую из кнопок на клавиатуре и начинайте изучать.</blockquote>"))
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("error_text", "<blockquote><b>❌ Ошибка</b>\n<i>• Вы не подписались на все каналы</i>\n<i>• Подпишитесь и нажмите \"Проверить\" снова</i></blockquote>"))
    
    system_defaults = {
        "Название:": "<blockquote><b>📝 Введите новое название</b>\n<i>• Название будет отображаться на кнопке</i>\n<i>• Можно использовать эмодзи для красоты</i>\n<i>• Максимум 50 символов</i></blockquote>",
        "Ссылка:": "<blockquote><b>🔗 Введите ссылку</b>\n<i>• Можно указать @username</i>\n<i>• Можно полную ссылку https://t.me/...</i>\n<i>• Ссылка должна быть на канал/чат/бота</i></blockquote>",
        "Новое название:": "<blockquote><b>✏️ Введите новое название</b>\n<i>• Старое название будет заменено</i>\n<i>• Название должно быть уникальным</i></blockquote>",
        "Новая ссылка:": "<blockquote><b>🔗 Введите новую ссылку</b>\n<i>• Старая ссылка будет заменена</i>\n<i>• Формат: @username или полная ссылка</i></blockquote>",
        "Добавлено: {name}": "<blockquote><b>✅ Добавлено:</b> {name}\n<i>• Новая кнопка появилась в меню</i>\n<i>• Вы можете отредактировать её позже</i></blockquote>",
        "Удалено: {name}": "<blockquote><b>❌ Удалено:</b> {name}\n<i>• Кнопка удалена из меню</i>\n<i>• Данные восстановить нельзя</i></blockquote>",
        "Изменено: {name}": "<blockquote><b>✏️ Изменено:</b> {name}\n<i>• Обновленные данные сохранены</i>\n<i>• Изменения вступят в силу сразу</i></blockquote>",
        "Нет кнопок": "<blockquote><b>📭 Нет кнопок</b>\n<i>• Добавьте кнопку через меню</i>\n<i>• Нажмите \"➕ Добавить\"</i>\n<i>• Введите название и текст/ссылку</i></blockquote>",
        "Ошибка": "<blockquote><b>⚠️ Ошибка</b>\n<i>• Проверьте введенные данные</i>\n<i>• Убедитесь, что ID существует</i>\n<i>• Попробуйте еще раз</i></blockquote>",
        "Выберите:": "<blockquote><b>🔢 Выберите ID кнопки</b>\n<i>• Введите номер из списка ниже</i>\n<i>• Только цифры</i></blockquote>",
        "Введите ID:": "<blockquote><b>🔢 Введите ID</b>\n<i>• Напишите только цифру</i>\n<i>• Пример: 1, 2, 3...</i></blockquote>"
    }
    for key, value in system_defaults.items():
        cursor.execute("INSERT OR IGNORE INTO system_messages (key, value) VALUES (?, ?)", (key, value))
    
    for i in range(1, 6):
        cursor.execute("INSERT OR IGNORE INTO menu_buttons (name, content) VALUES (?, ?)", (str(i), f"<blockquote>📄 Текст для кнопки {i}</blockquote>"))
    
    for i in range(1, 6):
        cursor.execute("INSERT OR IGNORE INTO subs_buttons (name, url) VALUES (?, ?)", (f"📢 Канал {i}", f"https://t.me/example{i}"))
    
    conn.commit()

init_defaults()

def get_system_message(key: str) -> str:
    cursor.execute("SELECT value FROM system_messages WHERE key=?", (key,))
    row = cursor.fetchone()
    return row[0] if row else key

def get_menu_keyboard():
    cursor.execute("SELECT name FROM menu_buttons ORDER BY id")
    buttons = [KeyboardButton(text=row[0]) for row in cursor.fetchall()]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_subs_keyboard():
    cursor.execute("SELECT id, name, url FROM subs_buttons ORDER BY id")
    rows = cursor.fetchall()
    buttons = []
    row = []
    for id, name, url in rows:
        row.append(InlineKeyboardButton(text=name, url=url))
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
        [InlineKeyboardButton(text="📝 Тексты", callback_data="admin_texts"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton(text="🚪 Выйти", callback_data="admin_exit")]
    ])

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
    keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data="reply_add"), InlineKeyboardButton(text="➖ Удалить", callback_data="reply_delete")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
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

def get_system_keyboard():
    system_keys = [
        "Название:", "Ссылка:",
        "Новое название:", "Новая ссылка:",
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
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin")])
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛟 Поддержка", url="https://t.me/KrotProb")]
    ])
    
    await call.message.delete()
    await call.message.answer(success_text, parse_mode="HTML", reply_markup=keyboard)
    await call.message.answer("<b>📋 Меню открыто</b>\n<i>• Выберите интересующий раздел</i>", parse_mode="HTML", reply_markup=get_menu_keyboard())
    await call.answer()

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    await message.answer("<b>🔐 Админ панель открыта</b>\n<i>• Выберите действие</i>", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.callback_query(lambda call: call.data == "admin_reply")
async def admin_reply(call: types.CallbackQuery):
    await call.message.edit_text("<b>📋 Управление reply кнопками</b>\n<i>• Выберите кнопку для редактирования</i>\n<i>• Нажмите на кнопку для изменения</i>", parse_mode="HTML", reply_markup=get_reply_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_inline")
async def admin_inline(call: types.CallbackQuery):
    await call.message.edit_text("<b>🔗 Управление инлайн кнопками</b>\n<i>• Выберите кнопку для редактирования</i>\n<i>• Нажмите на кнопку для изменения</i>", parse_mode="HTML", reply_markup=get_inline_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_texts")
async def admin_texts(call: types.CallbackQuery):
    await call.message.edit_text("<b>📝 Редактирование текстов</b>\n<i>• Выберите текст для изменения</i>\n<i>• Можно использовать HTML-теги</i>", parse_mode="HTML", reply_markup=get_texts_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_settings")
async def admin_settings(call: types.CallbackQuery):
    await call.message.edit_text("<b>⚙️ Системные настройки</b>\n<i>• Выберите сообщение для редактирования</i>\n<i>• Изменения вступят в силу сразу</i>", parse_mode="HTML", reply_markup=get_system_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "admin_exit")
async def admin_exit(call: types.CallbackQuery):
    await call.message.delete()
    await call.answer()

# ========== Reply кнопки ==========
@dp.callback_query(lambda call: call.data.startswith("reply_edit_"))
async def reply_edit_select(call: types.CallbackQuery, state: FSMContext):
    btn_id = int(call.data.split("_")[2])
    cursor.execute("SELECT name, content FROM menu_buttons WHERE id=?", (btn_id,))
    name, content = cursor.fetchone()
    await state.update_data(waiting_reply_edit_id=btn_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data="reply_change_name"), InlineKeyboardButton(text="📝 Изменить текст", callback_data="reply_change_text")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_reply")]
    ])
    await call.message.edit_text(f"<b>📋 Редактирование кнопки</b>\n\n<b>• Текущее название:</b> <code>{name}</code>\n<b>• Текущий текст:</b> <code>{content}</code>\n\n<i>• Что хотите изменить?</i>\n<i>• Нажмите на соответствующую кнопку</i>", parse_mode="HTML", reply_markup=keyboard)
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
    await admin_reply(message)

@dp.message(EditStates.waiting_reply_edit_text)
async def reply_save_edit_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["waiting_reply_edit_id"]
    new_text = f"<blockquote>{message.html_text}</blockquote>"
    cursor.execute("UPDATE menu_buttons SET content=? WHERE id=?", (new_text, btn_id))
    conn.commit()
    await message.answer(get_system_message("Изменено: {name}").replace("{name}", "текст"), parse_mode="HTML")
    await state.clear()
    await admin_reply(message)

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
    text = f"<blockquote>{message.html_text}</blockquote>"
    cursor.execute("INSERT INTO menu_buttons (name, content) VALUES (?, ?)", (name, text))
    conn.commit()
    await message.answer(get_system_message("Добавлено: {name}").replace("{name}", name), parse_mode="HTML")
    await state.clear()
    await admin_reply(message)

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
    await admin_reply(message)

# ========== Инлайн кнопки ==========
@dp.callback_query(lambda call: call.data.startswith("inline_edit_"))
async def inline_edit_select(call: types.CallbackQuery, state: FSMContext):
    btn_id = int(call.data.split("_")[2])
    cursor.execute("SELECT name, url FROM subs_buttons WHERE id=?", (btn_id,))
    name, url = cursor.fetchone()
    await state.update_data(waiting_inline_edit_id=btn_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data="inline_change_name"), InlineKeyboardButton(text="🔗 Изменить ссылку", callback_data="inline_change_url")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_inline")]
    ])
    await call.message.edit_text(f"<b>🔗 Редактирование кнопки</b>\n\n<b>• Текущее название:</b> <code>{name}</code>\n<b>• Текущая ссылка:</b> <code>{url}</code>\n\n<i>• Что хотите изменить?</i>\n<i>• Нажмите на соответствующую кнопку</i>", parse_mode="HTML", reply_markup=keyboard)
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
    await admin_inline(message)

@dp.message(EditStates.waiting_inline_edit_url)
async def inline_save_edit_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    btn_id = data["waiting_inline_edit_id"]
    new_url = normalize_url(message.text)
    cursor.execute("UPDATE subs_buttons SET url=? WHERE id=?", (new_url, btn_id))
    conn.commit()
    await message.answer(get_system_message("Изменено: {name}").replace("{name}", "ссылка"), parse_mode="HTML")
    await state.clear()
    await admin_inline(message)

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
    await admin_inline(message)

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
    await admin_inline(message)

# ========== Тексты ==========
@dp.callback_query(lambda call: call.data == "text_start")
async def edit_start_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='start_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="start_text")
    await call.message.edit_text(f"<b>📝 Текущий текст приветствия</b>\n<code>{current}</code>\n\n<i>• Введите новый текст</i>\n<i>• Поддерживается HTML-форматирование</i>", parse_mode="HTML")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_success")
async def edit_success_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='success_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="success_text")
    await call.message.edit_text(f"<b>✅ Текущий текст успеха</b>\n<code>{current}</code>\n\n<i>• Введите новый текст</i>\n<i>• Поддерживается HTML-форматирование</i>", parse_mode="HTML")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.callback_query(lambda call: call.data == "text_error")
async def edit_error_text(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='error_text'")
    current = cursor.fetchone()[0]
    await state.update_data(text_key="error_text")
    await call.message.edit_text(f"<b>❌ Текущий текст ошибки</b>\n<code>{current}</code>\n\n<i>• Введите новый текст</i>\n<i>• Поддерживается HTML-форматирование</i>", parse_mode="HTML")
    await state.set_state(EditStates.waiting_text)
    await call.answer()

@dp.message(EditStates.waiting_text)
async def save_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    text_key = data["text_key"]
    new_text = f"<blockquote>{message.html_text}</blockquote>"
    cursor.execute("UPDATE settings SET value=? WHERE key=?", (new_text, text_key))
    conn.commit()
    await message.answer("<b>✅ Сохранено</b>\n<i>• Новый текст сохранен</i>\n<i>• Изменения вступят в силу сразу</i>", parse_mode="HTML")
    await state.clear()
    await admin_texts(message)

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
    elif "Ссылка" in key_raw and "Новая" not in key_raw:
        key = "Ссылка:"
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
    await call.message.edit_text(f"<b>⚙️ Редактирование сообщения</b>\n\n<b>• Текущий текст:</b>\n<code>{current}</code>\n\n<i>• Введите новый текст</i>\n<i>• Поддерживается HTML-форматирование</i>", parse_mode="HTML")
    await state.set_state(EditStates.waiting_system)
    await call.answer()

@dp.message(EditStates.waiting_system)
async def save_system_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    system_key = data["system_key"]
    new_text = f"<blockquote>{message.html_text}</blockquote>"
    cursor.execute("UPDATE system_messages SET value=? WHERE key=?", (new_text, system_key))
    conn.commit()
    await message.answer("<b>✅ Сохранено</b>\n<i>• Системное сообщение обновлено</i>\n<i>• Изменения вступят в силу сразу</i>", parse_mode="HTML")
    await state.clear()
    await admin_settings(message)

# ========== Назад ==========
@dp.callback_query(lambda call: call.data == "back_to_reply")
async def back_to_reply(call: types.CallbackQuery):
    await call.message.edit_text("<b>📋 Управление reply кнопками</b>\n<i>• Выберите кнопку для редактирования</i>\n<i>• Нажмите на кнопку для изменения</i>", parse_mode="HTML", reply_markup=get_reply_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_inline")
async def back_to_inline(call: types.CallbackQuery):
    await call.message.edit_text("<b>🔗 Управление инлайн кнопками</b>\n<i>• Выберите кнопку для редактирования</i>\n<i>• Нажмите на кнопку для изменения</i>", parse_mode="HTML", reply_markup=get_inline_list_keyboard())
    await call.answer()

@dp.callback_query(lambda call: call.data == "back_to_admin")
async def back_to_admin_callback(call: types.CallbackQuery):
    await call.message.edit_text("<b>🔐 Админ панель открыта</b>\n<i>• Выберите действие</i>\n<i>• Нажмите на нужную кнопку</i>", parse_mode="HTML", reply_markup=get_admin_keyboard())
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
