import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_server: str = ""
    db_database: str = "Fusion_Dashboard"
    db_user: str = ""
    db_password: str = ""
    db_encrypt: str = "yes"
    db_trust_server_certificate: str = "no"
    secret_key: str = "change-me"

    # Module DBs
    core_db: str = ""

def load_settings() -> Settings:
    # Optional INI support (local dev). In production prefer env vars.
    ini_path = os.getenv("FUSION_INI_PATH")
    if not ini_path:
        default_ini = Path(__file__).resolve().parents[1] / "config" / "Fusion_Dashboard.ini"
        if default_ini.exists():
            ini_path = str(default_ini)

    ini_values = {}
    if ini_path and Path(ini_path).exists():
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        if "database" in cfg:
            db = cfg["database"]
            ini_values = {
                "db_driver": db.get("driver", "").strip(),
                "db_server": db.get("server", "").strip(),
                "db_database": db.get("database", "").strip(),
                "db_user": db.get("user", "").strip(),
                "db_password": db.get("password", "").strip(),
                "db_encrypt": db.get("encrypt", "yes").strip(),
                "db_trust_server_certificate": db.get("trust_server_certificate", "no").strip(),
            }

    db_driver = os.getenv("DB_DRIVER") or ini_values.get("db_driver") or "ODBC Driver 18 for SQL Server"
    db_driver = db_driver.strip()
    if db_driver.startswith("{") and db_driver.endswith("}"):
        db_driver = db_driver[1:-1]

    core_db = os.getenv("CORE_DB") or os.getenv("Core_DB") or ""

    return Settings(
        db_driver=db_driver,
        db_server=os.getenv("DB_SERVER") or ini_values.get("db_server",""),
        db_database=os.getenv("DB_DATABASE") or ini_values.get("db_database") or "Fusion_Dashboard",
        db_user=os.getenv("DB_USER") or ini_values.get("db_user",""),
        db_password=os.getenv("DB_PASSWORD") or ini_values.get("db_password",""),
        db_encrypt=os.getenv("DB_ENCRYPT") or ini_values.get("db_encrypt") or "yes",
        db_trust_server_certificate=os.getenv("DB_TRUST_SERVER_CERTIFICATE") or ini_values.get("db_trust_server_certificate") or "no",
        secret_key=os.getenv("SECRET_KEY") or "change-me",
        core_db=core_db,
    )
