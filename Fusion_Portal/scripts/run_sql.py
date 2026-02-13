import argparse
import os
import re
from pathlib import Path

import pyodbc

def load_conn_str() -> str:
    driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE", "Fusion_Dashboard")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    encrypt = os.getenv("DB_ENCRYPT", "yes")
    trust = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "no")

    ini_path = os.getenv("FUSION_INI_PATH")
    if not ini_path:
        default_ini = Path(__file__).resolve().parents[1] / "config" / "Fusion_Dashboard.ini"
        if default_ini.exists():
            ini_path = str(default_ini)

    if ini_path and Path(ini_path).exists():
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        db = cfg["database"]
        driver = db.get("driver", driver)
        server = db.get("server", server)
        database = db.get("database", database)
        user = db.get("user", user)
        password = db.get("password", password)
        encrypt = db.get("encrypt", encrypt)
        trust = db.get("trust_server_certificate", trust)

        driver = driver.strip()
        if driver.startswith("{") and driver.endswith("}"):
            driver = driver[1:-1]

    missing = [k for k, v in {"DB_SERVER": server, "DB_USER": user, "DB_PASSWORD": password}.items() if not v]
    if missing:
        raise SystemExit(f"Missing required DB settings: {', '.join(missing)}")

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust};"
        "Connection Timeout=30;"
    )

def split_batches(sql_text: str):
    pattern = re.compile(r"^\s*GO\s*$", flags=re.IGNORECASE | re.MULTILINE)
    return [p.strip() for p in pattern.split(sql_text) if p.strip()]

def main():
    ap = argparse.ArgumentParser(description="Run a SQL Server .sql file, splitting on GO statements.")
    ap.add_argument("sql_file", help="Path to .sql file")
    args = ap.parse_args()

    sql_path = Path(args.sql_file)
    if not sql_path.exists():
        raise SystemExit(f"SQL file not found: {sql_path}")

    batches = split_batches(sql_path.read_text(encoding="utf-8"))
    if not batches:
        raise SystemExit("No SQL batches found.")

    conn_str = load_conn_str()
    with pyodbc.connect(conn_str, autocommit=True) as conn:
        cur = conn.cursor()
        for i, batch in enumerate(batches, start=1):
            print(f"Running batch {i}/{len(batches)}...")
            cur.execute(batch)
        cur.close()
    print("Done.")

if __name__ == "__main__":
    main()
