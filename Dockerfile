# 1. Берём официальный образ Python
FROM python:3.11-slim

# 2. Устанавливаем рабочую директорию
WORKDIR /app

# 3. Копируем зависимости и устанавливаем их
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Копируем всю серверную часть
COPY backend/ ./

# 5. Подготавливаем директорию для миграций/инициализации БД (по желанию)
#    Здесь при старте контейнера можно запустить init_db.py
#    но в docker-compose ниже я покажу, как это делать отдельно.

# 6. Открываем порт, который слушает uvicorn
EXPOSE 8000

# 7. Точка входа
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
