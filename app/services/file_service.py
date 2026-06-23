import uuid
from pathlib import Path
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import UploadFile

from app.models.project import Project
from app.utils.file_utils import save_uploaded_file, delete_physical_file
from app.core.config import settings

# Resolve project paths using configuration settings
UPLOADS_DIR = Path(settings.UPLOAD_DIR)
TEMP_DIR = Path(settings.TEMP_DIR)
PROCESSED_DIR = Path(settings.STORAGE_ROOT) / "processed"


def upload_file(db: Session, file: UploadFile, user_id: uuid.UUID) -> Project:
    """
    Validates, saves the physical file to disk, and registers a Project record in the database.
    If the database operation fails, it cleans up the stored file to avoid orphans.
    """
    # 1. Save physically to storage/uploads/ (validates file size/extension/MIME type)
    saved_path = save_uploaded_file(file, UPLOADS_DIR)
    
    # 2. Construct the virtual url for the file (e.g. static endpoint reference)
    original_file_url = f"/api/v1/projects/file/{saved_path.name}"
    
    # 3. Create database entry
    db_project = Project(
        user_id=user_id,
        filename=file.filename,
        original_file_path=str(saved_path),
        original_file_url=original_file_url,
        status="UPLOADED"
    )
    
    try:
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        return db_project
    except Exception as e:
        # DB rollback and delete physical file on database errors
        db.rollback()
        delete_physical_file(saved_path)
        raise e

def delete_file(db: Session, project_id: uuid.UUID) -> bool:
    """
    Deletes the project record from the database and removes its associated file from storage.
    """
    stmt = select(Project).where(Project.id == project_id)
    project = db.execute(stmt).scalar_one_or_none()
    if not project:
        return False
        
    # Delete physically
    file_path = Path(project.original_file_path)
    delete_physical_file(file_path)
    
    # Delete record
    db.delete(project)
    db.commit()
    return True

def get_file_path(project: Project) -> Path:
    """
    Get the absolute Path object for the project's original file.
    """
    return Path(project.original_file_path)
