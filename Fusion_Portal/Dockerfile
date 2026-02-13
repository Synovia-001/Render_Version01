# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1         PYTHONUNBUFFERED=1

WORKDIR /app

# unixODBC + build deps for pyodbc + kerberos lib for slim images
RUN apt-get update && apt-get install -y --no-install-recommends         curl ca-certificates gnupg         unixodbc unixodbc-dev         gcc g++         libgssapi-krb5-2      && rm -rf /var/lib/apt/lists/*

# Microsoft ODBC Driver 18 (Debian 12 / bookworm) - no apt-key
RUN set -eux;         curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb;         dpkg -i packages-microsoft-prod.deb;         rm packages-microsoft-prod.deb;         apt-get update;         ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18;         rm -rf /var/lib/apt/lists/*;         odbcinst -q -d -n "ODBC Driver 18 for SQL Server"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Quick sanity check at build time
RUN python -c "import pyodbc; print('ODBC drivers:', pyodbc.drivers())"

CMD ["sh", "-c", "gunicorn wsgi:server --workers ${WEB_CONCURRENCY:-2} --threads 4 --bind 0.0.0.0:${PORT:-10000} --timeout 120"]
