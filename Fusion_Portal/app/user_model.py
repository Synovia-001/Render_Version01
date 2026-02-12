from dataclasses import dataclass
from flask_login import UserMixin

@dataclass
class User(UserMixin):
    user_id: int
    username: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str = "User"
    is_active: bool = True

    def get_id(self) -> str:
        return str(self.user_id)

    @property
    def display_name(self) -> str:
        name = " ".join([p for p in [self.first_name, self.last_name] if p])
        return name if name.strip() else self.username
