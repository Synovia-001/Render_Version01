import bcrypt
import hashlib

def _pw_bytes(password: str) -> bytes:
    b = password.encode("utf-8")
    # bcrypt algorithm limit; bcrypt 5 raises ValueError if >72 bytes
    if len(b) > 72:
        b = hashlib.sha256(b).digest()
    return b

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(_pw_bytes(password), salt).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False
