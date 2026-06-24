import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.models.project import Project
from app.models.user import User

router = APIRouter()


def _get_owned_project(
    db: Session,
    project_id: uuid.UUID,
    current_user: User,
) -> Project:
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user.id,
    ).first()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


def _download_processed_file(
    db: Session,
    project_id: uuid.UUID,
    current_user: User,
    output_dir: str,
    filename_prefix: str,
) -> FileResponse:
    _get_owned_project(db, project_id, current_user)

    file_path = Path(output_dir) / f"{project_id}.wav"
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found",
        )

    return FileResponse(
        path=file_path,
        media_type="audio/wav",
        filename=f"{filename_prefix}_{project_id}.wav",
    )


@router.get("/vocals/{project_id}")
def download_vocals(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    return _download_processed_file(
        db=db,
        project_id=project_id,
        current_user=current_user,
        output_dir=settings.VOCALS_DIR,
        filename_prefix="vocals",
    )


@router.get("/instrumental/{project_id}")
def download_instrumental(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    return _download_processed_file(
        db=db,
        project_id=project_id,
        current_user=current_user,
        output_dir=settings.INSTRUMENTAL_DIR,
        filename_prefix="instrumental",
    )