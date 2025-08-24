#!/usr/bin/env python3
"""
Скрипт для миграции базы данных в директорию data/
"""

import os
import shutil
import sqlite3

def migrate_database():
    """Мигрирует базу данных в директорию data/"""
    
    old_db_path = "flibusta_bot.db"
    new_db_path = "data/flibusta_bot.db"
    
    print("🔄 Миграция базы данных...")
    
    # Проверяем, существует ли старая база данных
    if not os.path.exists(old_db_path):
        print("ℹ️ Старая база данных не найдена, пропускаем миграцию")
        return
    
    # Создаем директорию data, если её нет
    os.makedirs("data", exist_ok=True)
    
    # Проверяем, существует ли новая база данных
    if os.path.exists(new_db_path):
        print("⚠️ Новая база данных уже существует")
        response = input("Перезаписать? (y/N): ").lower().strip()
        if response != 'y':
            print("❌ Миграция отменена")
            return
    
    try:
        # Копируем базу данных
        shutil.copy2(old_db_path, new_db_path)
        print(f"✅ База данных успешно скопирована в {new_db_path}")
        
        # Проверяем целостность новой базы данных
        conn = sqlite3.connect(new_db_path)
        cursor = conn.cursor()
        
        # Проверяем основные таблицы
        tables = ['users', 'downloaded_books', 'kindle_sent_books', 'search_history', 'admin_users']
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"📊 Таблица {table}: {count} записей")
            except sqlite3.OperationalError:
                print(f"⚠️ Таблица {table} не найдена")
        
        conn.close()
        
        # Создаем резервную копию старой базы данных
        backup_path = f"{old_db_path}.backup"
        shutil.copy2(old_db_path, backup_path)
        print(f"💾 Создана резервная копия: {backup_path}")
        
        print("🎉 Миграция завершена успешно!")
        print("📝 Теперь можно удалить старую базу данных:")
        print(f"   rm {old_db_path}")
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        return False
    
    return True

if __name__ == "__main__":
    migrate_database()
