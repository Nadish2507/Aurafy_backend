import logging
import uuid
from typing import Any, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_active_user
from app.models.project import Project
from app.models.user import User
from app.schemas.project import UploadResponse, ProjectResponse, ProjectStatusResponse
from app.services import audio_service
from app.services import file_service
from app.utils.file_utils import FileValidationError

router = APIRouter()
logger = logging.getLogger(__name__)


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


def _get_project_for_processing(
    db: Session,
    project_id: uuid.UUID,
    current_user: User,
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project",
        )
    return project


def _run_process_project_background(project_id: uuid.UUID, job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        audio_service.process_project(db, project_id, job_id)
    except Exception:
        logger.exception(
            "Background processing failed for project_id=%s job_id=%s",
            project_id,
            job_id,
        )
    finally:
        db.close()


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


@router.post(
    "/{project_id}/process",
    response_model=ProjectResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_project(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    project = _get_project_for_processing(db, project_id, current_user)
    project_status = audio_service.normalize_status(project.status)

    if not audio_service.can_start_processing(project):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project cannot be processed from status {project_status}",
        )

    try:
        job = audio_service.create_pending_job(db, project)
        background_tasks.add_task(_run_process_project_background, project.id, job.id)
        logger.info(
            "Processing queued for project_id=%s user_id=%s job_id=%s",
            project.id,
            current_user.id,
            job.id,
        )
        return project
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to queue processing for project_id=%s user_id=%s",
            project_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start project processing",
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
    except Exception:
        logger.exception("Upload failed for user_id=%s filename=%s", current_user.id, file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process file upload"
        )
