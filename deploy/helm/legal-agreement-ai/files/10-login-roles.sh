#!/bin/sh
# Local stack only: create the login roles the app and worker use (least privilege; they own nothing).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
create role app_login login password '${APP_DB_PASSWORD}';
create role worker_login login password '${WORKER_DB_PASSWORD}';
SQL
