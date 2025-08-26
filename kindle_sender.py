#!/usr/bin/env python3
"""
Модуль для отправки книг на Kindle по email
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email import encoders
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class KindleSender:
    """Отправляет книги на Kindle по email"""
    
    def __init__(self):
        # Настройки SMTP (Gmail)
        self.smtp_server = "smtp.gmail.com"
        self.port = 465  # SSL
        self.login = os.getenv('GMAIL_LOGIN')
        self.password = os.getenv('GMAIL_PASSWORD')
        
        # Email для Kindle (из переменных окружения)
        self.kindle_email = os.getenv('KINDLE_EMAIL')
        
        # Проверяем настройки
        if not self.login or not self.password:
            raise ValueError("Не указаны учетные данные Gmail в .env файле")
        if not self.kindle_email:
            raise ValueError("Не указан email для Kindle в .env файле")
    
    def send_book_to_kindle(self, book_content: bytes, book_title: str, author: str = None, user_kindle_email: str = None) -> bool:
        """Отправляет книгу на Kindle"""
        try:
            # Используем email пользователя, если передан, иначе используем глобальный
            target_email = user_kindle_email if user_kindle_email else self.kindle_email
            print(f"📧 Отправка книги '{book_title}' на Kindle...")
            print(f"📧 Email получателя: {target_email}")
            
            # Создаем письмо
            msg = MIMEMultipart()
            msg["Subject"] = f"Книга: {book_title}"
            msg["From"] = self.login
            msg["To"] = target_email
            
            # Очищаем название книги для отображения
            clean_title = book_title.replace('"', '').replace("'", "").strip()
            
            # Текст письма
            body = f"""
            Привет! 
            
            Отправляю книгу: {clean_title}
            """
            if author:
                body += f"Автор: {author}\n"
            
            body += "\nКнига прикреплена к письму в формате EPUB."
            
            msg.attach(MIMEText(body, "plain", "utf-8"))
            
            # Имя файла - исправляем проблемы с кодировкой
            safe_title = self._sanitize_filename(book_title)
            filename = f"{safe_title}.epub"
            
            # Прикрепляем файл книги
            # Используем MIMEApplication для лучшей совместимости
            attachment = MIMEApplication(book_content, _subtype='epub')
            attachment.add_header('Content-Disposition', 'attachment', filename=filename)
            
            # Отладка (раскомментируйте если нужно)
            # print(f"📁 Имя файла: {filename}")
            
            # Отладочная информация
            print(f"🔍 Отладочная информация:")
            print(f"   📁 Имя файла: {filename}")
            print(f"   📧 Content-Disposition: attachment; filename=\"{filename}\"")
            
            msg.attach(attachment)
            
            # Отправляем письмо
            with smtplib.SMTP_SSL(self.smtp_server, self.port) as server:
                server.login(self.login, self.password)
                server.sendmail(msg["From"], [target_email], msg.as_string())
            
            print(f"✅ Книга '{book_title}' успешно отправлена на Kindle!")
            print(f"📧 Email: {target_email}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка отправки на Kindle: {e}")
            return False
    
    def _sanitize_filename(self, filename: str) -> str:
        """Очищает имя файла от недопустимых символов"""
        import re
        
        # Убираем кавычки и лишние символы
        filename = re.sub(r'["\']', '', filename)
        
        # Заменяем пробелы на подчеркивания
        filename = filename.replace(' ', '_')
        
        # Убираем все символы кроме букв, цифр, подчеркиваний и дефисов
        filename = re.sub(r'[^\w\-_]', '', filename)
        
        # Ограничиваем длину имени файла
        if len(filename) > 50:
            filename = filename[:50]
        
        # Убираем лишние подчеркивания
        filename = re.sub(r'_+', '_', filename)
        filename = filename.strip('_')
        
        # Если имя файла пустое, используем fallback
        if not filename:
            filename = "book"
        
        # Дополнительная проверка - если имя содержит не-ASCII символы, транслитерируем
        try:
            filename.encode('ascii')
        except UnicodeEncodeError:
            # Транслитерация русских букв
            translit_map = {
                'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
                'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
                'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
                'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
                'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
            }
            
            for cyr, lat in translit_map.items():
                filename = filename.replace(cyr, lat)
                filename = filename.replace(cyr.upper(), lat.upper())
        
        return filename
    
    def test_connection(self) -> bool:
        """Тестирует подключение к SMTP серверу"""
        try:
            print("🔍 Тестирование подключения к Gmail...")
            with smtplib.SMTP_SSL(self.smtp_server, self.port) as server:
                server.login(self.login, self.password)
            print("✅ Подключение к Gmail успешно!")
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к Gmail: {e}")
            return False


async def send_book_to_kindle_async(book_content: bytes, book_title: str, author: str = None, user_kindle_email: str = None) -> bool:
    """Асинхронная обертка для отправки книги на Kindle"""
    import asyncio
    
    def _send():
        sender = KindleSender()
        return sender.send_book_to_kindle(book_content, book_title, author, user_kindle_email)
    
    # Запускаем в отдельном потоке, чтобы не блокировать asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send)
