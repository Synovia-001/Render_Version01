from passlib.context import CryptContext

# Prefer bcrypt_sha256 (no 72-byte password limit) but keep bcrypt for legacy hashes.
pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    # bcrypt_sha256 can handle long passwords safely.
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except ValueError:
        # Defensive: if a legacy bcrypt backend raises due to length, fall back to
        # bcrypt's behavior (first 72 bytes).
        try:
            pw72 = (password or "").encode("utf-8")[:72].decode("utf-8", errors="ignore")
            return pwd_context.verify(pw72, password_hash)
        except Exception:
            return False
