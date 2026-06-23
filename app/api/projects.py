from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from typing import Any

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.models.user import User
from app.schemas.project import UploadResponse, ProjectResponse
from app.services import file_service
from app.utils.file_utils import FileValidationError

router = APIRouter()

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
