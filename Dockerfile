# Используем официальный образ Python 3.11 slim
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект в контейнер
COPY . .

# Создаем папку для буфера, если её нет
RUN mkdir -p buffer_images

# Открываем порт (при необходимости)
EXPOSE 8000

# Команда запуска бота
CMD ["python", "bot.py"]
