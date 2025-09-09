# Используем официальный образ Python 3.8
FROM python:3.8-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все остальные файлы проекта в рабочую директорию
COPY . .

# Команда для запуска скрипта.
# Мы не используем CMD здесь, так как будем запускать скрипт по расписанию через Cron.
# CMD ["python", "main.py"]
