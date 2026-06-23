import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ProjectCreate(BaseModel):
    filename: str

class ProjectResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    original_file_path: str
    original_file_url: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UploadResponse(BaseModel):
    message: str
    project: ProjectResponse
