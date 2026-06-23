import os
import re
import uuid
from pathlib import Path
from typing import Set
from fastapi import UploadFile

ALLOWED_EXTENSIONS: Set[str] = {".mp3", ".wav", ".mp4", ".mov", ".avi"}

ALLOWED_MIME_TYPES: Set[str] = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/avi",
    "video/msvideo"
}

# 500 MB in bytes
MAX_FILE_SIZE = 500 * 1024 * 1024

class FileValidationError(Exception):
    """Base exception for file validation errors."""
    pass

class FileSizeLimitExceededError(FileValidationError):
    """Exception raised when file size exceeds the allowed limit."""
    def __init__(self, max_size_mb: int = 500):
        super().__init__(f"File size exceeds the maximum limit of {max_size_mb}MB.")

class UnsupportedFileExtensionError(FileValidationError):
    """Exception raised when file extension is not supported."""
    def __init__(self, extension: str):
        super().__init__(f"File extension '{extension}' is not supported.")

class UnsupportedMimeTypeError(FileValidationError):
    """Exception raised when MIME type is not supported."""
    def __init__(self, mime_type: str):
        super().__init__(f"MIME type '{mime_type}' is not supported.")

def sanitize_filename(filename: str) -> str:
    """
    Sanitize the filename by removing path traversal components
    and replacing unsafe characters.
    """
    # Isolate filename from any directory components (prevent path traversal)
    base_name = Path(filename).name
    # Replace non-alphanumeric characters (except dots, underscores, hyphens) with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', base_name)
    # Prevent empty or dangerous names
    if not sanitized or sanitized in (".", ".."):
        sanitized = "uploaded_file"
    return sanitized

def generate_unique_filename(filename: str) -> str:
    """
    Generate a unique, sanitized filename.
    """
    sanitized = sanitize_filename(filename)
    path = Path(sanitized)
    stem = path.stem
    suffix = path.suffix.lower()
    unique_id = uuid.uuid4().hex
    return f"{stem}_{unique_id}{suffix}"

def validate_file_metadata(filename: str, content_type: str) -> None:
    """
    Validate the file's extension and MIME type before reading content.
    """
    # Safeguard against empty names
    if not filename:
        raise UnsupportedFileExtensionError("")
    
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileExtensionError(suffix)
    
    # Safe check for None content-type
    mime = (content_type or "").lower().strip()
    if mime not in ALLOWED_MIME_TYPES:
        raise UnsupportedMimeTypeError(content_type)

def save_uploaded_file(file: UploadFile, destination_dir: Path) -> Path:
    """
    Save the uploaded file to the destination directory.
    Validates the extension/MIME type, and monitors the size during write.
    """
    # 1. Validate extension and mime type
    validate_file_metadata(file.filename, file.content_type)
    
    # 2. Ensure destination exists
    destination_dir.mkdir(parents=True, exist_ok=True)
    
    # 3. Generate secure, unique filename
    unique_name = generate_unique_filename(file.filename)
    destination_path = destination_dir / unique_name
    
    # Check if size is already available and exceeds limit
    if file.size and file.size > MAX_FILE_SIZE:
        raise FileSizeLimitExceededError()
        
    # 4. Save in chunks and monitor size
    total_bytes = 0
    chunk_size = 1024 * 1024  # 1MB
    
    try:
        # Reset file cursor just in case it was read elsewhere
        file.file.seek(0)
        with open(destination_path, "wb") as buffer:
            while True:
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE:
                    raise FileSizeLimitExceededError()
                buffer.write(chunk)
    except Exception as e:
        # Clean up partial file on failure
        if destination_path.exists():
            destination_path.unlink()
        raise e
        
    return destination_path

def delete_physical_file(filepath: Path) -> bool:
    """
    Delete a file from disk if it exists.
    """
    try:
        path = Path(filepath)
        if path.exists() and path.is_file():
            path.unlink()
            return True
    except Exception:
        pass
    return False
