import os
from pathlib import Path
import configparser

DEFAULT_INI_PATHS = [
    Path(r"D:\Configuration\render.ini"),            # your Windows path
    Path(__file__).resolve().parent / "render.ini",  # optional local file beside code
]

def _read_ini_any_section(ini_path: Path) -> dict:
    """
    Supports these INI styles:

    Style A (no section header):
        DB_SERVER = ...
        DB_NAME = ...

    Style B (any section name):
        [database]
        DB_SERVER = ...

        OR

        [render]
        DB_SERVER = ...

    Returns a dict of keys->values from the chosen section.
    """
    cp = configparser.ConfigParser()

    txt = ini_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not txt:
        return {}

    # If no section header, wrap it in a default section
    if not txt.lstrip().startswith("["):
        txt = "[database]\n" + txt

    cp.read_string(txt)

    # Prefer these section names if present
    for sec in ["database", "render", "default"]:
        if cp.has_section(sec):
            section = sec
            break
    else:
        # Fallback to first section
        section = cp.sections()[0] if cp.sections() else None

    if not section:
        return {}

    out = {}
    for k, v in cp.items(section):
        out[k.upper()] = v.strip()

    return out


def load_settings() -> dict:
    """
    Priority:
      1) Environment variables (Render best practice)
      2) INI file at D:\\Configuration\\render.ini (local dev)
      3) INI file beside code (optional)

    Returns keys:
      DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD
      REPORT_MONTH (optional)
      ODBC_DRIVER (optional)
    """
    settings = {
        "DB_SERVER": os.getenv("DB_SERVER", "").strip(),
        "DB_NAME": os.getenv("DB_NAME", "").strip(),
        "DB_USER": os.getenv("DB_USER", "").strip(),
        "DB_PASSWORD": os.getenv("DB_PASSWORD", "").strip(),
        "REPORT_MONTH": os.getenv("REPORT_MONTH", "").strip(),   # optional now (we'll pick latest month)
        "ODBC_DRIVER": os.getenv("ODBC_DRIVER", "").strip(),     # optional
    }

    # If required env vars set, done
    if all(settings[k] for k in ["DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD"]):
        return settings

    ini_path = None
    for p in DEFAULT_INI_PATHS:
        if p.exists():
            ini_path = p
            break

    if not ini_path:
        return settings

    ini_vals = _read_ini_any_section(ini_path)

    # Fill missing values only
    for k in ["DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD", "REPORT_MONTH", "ODBC_DRIVER"]:
        if not settings.get(k):
            settings[k] = ini_vals.get(k, settings.get(k, ""))

    return settings