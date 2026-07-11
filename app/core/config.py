import glob
import logging
import os
from urllib.parse import quote_plus
from typing import Any, Optional

from pydantic import BaseModel, Field
from dotenv import find_dotenv, load_dotenv

# Load .env file if present
load_dotenv(find_dotenv())

logger = logging.getLogger(__name__)

def _has_ffmpeg_shared_libs(ffmpeg_bin: str) -> bool:
    patterns = [
        "avutil-*.dll",
        "avcodec-*.dll",
        "avformat-*.dll",
        "avfilter-*.dll",
        "swscale-*.dll",
        "swresample-*.dll",
    ]
    return all(bool(glob.glob(os.path.join(ffmpeg_bin, pattern))) for pattern in patterns)


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

    STORAGE_ROOT: str = ""
    UPLOAD_DIR: str = ""
    TEMP_DIR: str = ""
    VOCALS_DIR: str = ""
    INSTRUMENTAL_DIR: str = ""

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

        # Initialize storage directories
        if not self.STORAGE_ROOT:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.STORAGE_ROOT = os.getenv("STORAGE_ROOT", os.path.join(base_dir, "storage"))

        self.STORAGE_ROOT = os.path.abspath(self.STORAGE_ROOT)
        self.UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", os.path.join(self.STORAGE_ROOT, "uploads")))
        self.TEMP_DIR = os.path.abspath(os.getenv("TEMP_DIR", os.path.join(self.STORAGE_ROOT, "temp")))

        processed_dir = os.path.join(self.STORAGE_ROOT, "processed")
        self.VOCALS_DIR = os.path.abspath(os.getenv("VOCALS_DIR", os.path.join(processed_dir, "vocals")))
        self.INSTRUMENTAL_DIR = os.path.abspath(os.getenv("INSTRUMENTAL_DIR", os.path.join(processed_dir, "instrumental")))

        # Ensure directories exist
        os.makedirs(self.STORAGE_ROOT, exist_ok=True)
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
        os.makedirs(self.TEMP_DIR, exist_ok=True)
        os.makedirs(self.VOCALS_DIR, exist_ok=True)
        os.makedirs(self.INSTRUMENTAL_DIR, exist_ok=True)

        # Ensure FFmpeg bin directory is in PATH
        ffmpeg_bin = os.getenv("FFMPEG_BIN", r"C:\ffmpeg\ffmpeg-8.1.1-essentials_build\bin")
        if os.path.exists(ffmpeg_bin) and ffmpeg_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_bin + os.pathsep + os.environ.get("PATH", "")

        if os.path.exists(ffmpeg_bin):
            ffmpeg_exe = os.path.join(ffmpeg_bin, "ffmpeg.exe")
            ffprobe_exe = os.path.join(ffmpeg_bin, "ffprobe.exe")
            if not os.path.exists(ffmpeg_exe) or not os.path.exists(ffprobe_exe):
                logger.warning(
                    "FFmpeg bin path %s does not contain ffmpeg.exe or ffprobe.exe. "
                    "Make sure FFmpeg is installed and FFMPEG_BIN points to the correct shared build.",
                    ffmpeg_bin,
                )
            if not _has_ffmpeg_shared_libs(ffmpeg_bin):
                logger.warning(
                    "FFmpeg bin path %s does not appear to contain shared FFmpeg DLLs. "
                    "TorchCodec requires a full-shared FFmpeg build on Windows (e.g. avutil-*.dll, avcodec-*.dll, avformat-*.dll).",
                    ffmpeg_bin,
                )


settings = Settings()