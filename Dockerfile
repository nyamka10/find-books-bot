FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем директорию для базы данных
RUN mkdir -p /app/data

# Создаем пользователя для безопасности
RUN useradd --create-home --shell /bin/bash bot && \
    chown -R bot:bot /app
USER bot

# Открываем порт (если понадобится для мониторинга)
EXPOSE 8000

# Команда запуска
CMD ["python", "bot.py"]
