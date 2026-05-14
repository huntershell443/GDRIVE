#!/usr/bin/env bash
set -e

DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"

echo ">>> Aguardando Postgres em ${DB_HOST}:${DB_PORT}..."
until nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 1
done
echo ">>> Postgres pronto."

echo ">>> Rodando migrations..."
python manage.py migrate --noinput

echo ">>> Coletando estáticos..."
python manage.py collectstatic --noinput || true

echo ">>> Iniciando servidor na porta 8787..."
exec python server.py
