import os
from urllib.parse import quote_plus
from typing import Any, Optional

from pydantic import BaseModel, Field
from dotenv import find_dotenv, load_dotenv

# Load .env file if present
load_dotenv(find_dotenv())


class Settings(BaseModel):
    PROJECT_NAME: str = "Aurafy"
    API_V1_STR: str = "/api/v1"

    # JWT Authentication Settings
    SECRET_KEY: str = Field(
        default_factory=lambda: os.getenv(
            "SECRET_KEY",
            "supersecretjwtkeyforaurafyphase1and2localdevelopmentonly"
        )
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default_factory=lambda: int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "11520")
        )
    )

    # PostgreSQL Settings
    POSTGRES_SERVER: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_SERVER", "localhost")
    )
    POSTGRES_USER: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_USER", "postgres")
    )
    POSTGRES_PASSWORD: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "postgres")
    )
    POSTGRES_DB: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_DB", "aurafy")
    )
    POSTGRES_PORT: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_PORT", "5432")
    )

    SQLALCHEMY_DATABASE_URI: Optional[str] = None

    model_config = {
        "arbitrary_types_allowed": True
    }

    def __init__(self, **data: Any):
        super().__init__(**data)

        db_url = os.getenv("DATABASE_URL")

        if db_url:
            self.SQLALCHEMY_DATABASE_URI = db_url
        else:
            encoded_password = quote_plus(self.POSTGRES_PASSWORD)

            self.SQLALCHEMY_DATABASE_URI = (
                f"postgresql://{self.POSTGRES_USER}:{encoded_password}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )


settings = Settings()