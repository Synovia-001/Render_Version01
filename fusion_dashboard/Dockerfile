# syntax=docker/dockerfile:1
FROM python:3.12-slim

# unixODBC + build deps for pyodbc
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg apt-transport-https \
    unixodbc unixodbc-dev \
    gcc g++ \
 && rm -rf /var/lib/apt/lists/*

# Microsoft ODBC Driver 18 (Debian 12 / bookworm)
RUN set -eux; \
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg; \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list; \
    apt-get update; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD gunicorn app:server --bind 0.0.0.0:$PORT
