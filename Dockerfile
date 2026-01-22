# Dockerfile для ACH (Adversarial Code Hardening)
# 
# Безопасность:
# - Непривилегированный пользователь
# - Минимальный образ
# - Нет лишних пакетов

FROM python:3.11-slim

# Метаданные
LABEL maintainer="ACH Project"
LABEL description="Adversarial Code Hardening - безопасная песочница"

# Создаём непривилегированного пользователя
RUN useradd -m -s /bin/bash -u 1000 runner

# Рабочая директория
WORKDIR /app

# Зависимости (отдельный слой для кэширования)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

# Копируем код
COPY --chown=runner:runner . .

# Создаём директорию для результатов
RUN mkdir -p /app/results && chown runner:runner /app/results

# Переключаемся на непривилегированного пользователя
USER runner

# Проверка что всё работает
RUN python -c "from src.config import Config; print('✅ Config OK')"

# Точка входа
ENTRYPOINT ["python"]
CMD ["examples/json_parser/manual_loop.py"]
