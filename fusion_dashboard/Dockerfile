# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# OS deps for pyodbc + unixODBC + Microsoft driver
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    unixodbc unixodbc-dev \
    gcc g++ \
    libgssapi-krb5-2 \
 && rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver 18 using Microsoft-supported repo bootstrap (no apt-key)
RUN set -eux; \
    curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb; \
    dpkg -i packages-microsoft-prod.deb; \
    rm packages-microsoft-prod.deb; \
    apt-get update; \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
    rm -rf /var/lib/apt/lists/*; \
    odbcinst -q -d -n "ODBC Driver 18 for SQL Server"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: build-time sanity check that pyodbc can see the driver
RUN python -c "import pyodbc; print('ODBC drivers:', pyodbc.drivers())"

COPY . .

# Render provides PORT (default 10000). Bind to it or Render can’t route traffic.
CMD ["sh", "-c", "gunicorn app:server --workers 2 --threads 4 --bind 0.0.0.0:${PORT:-10000} --timeout 120"]
