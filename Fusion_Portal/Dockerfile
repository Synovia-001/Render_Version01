FROM python:3.11-slim

WORKDIR /app

# System deps for pyodbc + msodbcsql17
RUN apt-get update &&         apt-get install -y --no-install-recommends curl gnupg apt-transport-https ca-certificates unixodbc unixodbc-dev gcc g++ &&         curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - &&         curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list &&         apt-get update &&         ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 &&         apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render provides PORT. Default to 8050 for local Docker.
CMD ["sh", "-c", "gunicorn wsgi:server --workers 2 --threads 4 --bind 0.0.0.0:${PORT:-8050} --timeout 120"]
