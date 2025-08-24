#!/usr/bin/env python3
"""
Простой асинхронный парсер для сайта Флибуста (flibusta.is)
"""

import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import urljoin, quote
import json
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


class FlibustaParser:
    """Асинхронный парсер для сайта Флибуста"""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv('FLIBUSTA_BASE_URL', 'https://flibusta.is')
        self.session = None
        self.is_authenticated = False
        self.user_id = None
        
        # Заголовки для имитации браузера
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Таймауты
        self.timeout = aiohttp.ClientTimeout(total=30, connect=10)
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        self.session = aiohttp.ClientSession(headers=self.headers, timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        if self.session:
            await self.session.close()
    
    async def login(self, username: str = None, password: str = None) -> bool:
        """Авторизация на сайте Флибуста"""
        username = username or os.getenv('FLIBUSTA_USERNAME')
        password = password or os.getenv('FLIBUSTA_PASSWORD')
        
        if not username or not password:
            print("❌ Не указаны учетные данные")
            return False
        
        try:
            print(f"🔐 Авторизация пользователя: {username}")
            
            # Получаем страницу входа
            async with self.session.get(f"{self.base_url}/user/login") as response:
                if response.status != 200:
                    print(f"❌ Ошибка получения страницы входа: {response.status}")
                    return False
                
                login_page_text = await response.text()
            
            soup = BeautifulSoup(login_page_text, 'html.parser')
            
            # Ищем форму входа
            login_form = soup.find('form', {'method': 'post'})
            if not login_form:
                print("❌ Форма входа не найдена")
                return False
            
            # Получаем CSRF токен если есть
            csrf_token = None
            csrf_input = login_form.find('input', {'name': 'csrf_token'})
            if csrf_input:
                csrf_token = csrf_input.get('value')
            
            # Данные для входа
            login_data = {
                'name': username,
                'pass': password,
                'op': 'Войти',
                'form_build_id': '',
                'form_id': 'user_login'
            }
            
            if csrf_token:
                login_data['csrf_token'] = csrf_token
            
            # Выполняем вход
            async with self.session.post(
                f"{self.base_url}/user/login",
                data=login_data,
                allow_redirects=True
            ) as login_response:
                
                if login_response.status == 200:
                    login_response_text = await login_response.text()
                    
                    # Проверяем успешность входа
                    if 'user' in str(login_response.url) or 'logout' in login_response_text:
                        self.is_authenticated = True
                        print(f"✅ Успешная авторизация")
                        
                        # Получаем ID пользователя
                        await self._get_user_id()
                        
                        # Задержка между запросами
                        await asyncio.sleep(1.0)
                        return True
                    else:
                        print("❌ Авторизация не удалась - проверьте логин и пароль")
                        return False
                else:
                    print(f"❌ Ошибка при входе: {login_response.status}")
                    return False
                    
        except Exception as e:
            print(f"❌ Ошибка при авторизации: {e}")
            return False
    
    async def _get_user_id(self):
        """Получает ID пользователя"""
        try:
            async with self.session.get(f"{self.base_url}/user") as response:
                if response.status == 200:
                    profile_text = await response.text()
                    soup = BeautifulSoup(profile_text, 'html.parser')
                    
                    user_link = soup.find('a', href=re.compile(r'/user/\d+'))
                    if user_link:
                        user_id = re.search(r'/user/(\d+)', user_link['href'])
                        if user_id:
                            self.user_id = user_id.group(1)
                            print(f"🆔 ID пользователя: {self.user_id}")
        except Exception as e:
            print(f"⚠️ Ошибка получения ID пользователя: {e}")
    
    async def search_books(self, query: str, limit: int = 20) -> List[Dict]:
        """Поиск книг по запросу"""
        try:
            print(f"🔍 Поиск: '{query}' (лимит: {limit})")
            
            # Кодируем запрос для URL
            encoded_query = quote(query.encode('utf-8'))
            search_url = f"{self.base_url}/booksearch?ask={encoded_query}"
            
            async with self.session.get(search_url) as response:
                if response.status != 200:
                    print(f"❌ Ошибка поиска: {response.status}")
                    return []
                
                search_text = await response.text()
            
            # Отладка (раскомментируйте если нужно)
            # with open('debug_search.html', 'w', encoding='utf-8') as f:
            #     f.write(search_text)
            # print("💾 HTML страницы сохранен в debug_search.html")
            
            soup = BeautifulSoup(search_text, 'html.parser')
            books = []
            
            # Ищем секцию "Найденные книги"
            books_section = None
            for h3 in soup.find_all('h3'):
                if 'Найденные книги' in h3.get_text():
                    books_section = h3.find_next_sibling('ul')
                    break
            
            if books_section:
                book_items = books_section.find_all('li')
                
                for item in book_items[:limit]:
                    try:
                        # Ищем ссылку на книгу (первая ссылка с /b/)
                        book_link = item.find('a', href=re.compile(r'/b/\d+'))
                        if not book_link:
                            continue
                        
                        # Извлекаем информацию о книге
                        book_info = {
                            'title': book_link.get_text(strip=True),
                            'book_url': urljoin(self.base_url, book_link['href']),
                            'book_id': re.search(r'/b/(\d+)', book_link['href']).group(1)
                        }
                        
                        # Ищем автора (ссылка с /a/)
                        author_links = item.find_all('a', href=re.compile(r'/a/\d+'))
                        if author_links:
                            # Берем первого автора
                            author_link = author_links[0]
                            book_info['author'] = author_link.get_text(strip=True)
                            book_info['author_url'] = urljoin(self.base_url, author_link['href'])
                            book_info['author_id'] = re.search(r'/a/(\d+)', author_link['href']).group(1)
                            
                            # Если есть несколько авторов
                            if len(author_links) > 1:
                                authors = []
                                for auth_link in author_links:
                                    authors.append(auth_link.get_text(strip=True))
                                book_info['authors'] = authors
                        
                        # Очищаем название от подсветки и лишних пробелов
                        title_clean = re.sub(r'<span[^>]*>|</span>', '', book_info['title'])
                        title_clean = re.sub(r'\s+', ' ', title_clean).strip()
                        book_info['title'] = title_clean
                        
                        if book_info['title']:  # Только если есть название
                            books.append(book_info)
                    except Exception as e:
                        print(f"⚠️ Ошибка обработки книги: {e}")
                        continue
            else:
                print("❌ Секция 'Найденные книги' не найдена")
                
                # Fallback: ищем любые ссылки на книги
                all_book_links = soup.find_all('a', href=re.compile(r'/b/\d+'))
                
                for link in all_book_links[:limit]:
                    try:
                        book_info = {
                            'title': link.get_text(strip=True),
                            'book_url': urljoin(self.base_url, link['href']),
                            'book_id': re.search(r'/b/(\d+)', link['href']).group(1)
                        }
                        
                        if book_info['title']:
                            books.append(book_info)
                    except Exception as e:
                        continue
            
            print(f"📚 Итого найдено: {len(books)} книг")
            
            # Задержка между запросами
            await asyncio.sleep(1.0)
            return books
            
        except Exception as e:
            print(f"❌ Ошибка поиска: {e}")
            return []
    
    def _parse_book_item(self, item) -> Optional[Dict]:
        """Парсит информацию о книге"""
        try:
            book_info = {}
            
            # Название книги
            title_elem = item.find('a', href=re.compile(r'/book/\d+'))
            if title_elem:
                book_info['title'] = title_elem.get_text(strip=True)
                book_info['book_url'] = urljoin(self.base_url, title_elem['href'])
                book_info['book_id'] = re.search(r'/book/(\d+)', title_elem['href']).group(1)
            
            # Автор
            author_elem = item.find('a', href=re.compile(r'/author/\d+'))
            if author_elem:
                book_info['author'] = author_elem.get_text(strip=True)
                book_info['author_url'] = urljoin(self.base_url, author_elem['href'])
                book_info['author_id'] = re.search(r'/author/(\d+)', author_elem['href']).group(1)
            
            # Жанры
            genres = []
            genre_elems = item.find_all('a', href=re.compile(r'/genre/\d+'))
            for genre_elem in genre_elems:
                genres.append(genre_elem.get_text(strip=True))
            if genres:
                book_info['genres'] = genres
            
            # Описание
            desc_elem = item.find('div', class_='description') or item.find('div', class_='annotation')
            if desc_elem:
                book_info['description'] = desc_elem.get_text(strip=True)
            
            # Рейтинг
            rating_elem = item.find('span', class_='rating') or item.find('div', class_='score')
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                if rating_match:
                    book_info['rating'] = float(rating_match.group(1))
            
            return book_info if book_info else None
            
        except Exception as e:
            print(f"⚠️ Ошибка парсинга книги: {e}")
            return None
    
    async def get_book_details(self, book_id: str) -> Optional[Dict]:
        """Получает детальную информацию о книге"""
        try:
            print(f"📖 Детали книги ID: {book_id}")
            
            book_url = f"{self.base_url}/b/{book_id}"
            
            async with self.session.get(book_url) as response:
                if response.status != 200:
                    print(f"❌ Ошибка получения книги: {response.status}")
                    return None
                
                book_text = await response.text()
            
            # Отладка (раскомментируйте если нужно)
            # with open(f'debug_book_{book_id}.html', 'w', encoding='utf-8') as f:
            #     f.write(book_text)
            # print(f"💾 HTML страницы книги сохранен в debug_book_{book_id}.html")
            
            soup = BeautifulSoup(book_text, 'html.parser')
            book_info = {'book_id': book_id, 'book_url': book_url}
            
            # Название - ищем в заголовке страницы
            title_elem = soup.find('h1', class_='title')
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                # Убираем формат файла из названия (fb2), (epub) и т.д.
                title_text = re.sub(r'\s*\([^)]+\)\s*$', '', title_text)
                book_info['title'] = title_text
            else:
                # Fallback на обычный title
                title_elem = soup.find('title')
                if title_elem:
                    title_text = title_elem.get_text(strip=True)
                    if '| Флибуста' in title_text:
                        title_text = title_text.split('| Флибуста')[0].strip()
                    book_info['title'] = title_text
            
            # Автор - ищем ссылку на автора (первая ссылка /a/)
            author_elem = soup.find('a', href=re.compile(r'/a/\d+'))
            if author_elem:
                book_info['author'] = author_elem.get_text(strip=True)
                book_info['author_url'] = urljoin(self.base_url, author_elem['href'])
                book_info['author_id'] = re.search(r'/a/(\d+)', author_elem['href']).group(1)
            
            # Жанры - ищем ссылки на жанры
            genres = []
            genre_elems = soup.find_all('a', href=re.compile(r'/g/\d+'))
            for genre_elem in genre_elems:
                genre_text = genre_elem.get_text(strip=True)
                if genre_text and len(genre_text) > 2:  # Фильтруем пустые
                    genres.append(genre_text)
            if genres:
                book_info['genres'] = genres
            
            # Описание - ищем аннотацию
            annotation_elem = soup.find('h2', string='Аннотация')
            if annotation_elem:
                # Ищем следующий элемент после заголовка "Аннотация"
                next_elem = annotation_elem.find_next_sibling()
                if next_elem and next_elem.name != 'br':
                    desc_text = next_elem.get_text(strip=True)
                    if desc_text and desc_text != 'отсутствует':
                        book_info['description'] = desc_text
            
            # Ссылки на скачивание (если авторизованы)
            if self.is_authenticated:
                download_links = []
                
                # Ищем select элемент с форматами файлов
                format_select = soup.find('select', {'id': 'useropt'})
                if format_select:
                    # Получаем все доступные форматы
                    format_options = format_select.find_all('option')
                    base_download_url = f"{self.base_url}/b/{book_id}/"
                    
                    for option in format_options:
                        format_type = option.get('value', '').upper()
                        if format_type:
                            download_url = base_download_url + format_type.lower()
                            download_links.append({
                                'format': format_type,
                                'url': download_url,
                                'text': f"Скачать в формате {format_type}"
                            })
                
                # Если select не найден, ищем обычные ссылки на скачивание
                if not download_links:
                    download_patterns = [
                        r'/download/\w+',  # /download/fb2, /download/epub и т.д.
                        r'/get/\w+',       # /get/fb2, /get/epub и т.д.
                        r'/book/\d+/\w+'   # /book/123/fb2, /book/123/epub и т.д.
                    ]
                    
                    for pattern in download_patterns:
                        download_elems = soup.find_all('a', href=re.compile(pattern))
                        for elem in download_elems:
                            href = elem.get('href', '')
                            text = elem.get_text(strip=True)
                            
                            # Определяем формат по URL или тексту
                            format_match = re.search(r'\.(\w+)$', href) or re.search(r'\.(\w+)$', text)
                            if format_match:
                                format_type = format_match.group(1).upper()
                            else:
                                # Попробуем определить по тексту ссылки
                                if 'fb2' in text.lower() or 'fb2' in href.lower():
                                    format_type = 'FB2'
                                elif 'epub' in text.lower() or 'epub' in href.lower():
                                    format_type = 'EPUB'
                                elif 'mobi' in text.lower() or 'mobi' in href.lower():
                                    format_type = 'MOBI'
                                elif 'pdf' in text.lower() or 'pdf' in href.lower():
                                    format_type = 'PDF'
                                elif 'txt' in text.lower() or 'txt' in href.lower():
                                    format_type = 'TXT'
                                else:
                                    format_type = 'UNKNOWN'
                            
                            download_links.append({
                                'format': format_type,
                                'url': urljoin(self.base_url, href),
                                'text': text
                            })
                
                if download_links:
                    book_info['download_links'] = download_links
            
            # Задержка между запросами
            await asyncio.sleep(1.0)
            return book_info
            
        except Exception as e:
            print(f"❌ Ошибка получения деталей: {e}")
            return None
    
    async def download_book(self, book_id: str, format_type: str = 'epub') -> Optional[bytes]:
        """Скачивает книгу в указанном формате"""
        try:
            print(f"⬇️  Скачивание книги {book_id} в формате {format_type.upper()}")
            
            download_url = f"{self.base_url}/b/{book_id}/{format_type.lower()}"
            
            async with self.session.get(download_url) as response:
                if response.status != 200:
                    print(f"❌ Ошибка скачивания: {response.status}")
                    return None
                
                book_content = await response.read()
                print(f"✅ Книга скачана: {len(book_content)} байт")
                return book_content
                
        except Exception as e:
            print(f"❌ Ошибка скачивания: {e}")
            return None
    
    async def logout(self):
        """Выход из системы"""
        try:
            if self.is_authenticated:
                async with self.session.get(f"{self.base_url}/user/logout") as response:
                    self.is_authenticated = False
                    self.user_id = None
                    print("👋 Выход выполнен успешно")
        except Exception as e:
            print(f"⚠️ Ошибка при выходе: {e}")


async def search_books(query: str, limit: int = 10):
    """Простая функция для поиска книг"""
    async with FlibustaParser() as parser:
        # Авторизация
        if await parser.login():
            print("✅ Авторизация успешна!")
            
            # Поиск книг
            books = await parser.search_books(query, limit)
            
            if books:
                print(f"\n📚 Результаты поиска по запросу '{query}':")
                for i, book in enumerate(books, 1):
                    print(f"\n{i}. {book.get('title', 'Название не найдено')}")
                    if book.get('author'):
                        print(f"   👤 Автор: {book['author']}")
                    if book.get('genres'):
                        print(f"   🏷️  Жанры: {', '.join(book['genres'][:3])}")
                    if book.get('rating'):
                        print(f"   ⭐ Рейтинг: {book['rating']}")
                
                # Получаем детали первой книги
                if books:
                    print(f"\n📖 Детали первой книги:")
                    book_details = await parser.get_book_details(books[0]['book_id'])
                    if book_details:
                        print(json.dumps(book_details, ensure_ascii=False, indent=2))
            else:
                print(f"❌ По запросу '{query}' ничего не найдено")
            
            # Выход
            await parser.logout()
        else:
            print("❌ Авторизация не удалась!")


async def main():
    """Главная функция для тестирования"""
    print("🚀 Парсер Флибуста")
    print("=" * 50)
    
    # Проверяем наличие учетных данных
    if not os.getenv('FLIBUSTA_USERNAME') or not os.getenv('FLIBUSTA_PASSWORD'):
        print("❌ Не указаны учетные данные!")
        print("Создайте файл .env с содержимым:")
        print("FLIBUSTA_USERNAME=ваш_логин")
        print("FLIBUSTA_PASSWORD=ваш_пароль")
        return
    
    # Пример поиска
    await search_books("фантастика", limit=5)


if __name__ == "__main__":
    asyncio.run(main())
