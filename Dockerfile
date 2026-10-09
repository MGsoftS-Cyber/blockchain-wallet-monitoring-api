FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/entrypoint.sh ./entrypoint.sh
RUN useradd --create-home wallet && chown -R wallet:wallet /app
USER wallet
EXPOSE 8000
CMD ["sh", "entrypoint.sh"]
