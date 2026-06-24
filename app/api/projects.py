import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.models.project import Project
from app.models.user import User
from app.schemas.project import UploadResponse, ProjectResponse, ProjectStatusResponse
from app.services import audio_service
from app.services import file_service
from app.utils.file_utils import FileValidationError

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


@router.get("", response_model=List[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    return db.query(Project).filter(
        Project.user_id == current_user.id,
    ).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    return _get_owned_project(db, project_id, current_user)


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
def get_project_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    project = _get_owned_project(db, project_id, current_user)
    return ProjectStatusResponse(
        project_id=project.id,
        status=project.status,
        vocals_url=project.vocals_url,
        instrumental_url=project.instrumental_url,
    )


@router.post("/{project_id}/process", response_model=ProjectResponse)
def process_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    project = _get_owned_project(db, project_id, current_user)
    if project.status.lower() == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is already processing",
        )

    try:
        return audio_service.process_project(db, project_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process project: {str(e)}",
        )


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_project_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Upload a media file (MP3, WAV, MP4, MOV, AVI) under the authenticated user's account.
    Performs file size, extension, and MIME type validation.
    """
    try:
        project = file_service.upload_file(db, file, current_user.id)
        return UploadResponse(
            message="File uploaded successfully",
            project=ProjectResponse.model_validate(project)
        )
    except FileValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process file upload: {str(e)}"
        )