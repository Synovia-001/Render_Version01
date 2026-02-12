# syntax=docker/dockerfile:1
FROM python:3.12-slim

# 1) OS deps for pyodbc + unixODBC
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg apt-transport-https \
    unixodbc unixodbc-dev \
    gcc g++ \
 && rm -rf /var/lib/apt/lists/*

# 2) Install Microsoft ODBC Driver 18 (msodbcsql18) on Debian 12 (bookworm)
RUN set -eux; \
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg; \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list; \
    apt-get update; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app code
COPY . .

# Render provides $PORT. Web services must bind to 0.0.0.0.
CMD gunicorn app:server --bind 0.0.0.0:$PORT
