FROM python:3.11-slim-bookworm

WORKDIR /app

# System deps for pyodbc + msodbcsql17
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg apt-transport-https \
        unixodbc unixodbc-dev gcc g++ && \
    # Configure Microsoft repo (Debian 12 / bookworm)
    curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    rm packages-microsoft-prod.deb && \
    apt-get update && \
    # Install ODBC 17 + kerberos lib (needed on slim images)
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql17 libgssapi-krb5-2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "gunicorn wsgi:server --workers 2 --threads 4 --bind 0.0.0.0:${PORT:-8050} --timeout 120"]
