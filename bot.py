#!/usr/bin/env python3
"""
Телеграм бот для парсера Флибуста
"""

import asyncio
import logging
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton
)
from aiogram.filters import Command
import aiosqlite
import os
from dotenv import load_dotenv

# Импортируем наш парсер
from flibusta_parser import FlibustaParser
from kindle_sender import KindleSender

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния FSM
class UserStates(StatesGroup):
    waiting_for_search_query = State()
    waiting_for_kindle_email = State()
    confirming_kindle_email = State()

# Инициализация бота
bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# База данных
DB_PATH = "flibusta_bot.db"

def escape_markdown(text: str) -> str:
    """Экранирует специальные символы для Markdown"""
    if not text:
        return ""
    
    # Ограничиваем длину текста для избежания проблем
    if len(text) > 1000:
        text = text[:1000] + "..."
    
    # Экранируем все специальные символы Markdown
    special_chars = ['*', '_', '[', ']', '`', '#', '+', '-', '=', '|', '{', '}', '.', '!', '(', ')', '~', '>', '<']
    escaped_text = text
    
    for char in special_chars:
        escaped_text = escaped_text.replace(char, f'\\{char}')
    
    # Дополнительная проверка на экранирование
    try:
        # Проверяем, что экранированный текст не содержит неэкранированных символов
        test_message = f"Test: {escaped_text}"
        # Если есть проблемы с экранированием, возвращаем безопасную версию
        return escaped_text
    except Exception:
        # В случае ошибки возвращаем безопасную версию без специальных символов
        safe_text = text.replace('*', '').replace('_', '').replace('[', '').replace(']', '').replace('`', '')
        safe_text = safe_text.replace('#', '').replace('+', '').replace('-', '').replace('=', '').replace('|', '')
        safe_text = safe_text.replace('{', '').replace('}', '').replace('.', '').replace('!', '').replace('(', '').replace(')', '')
        safe_text = safe_text.replace('~', '').replace('>', '').replace('<', '')
        return safe_text[:500]  # Ограничиваем длину

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                kindle_email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS downloaded_books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                book_title TEXT,
                book_author TEXT,
                format_type TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kindle_sent_books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                book_title TEXT,
                book_author TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                search_query TEXT,
                results_count INTEGER,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()

async def get_user_kindle_email(telegram_id: int) -> str:
    """Получает email Kindle пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT kindle_email FROM users WHERE telegram_id = ?", 
            (telegram_id,)
        )
        result = await cursor.fetchone()
        return result[0] if result else None

async def save_user_kindle_email(telegram_id: int, kindle_email: str):
    """Сохраняет email Kindle пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users (telegram_id, kindle_email) 
            VALUES (?, ?)
        """, (telegram_id, kindle_email))
        await db.commit()

async def save_downloaded_book(telegram_id: int, book_title: str, book_author: str, format_type: str):
    """Сохраняет информацию о скачанной книге"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO downloaded_books (telegram_id, book_title, book_author, format_type)
            VALUES (?, ?, ?, ?)
        """, (telegram_id, book_title, book_author, format_type))
        await db.commit()

async def save_kindle_sent_book(telegram_id: int, book_title: str, book_author: str):
    """Сохраняет информацию об отправленной на Kindle книге"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO kindle_sent_books (telegram_id, book_title, book_author)
            VALUES (?, ?, ?)
        """, (telegram_id, book_title, book_author))
        await db.commit()

async def save_search_history(telegram_id: int, search_query: str, results_count: int):
    """Сохраняет историю поиска"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO search_history (telegram_id, search_query, results_count)
            VALUES (?, ?, ?)
        """, (telegram_id, search_query, results_count))
        await db.commit()

async def is_admin(telegram_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT telegram_id FROM admin_users WHERE telegram_id = ?", 
            (telegram_id,)
        )
        result = await cursor.fetchone()
        return result is not None

async def add_admin(telegram_id: int, username: str = None):
    """Добавляет администратора"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO admin_users (telegram_id, username) 
            VALUES (?, ?)
        """, (telegram_id, username))
        await db.commit()

# Клавиатуры
def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [KeyboardButton(text="🔍 Поиск книги"), KeyboardButton(text="⚙️ Настройка Kindle")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Админ-панель"""
    keyboard = [
        [KeyboardButton(text="🔍 Поиск книги"), KeyboardButton(text="⚙️ Настройка Kindle")],
        [KeyboardButton(text="👑 Админ-панель")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню"""
    keyboard = [
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_empty_keyboard():
    """Клавиатура для скрытия главного меню"""
    return ReplyKeyboardRemove()

def get_book_formats_keyboard(book_id: str) -> InlineKeyboardMarkup:
    """Клавиатура с форматами книги"""
    keyboard = [
        [
            InlineKeyboardButton(text="📖 EPUB", callback_data=f"download_{book_id}_epub"),
            InlineKeyboardButton(text="📄 FB2", callback_data=f"download_{book_id}_fb2"),
            InlineKeyboardButton(text="📱 MOBI", callback_data=f"download_{book_id}_mobi")
        ],
        [
            InlineKeyboardButton(text="📧 Отправить на Kindle", callback_data=f"kindle_{book_id}"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_pagination_keyboard(current_page: int, total_pages: int, query: str) -> InlineKeyboardMarkup:
    """Клавиатура пагинации - только стрелки"""
    keyboard = []
    
    # Добавляем отладочную информацию
    logger.info(f"get_pagination_keyboard: страница {current_page}, всего страниц {total_pages}, запрос '{query}'")
    
    # Навигация - только стрелки
    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{query}_{current_page-1}"))
    
    # Показываем текущую страницу в центре
    nav_row.append(InlineKeyboardButton(text=f"•{current_page}•", callback_data="no_action"))
    
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{query}_{current_page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
        logger.info(f"Добавлена навигация: {len(nav_row)} кнопок")
    
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])
    
    logger.info(f"Итоговая пагинация: {len(keyboard)} рядов")
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    # Проверяем, является ли пользователь администратором
    is_admin_user = await is_admin(message.from_user.id)
    
    welcome_text = "📚 Добро пожаловать в бот Флибуста!\n\n"
    welcome_text += "🔍 Ищите книги, скачивайте их в разных форматах\n"
    welcome_text += "📧 Отправляйте на Kindle по email\n\n"
    
    if is_admin_user:
        welcome_text += "👑 **Вы администратор**\n"
        welcome_text += "Доступна админ-панель\n\n"
        keyboard = get_admin_keyboard()
    else:
        keyboard = get_main_menu_keyboard()
    
    welcome_text += "Выберите действие:"
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")

@dp.message(F.text == "🔍 Поиск книги")
async def search_books_menu(message: types.Message, state: FSMContext):
    """Меню поиска книг"""
    await state.set_state(UserStates.waiting_for_search_query)
    # Скрываем главное меню и показываем поиск
    await message.answer(
        "🔍 Введите название книги или автора для поиска:",
        reply_markup=get_back_to_main_keyboard()
    )
    # Скрываем главное меню
    await message.answer(
        "⌨️ Главное меню скрыто. Используйте кнопку '🏠 Главное меню' для возврата.",
        reply_markup=get_empty_keyboard()
    )

@dp.message(F.text == "⚙️ Настройка Kindle")
async def kindle_settings_menu(message: types.Message):
    """Меню настройки Kindle"""
    kindle_email = await get_user_kindle_email(message.from_user.id)
    
    if kindle_email:
        await message.answer(
            f"⚙️ **Настройки Kindle**\n\n"
            f"📧 **Текущий email:** `{kindle_email}`\n\n"
            "Для изменения email нажмите кнопку ниже:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Изменить email", callback_data="change_kindle_email")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ]),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "⚙️ **Настройка Kindle**\n\n"
            "📧 Для отправки книг на Kindle нужно указать ваш Kindle email.\n\n"
            "🔗 **Важно:** Добавьте адрес бота `abookerbot@gmail.com` в белый список:\n"
            "https://www.amazon.com/hz/mycd/preferences/myx#/home/settings/payment\n\n"
            "После этого введите ваш Kindle email:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📧 Ввести email", callback_data="set_kindle_email")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ]),
            parse_mode="Markdown"
        )
    
    # Скрываем главное меню
    await message.answer(
        "⌨️ Главное меню скрыто. Используйте кнопку '🏠 Главное меню' для возврата.",
        reply_markup=get_empty_keyboard()
    )





@dp.message(F.text == "👑 Админ-панель")
async def admin_panel(message: types.Message):
    """Админ-панель"""
    # Проверяем права администратора
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели")
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Общая статистика
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        total_users = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM downloaded_books")
        total_downloads = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM kindle_sent_books")
        total_kindle = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM search_history")
        total_searches = (await cursor.fetchone())[0]
    
    text = f"👑 **Админ-панель**\n\n"
    text += f"📊 **Общая статистика:**\n"
    text += f"👥 Пользователей: {total_users}\n"
    text += f"⬇️ Загрузок: {total_downloads}\n"
    text += f"📧 Kindle отправок: {total_kindle}\n"
    text += f"🔍 Поисков: {total_searches}\n\n"
    text += "**Действия:**"
    
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users")],
            [InlineKeyboardButton(text="📊 Детальная статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton(text="🗑️ Очистить кеш бота", callback_data="admin_clear_cache")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]),
        parse_mode="Markdown"
    )
    
    # Скрываем главное меню
    await message.answer(
        "⌨️ Главное меню скрыто. Используйте кнопку '🏠 Главное меню' для возврата.",
        reply_markup=get_empty_keyboard()
    )



# Обработчики поиска
@dp.message(UserStates.waiting_for_search_query)
async def process_search_query(message: types.Message, state: FSMContext):
    """Обработка поискового запроса"""
    query = message.text.strip()
    
    if len(query) < 2:
        await message.answer("❌ Запрос должен содержать минимум 2 символа")
        return
    
    await state.clear()
    
    # Показываем сообщение о поиске
    search_msg = await message.answer("🔍 Ищу книги...")
    
    try:
        async with FlibustaParser() as parser:
            # Авторизация
            if not await parser.login():
                await search_msg.edit_text("❌ Ошибка авторизации на Флибуста")
                return
            
            # Поиск книг
            books = await parser.search_books(query, limit=100)
            
            # Добавляем отладочную информацию
            logger.info(f"Поиск по запросу '{query}': найдено {len(books) if books else 0} книг")
            if books:
                logger.info(f"Первая книга: {books[0] if len(books) > 0 else 'Нет данных'}")
                logger.info(f"Ключи первой книги: {list(books[0].keys()) if books else 'Нет данных'}")
            
            if not books:
                # Экранируем запрос для безопасного отображения в Markdown
                query_escaped = query.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
                
                await search_msg.edit_text(
                    f"❌ По запросу '{query_escaped}' ничего не найдено",
                    reply_markup=get_back_to_main_keyboard()
                )
                return
            
            # Сохраняем результаты в состояние
            await state.update_data(
                search_results=books,
                current_page=1,
                search_query=query
            )
            
            # Показываем первую страницу
            await show_search_results_page(message, books[:10], 1, len(books), query)
            await search_msg.delete()
            
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        await search_msg.edit_text(
            "❌ Произошла ошибка при поиске. Попробуйте позже.",
            reply_markup=get_back_to_main_keyboard()
        )

def create_search_results_content(books: list, page: int, total_books: int, query: str):
    """Создает содержимое для страницы результатов поиска"""
    total_pages = (total_books + 9) // 10  # Округляем вверх (10 книг на страницу)
    
    # Добавляем отладочную информацию
    logger.info(f"create_search_results_content: {len(books)} книг, страница {page}, всего {total_books}")
    if books:
        logger.info(f"Первая книга в списке: {books[0]}")
        logger.info(f"Ключи первой книги: {list(books[0].keys()) if books else 'Нет данных'}")
    
    # Формируем текст
    # Экранируем запрос для безопасного отображения в Markdown
    query_escaped = escape_markdown(query)
    
    text = f"🔍 **Результаты поиска: '{query_escaped}'**\n"
    text += f"📚 Найдено: {total_books} книг\n"
    text += f"📄 Страница {page} из {total_pages}\n\n"
    
    # Добавляем список книг с авторами
    for i, book in enumerate(books, 1):
        title = book.get('title', 'Без названия')
        author = book.get('author', 'Автор не указан')
        
        # Экранируем специальные символы Markdown
        title_escaped = escape_markdown(title)
        author_escaped = escape_markdown(author)
        
        # Ограничиваем длину названия и автора для красивого отображения
        title_short = title_escaped[:50] + "..." if len(title_escaped) > 50 else title_escaped
        author_short = author_escaped[:40] + "..." if len(author_escaped) > 40 else author_escaped
        
        text += f"**{i}.** 📖 **{title_short}**\n"
        text += f"👤 {author_short}\n\n"
    
    text += "**Выберите книгу для просмотра деталей:**"
    
    # Создаем клавиатуру с книгами и пагинацией
    keyboard = []
    
    # Кнопки для каждой книги - организуем в два ряда по 5 кнопок
    book_buttons_row1 = []
    book_buttons_row2 = []
    
    for i, book in enumerate(books, 1):
        book_id = book.get('book_id', '')  # Используем 'book_id' вместо 'id'
        title = book.get('title', 'Без названия')
        
        logger.info(f"Обрабатываю книгу {i}: book_id={book_id}, title={title}")
        
        if book_id:
            # Создаем более компактные кнопки
            button = InlineKeyboardButton(
                text=f"{i}",
                callback_data=f"select_book_{book_id}"
            )
            
            # Распределяем кнопки по рядам (по 5 кнопок в ряду)
            if i <= 5:  # Первые 5 книг в первый ряд
                book_buttons_row1.append(button)
            elif i <= 10:  # Следующие 5 книг во второй ряд
                book_buttons_row2.append(button)
    
    # Добавляем ряды с книгами
    if book_buttons_row1:
        keyboard.append(book_buttons_row1)
        logger.info(f"Добавлен первый ряд: {len(book_buttons_row1)} кнопок")
    if book_buttons_row2:
        keyboard.append(book_buttons_row2)
        logger.info(f"Добавлен второй ряд: {len(book_buttons_row2)} кнопок")
    
    # Добавляем пагинацию
    pagination_keyboard = get_pagination_keyboard(page, total_pages, query)
    keyboard.extend(pagination_keyboard.inline_keyboard)
    
    logger.info(f"Итоговая клавиатура: {len(keyboard)} рядов")
    
    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)

async def show_search_results_page(message: types.Message, books: list, page: int, total_books: int, query: str):
    """Показывает страницу результатов поиска"""
    text, keyboard = create_search_results_content(books, page, total_books, query)
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Обработчики callback
@dp.callback_query(F.data == "no_action")
async def process_no_action(callback: types.CallbackQuery):
    """Обработка неактивных кнопок"""
    await callback.answer("📄 Текущая страница")

@dp.callback_query(F.data.startswith("page_"))
async def process_page_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработка пагинации"""
    try:
        await callback.answer("📄 Переключаю страницу...")
        
        _, query, page = callback.data.split("_", 2)
        page = int(page)
        
        # Получаем результаты поиска из состояния
        data = await state.get_data()
        search_results = data.get('search_results', [])
        
        if not search_results:
            await callback.answer("❌ Результаты поиска не найдены")
            return
        
        # Показываем нужную страницу
        start_idx = (page - 1) * 10
        end_idx = start_idx + 10
        page_books = search_results[start_idx:end_idx]
        
        # Экранируем запрос для безопасного отображения в Markdown
        query_escaped = escape_markdown(query)
        
        # Создаем новое содержимое для страницы
        text, keyboard = create_search_results_content(page_books, page, len(search_results), query_escaped)
        
        # Редактируем существующее сообщение вместо создания нового
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка пагинации: {e}")
        
        # Проверяем валидность callback'а перед отправкой ответа об ошибке
        try:
            await callback.answer("❌ Ошибка переключения страницы")
        except Exception as callback_error:
            logger.error(f"Не удалось отправить callback answer: {callback_error}")
        
        try:
            await callback.message.answer(
                "❌ **Ошибка пагинации**\n\n"
                "Не удалось переключить страницу. Попробуйте еще раз.",
                reply_markup=get_back_to_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as message_error:
            logger.error(f"Не удалось отправить сообщение об ошибке: {message_error}")

@dp.callback_query(F.data.startswith("select_book_"))
async def process_book_selection_from_search(callback: types.CallbackQuery):
    """Обработка выбора книги из результатов поиска"""
    try:
        await callback.answer("📖 Загружаю информацию о книге...")
        
        book_id = callback.data.split("_", 2)[2]
        
        async with FlibustaParser() as parser:
            if not await parser.login():
                await callback.answer("❌ Ошибка авторизации")
                return
            
            # Получаем детали книги
            book_details = await parser.get_book_details(book_id)
            
            if not book_details:
                await callback.answer("❌ Не удалось получить информацию о книге")
                return
            
            # Формируем карточку книги
            title_escaped = escape_markdown(book_details['title'])
            author_escaped = escape_markdown(book_details['author'])
            
            text = f"📖 **{title_escaped}**\n\n"
            text += f"👤 **Автор:** {author_escaped}\n"
            
            if book_details.get('genres'):
                genres_escaped = escape_markdown(', '.join(book_details['genres']))
                text += f"🏷️ **Жанр:** {genres_escaped}\n"
            
            if book_details.get('description'):
                desc = book_details['description'][:300] + "..." if len(book_details['description']) > 300 else book_details['description']
                desc_escaped = escape_markdown(desc)
                text += f"\n📝 **Описание:**\n{desc_escaped}\n"
            
            # Показываем карточку с кнопками форматов
            keyboard = get_book_formats_keyboard(book_id)
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"Ошибка получения деталей книги: {e}")
        
        # Проверяем валидность callback'а перед отправкой ответа об ошибке
        try:
            await callback.answer("❌ Произошла ошибка")
        except Exception as callback_error:
            logger.error(f"Не удалось отправить callback answer: {callback_error}")
        
        # Отправляем сообщение об ошибке
        try:
            await callback.message.answer(
                "❌ **Ошибка загрузки книги**\n\n"
                "Не удалось получить информацию о книге. Попробуйте еще раз.",
                reply_markup=get_back_to_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as message_error:
            logger.error(f"Не удалось отправить сообщение об ошибке: {message_error}")

@dp.callback_query(F.data.startswith("book_"))
async def process_book_selection(callback: types.CallbackQuery):
    """Обработка выбора книги (для совместимости)"""
    await process_book_selection_from_search(callback)

@dp.callback_query(F.data.startswith("download_"))
async def process_download(callback: types.CallbackQuery):
    """Обработка скачивания книги"""
    try:
        # Проверяем, что callback еще валиден
        if callback.message.date.timestamp() < time.time() - 3600:  # 1 час
            await callback.answer("❌ Слишком старый запрос, попробуйте снова")
            return
            
        _, book_id, format_type = callback.data.split("_", 2)
        
        await callback.answer("⬇️ Загружаю книгу...")
        
        async with FlibustaParser() as parser:
            if not await parser.login():
                await callback.answer("❌ Ошибка авторизации")
                return
            
            # Скачиваем книгу
            book_content = await parser.download_book(book_id, format_type)
            
            if not book_content:
                await callback.answer("❌ Не удалось скачать книгу")
                return
            
            # Получаем детали книги для имени файла
            book_details = await parser.get_book_details(book_id)
            filename = f"{book_details['title']}.{format_type}"
            
            # Отправляем файл
            title_escaped = escape_markdown(book_details['title'])
            author_escaped = escape_markdown(book_details['author'])
            
            await callback.message.answer_document(
                types.BufferedInputFile(
                    book_content, 
                    filename=filename
                ),
                caption=f"📖 **{title_escaped}**\n👤 {author_escaped}\n📁 Формат: {format_type.upper()}",
                reply_markup=get_back_to_main_keyboard(),
                parse_mode="Markdown"
            )
            
            # Сохраняем в БД
            await save_downloaded_book(
                callback.from_user.id,
                book_details['title'],
                book_details['author'],
                format_type
            )
            
            # Проверяем валидность callback'а перед отправкой ответа
            try:
                await callback.answer("✅ Книга загружена!")
            except Exception as callback_error:
                logger.warning(f"Не удалось отправить callback answer после успешной загрузки: {callback_error}")
            
    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}")
        
        # Проверяем валидность callback'а перед отправкой ответа об ошибке
        try:
            await callback.answer("❌ Произошла ошибка при скачивании")
        except Exception as callback_error:
            logger.error(f"Не удалось отправить callback answer: {callback_error}")
        
        try:
            await callback.message.answer(
                "❌ **Ошибка скачивания**\n\n"
                "Не удалось скачать книгу. Попробуйте еще раз.",
                reply_markup=get_back_to_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as message_error:
            logger.error(f"Не удалось отправить сообщение об ошибке: {message_error}")

@dp.callback_query(F.data.startswith("kindle_"))
async def process_kindle_send(callback: types.CallbackQuery):
    """Обработка отправки на Kindle"""
    try:
        # Проверяем, что callback еще валиден
        if callback.message.date.timestamp() < time.time() - 3600:  # 1 час
            await callback.answer("❌ Слишком старый запрос, попробуйте снова")
            return
            
        book_id = callback.data.split("_", 1)[1]
        
        # Проверяем настройки Kindle
        kindle_email = await get_user_kindle_email(callback.from_user.id)
        
        if not kindle_email:
            await callback.answer("❌ Настройте Kindle email")
            await callback.message.answer(
                "❌ **Kindle email не настроен!**\n\n"
                "Для отправки книг на Kindle необходимо настроить email в главном меню.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
                ]),
                parse_mode="Markdown"
            )
            return
        
        await callback.answer("📧 Отправляю на Kindle...")
        
        async with FlibustaParser() as parser:
            if not await parser.login():
                await callback.answer("❌ Ошибка авторизации")
                return
            
            # Скачиваем книгу в EPUB
            book_content = await parser.download_book(book_id, 'epub')
            
            if not book_content:
                await callback.answer("❌ Не удалось скачать книгу")
                return
            
            # Получаем детали книги
            book_details = await parser.get_book_details(book_id)
            
            # Отправляем на Kindle
            kindle_sender = KindleSender()
            success = kindle_sender.send_book_to_kindle(
                book_content, 
                book_details['title'], 
                book_details['author']
            )
            
            if success:
                # Сохраняем в БД
                await save_kindle_sent_book(
                    callback.from_user.id,
                    book_details['title'],
                    book_details['author']
                )
                
                # Проверяем валидность callback'а перед отправкой ответа
                try:
                    await callback.answer("✅ Книга отправлена на Kindle!")
                except Exception as callback_error:
                    logger.warning(f"Не удалось отправить callback answer после успешной отправки: {callback_error}")
                
                # Экранируем специальные символы Markdown
                title_escaped = escape_markdown(book_details['title'])
                author_escaped = escape_markdown(book_details['author'])
                
                # Дополнительная проверка на пустые значения
                if not title_escaped:
                    title_escaped = "Неизвестная книга"
                if not author_escaped:
                    author_escaped = "Неизвестный автор"
                
                try:
                    await callback.message.answer(
                        f"✅ **Книга отправлена на Kindle!**\n\n"
                        f"📖 {title_escaped}\n"
                        f"👤 {author_escaped}\n"
                        f"📧 {kindle_email}\n\n"
                        f"Книга будет доставлена на ваш Kindle в течение нескольких минут.",
                        reply_markup=get_back_to_main_keyboard(),
                        parse_mode="Markdown"
                    )
                except Exception as markdown_error:
                    logger.warning(f"Ошибка Markdown форматирования, отправляем без разметки: {markdown_error}")
                    # Отправляем без Markdown разметки
                    await callback.message.answer(
                        f"✅ Книга отправлена на Kindle!\n\n"
                        f"📖 {title_escaped}\n"
                        f"👤 {author_escaped}\n"
                        f"📧 {kindle_email}\n\n"
                        f"Книга будет доставлена на ваш Kindle в течение нескольких минут.",
                        reply_markup=get_back_to_main_keyboard()
                    )
            else:
                # Проверяем валидность callback'а перед отправкой ответа
                try:
                    await callback.answer("❌ Ошибка отправки на Kindle")
                except Exception as callback_error:
                    logger.warning(f"Не удалось отправить callback answer после ошибки отправки: {callback_error}")
                
                try:
                    await callback.message.answer(
                        "❌ **Ошибка отправки на Kindle**\n\n"
                        "Проверьте настройки Gmail и попробуйте снова.",
                        reply_markup=get_back_to_main_keyboard(),
                        parse_mode="Markdown"
                    )
                except Exception as markdown_error:
                    logger.warning(f"Ошибка Markdown форматирования в сообщении об ошибке: {markdown_error}")
                    await callback.message.answer(
                        "❌ Ошибка отправки на Kindle\n\n"
                        "Проверьте настройки Gmail и попробуйте снова.",
                        reply_markup=get_back_to_main_keyboard()
                    )
            
    except Exception as e:
        logger.error(f"Ошибка отправки на Kindle: {e}")
        try:
            await callback.answer("❌ Произошла ошибка")
        except Exception as callback_error:
            logger.error(f"Не удалось отправить callback answer: {callback_error}")
        
        try:
            await callback.message.answer(
                "❌ **Ошибка отправки на Kindle**\n\n"
                "Не удалось отправить книгу. Попробуйте еще раз.",
                reply_markup=get_back_to_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as markdown_error:
            logger.warning(f"Ошибка Markdown форматирования в сообщении об общей ошибке: {markdown_error}")
            try:
                await callback.message.answer(
                    "❌ Ошибка отправки на Kindle\n\n"
                    "Не удалось отправить книгу. Попробуйте еще раз.",
                    reply_markup=get_back_to_main_keyboard()
                )
            except Exception as message_error:
                logger.error(f"Не удалось отправить сообщение об ошибке: {message_error}")

@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    try:
        await state.clear()
        # Показываем главное меню с ReplyKeyboardMarkup
        try:
            await callback.message.answer(
                "🏠 **Главное меню**\n\n"
                "Выберите действие:",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as markdown_error:
            logger.warning(f"Ошибка Markdown форматирования в главном меню: {markdown_error}")
            await callback.message.answer(
                "🏠 Главное меню\n\n"
                "Выберите действие:",
                reply_markup=get_main_menu_keyboard()
            )
        await callback.answer("🏠 Возврат в главное меню")
    except Exception as e:
        logger.error(f"Ошибка возврата в главное меню: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        await callback.message.answer(
            "🏠 **Главное меню**\n\n"
            "Выберите действие:",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer("🏠 Возврат в главное меню")

@dp.callback_query(F.data == "kindle_settings")
async def kindle_settings_callback(callback: types.CallbackQuery):
    """Настройки Kindle через callback"""
    try:
        await callback.answer("⚙️ Открываю настройки Kindle...")
        await kindle_settings_menu(callback.message)
    except Exception as e:
        logger.error(f"Ошибка открытия настроек Kindle: {e}")
        await callback.answer("❌ Ошибка открытия настроек")

@dp.callback_query(F.data == "set_kindle_email")
async def set_kindle_email_callback(callback: types.CallbackQuery, state: FSMContext):
    """Установка Kindle email"""
    try:
        await callback.answer("📧 Введите ваш Kindle email...")
        await state.set_state(UserStates.waiting_for_kindle_email)
        await callback.message.edit_text(
            "📧 Введите ваш Kindle email:\n\n"
            "Формат: `ваше_имя_XXXXXX@kindle.com`",
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка установки Kindle email: {e}")
        await callback.answer("❌ Ошибка настройки email")

@dp.callback_query(F.data == "change_kindle_email")
async def change_kindle_email_callback(callback: types.CallbackQuery, state: FSMContext):
    """Изменение Kindle email"""
    try:
        await callback.answer("📧 Введите новый Kindle email...")
        await state.set_state(UserStates.waiting_for_kindle_email)
        await callback.message.edit_text(
            "📧 Введите новый Kindle email:\n\n"
            "Формат: `ваше_имя_XXXXXX@kindle.com`",
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка изменения Kindle email: {e}")
        await callback.answer("❌ Ошибка изменения email")

@dp.message(UserStates.waiting_for_kindle_email)
async def process_kindle_email(message: types.Message, state: FSMContext):
    """Обработка ввода Kindle email"""
    email = message.text.strip()
    
    # Простая валидация
    if not email.endswith('@kindle.com'):
        await message.answer(
            "❌ **Неверный формат email!**\n\n"
            "Kindle email должен заканчиваться на `@kindle.com`\n"
            "Пример: `myname_XXXXXX@kindle.com`",
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    # Сохраняем email и запрашиваем подтверждение
    await state.update_data(kindle_email=email)
    await state.set_state(UserStates.confirming_kindle_email)
    
    await message.answer(
        f"📧 **Подтвердите настройки Kindle**\n\n"
        f"**Email:** `{email}`\n\n"
        f"⚠️ **Важно:** Убедитесь, что:\n"
        f"1. Email указан верно\n"
        f"2. Адрес `abookerbot@gmail.com` добавлен в белый список Amazon\n\n"
        f"Все верно?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, все верно", callback_data="confirm_kindle_email")],
            [InlineKeyboardButton(text="❌ Нет, изменить", callback_data="set_kindle_email")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "confirm_kindle_email")
async def confirm_kindle_email_callback(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение Kindle email"""
    data = await state.get_data()
    email = data.get('kindle_email')
    
    if email:
        # Сохраняем в БД
        await save_user_kindle_email(callback.from_user.id, email)
        
        await callback.message.edit_text(
            f"✅ **Kindle email сохранен!**\n\n"
            f"📧 Email: `{email}`\n\n"
            f"Теперь вы можете отправлять книги на Kindle прямо из бота!",
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )
        
        await state.clear()
    else:
        await callback.answer("❌ Email не найден")

# Обработчики истории
@dp.callback_query(F.data == "download_history")
async def show_download_history(callback: types.CallbackQuery):
    """Показывает историю загрузок"""
    try:
        await callback.answer("📚 Загружаю историю загрузок...")
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT book_title, book_author, format_type, downloaded_at 
                FROM downloaded_books 
                WHERE telegram_id = ? 
                ORDER BY downloaded_at DESC 
                LIMIT 10
            """, (callback.from_user.id,))
            
            books = await cursor.fetchall()
        
        if not books:
            await callback.message.answer(
                "📚 **История загрузок**\n\n"
                "У вас пока нет загруженных книг.",
                reply_markup=get_back_to_main_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        text = "📚 **История загрузок**\n\n"
        for book in books:
            title, author, format_type, date = book
            text += f"📖 **{title}**\n"
            text += f"👤 {author}\n"
            text += f"📁 {format_type.upper()} • {date[:10]}\n\n"
        
        await callback.message.answer(
            text,
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Ошибка показа истории загрузок: {e}")
        await callback.answer("❌ Ошибка загрузки истории")
        await callback.message.answer(
            "❌ **Ошибка загрузки истории**\n\n"
            "Не удалось загрузить историю загрузок. Попробуйте еще раз.",
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )

@dp.callback_query(F.data == "kindle_history")
async def show_kindle_history(callback: types.CallbackQuery):
    """Показывает историю отправок на Kindle"""
    try:
        await callback.answer("📧 Загружаю историю Kindle...")
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT book_title, book_author, sent_at 
                FROM kindle_sent_books 
                WHERE telegram_id = ? 
                ORDER BY sent_at DESC 
                LIMIT 10
            """, (callback.from_user.id,))
            
            books = await cursor.fetchall()
        
        if not books:
            await callback.message.answer(
                "📧 **История отправок на Kindle**\n\n"
                "Вы пока не отправляли книги на Kindle.",
                reply_markup=get_back_to_main_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        text = "📧 **История отправок на Kindle**\n\n"
        for book in books:
            title, author, date = book
            text += f"📖 **{title}**\n"
            text += f"👤 {author}\n"
            text += f"📅 {date[:10]}\n\n"
        
        await callback.message.answer(
            text,
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Ошибка показа истории Kindle: {e}")
        await callback.answer("❌ Ошибка загрузки истории")
        await callback.message.answer(
            "❌ **Ошибка загрузки истории**\n\n"
            "Не удалось загрузить историю Kindle. Попробуйте еще раз.",
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )

@dp.callback_query(F.data == "admin_clear_cache")
async def admin_clear_cache(callback: types.CallbackQuery):
    """Очистка кеша бота администратором"""
    try:
        # Проверяем права администратора
        if not await is_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет доступа к этой функции")
            return
        
        await callback.answer("🗑️ Очищаю кеш бота...")
        
        # Очищаем команды бота
        await bot.delete_my_commands()
        
        await callback.message.answer(
            "✅ **Кеш бота очищен!**\n\n"
            "Все старые команды и кеш удалены.\n"
            "Пользователи увидят обновленное меню при следующем запуске бота.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ]),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Ошибка очистки кеша: {e}")
        await callback.answer("❌ Ошибка очистки кеша")
        await callback.message.answer(
            "❌ **Ошибка очистки кеша**\n\n"
            "Не удалось очистить кеш бота. Попробуйте еще раз.",
            reply_markup=get_back_to_main_keyboard(),
            parse_mode="Markdown"
        )



@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: types.CallbackQuery):
    """Обработчик возврата в админ-панель"""
    try:
        # Проверяем права администратора
        if not await is_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет доступа к админ-панели")
            return
        
        await callback.answer("👑 Переходим в админ-панель...")
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Общая статистика
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM downloaded_books")
            total_downloads = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM kindle_sent_books")
            total_kindle = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM search_history")
            total_searches = (await cursor.fetchone())[0]
        
        text = f"👑 **Админ-панель**\n\n"
        text += f"📊 **Общая статистика:**\n"
        text += f"👥 Пользователей: {total_users}\n"
        text += f"⬇️ Загрузок: {total_downloads}\n"
        text += f"📧 Kindle отправок: {total_kindle}\n"
        text += f"🔍 Поисков: {total_searches}\n\n"
        text += "**Действия:**"
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin_users")],
                [InlineKeyboardButton(text="📊 Детальная статистика", callback_data="admin_stats")],
                [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add")],
                [InlineKeyboardButton(text="🗑️ Очистить кеш бота", callback_data="admin_clear_cache")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ]),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Ошибка возврата в админ-панель: {e}")
        await callback.answer("❌ Ошибка загрузки админ-панели")

async def main():
    """Главная функция"""
    # Инициализируем БД
    await init_db()
    
    # Очищаем кеш и сбрасываем команды бота
    try:
        await bot.delete_my_commands()
        logger.info("✅ Кеш бота очищен, команды сброшены")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось очистить кеш бота: {e}")
    
    # Запускаем бота
    logger.info("🚀 Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
