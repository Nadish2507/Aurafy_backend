import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin
from app.core.security import get_password_hash, verify_password

class EmailAlreadyExistsError(Exception):
    """Exception raised when an email is already registered."""
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Email '{email}' is already registered.")

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Retrieve a user by their email using SQLAlchemy 2.0 syntax."""
    stmt = select(User).where(User.email == email)
    return db.execute(stmt).scalar_one_or_none()

def get_user_by_id(db: Session, user_id: uuid.UUID) -> Optional[User]:
    """Retrieve a user by their ID using SQLAlchemy 2.0 syntax."""
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()

def register_user(db: Session, user_in: UserCreate) -> User:
    """Register a new user, performing email uniqueness validation."""
    existing_user = get_user_by_email(db, user_in.email)
    if existing_user:
        raise EmailAlreadyExistsError(user_in.email)
    
    hashed_password = get_password_hash(user_in.password)
    db_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        is_active=True
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, user_login: UserLogin) -> Optional[User]:
    """Authenticate a user by email and password."""
    user = get_user_by_email(db, user_login.email)
    if not user:
        return None
    if not verify_password(user_login.password, user.hashed_password):
        return None
    return user
