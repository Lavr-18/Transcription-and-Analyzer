# Используем официальный образ Python как базовый
FROM python:3.10.12-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /usr/src/app

# Копируем файл зависимостей
COPY requirements.txt ./

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код проекта
COPY . .

# Команда, которая будет выполняться при запуске контейнера
CMD [ "python", "main.py" ]