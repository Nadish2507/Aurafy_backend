from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.services import auth_service
from app.services.auth_service import EmailAlreadyExistsError

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: Session = Depends(get_db)
) -> Any:
    """
    Register a new user account.
    """
    try:
        user = auth_service.register_user(db, user_in)
        return user
    except EmailAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

@router.post("/login", response_model=Token)
async def login(
    user_in: UserLogin,
    db: Session = Depends(get_db)
) -> Any:
    """
    Authenticate user and return JWT access token.
    """
    user = auth_service.authenticate_user(db, user_in)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    access_token = create_access_token(subject=user.email)
    return Token(
        access_token=access_token,
        token_type="bearer"
    )

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get current authenticated user.
    """
    return current_user
