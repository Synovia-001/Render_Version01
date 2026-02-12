from getpass import getpass
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

pw = getpass("Password: ")
print(pwd_context.hash(pw))
