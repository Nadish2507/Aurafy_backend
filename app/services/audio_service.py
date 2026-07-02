import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy.orm import Session
import demucs.separate

from app.core.config import settings
from app.models.project import Project
from app.models.job import Job
from app.utils import audio_utils

logger = logging.getLogger(__name__)

PROCESSABLE_STATUSES = {"UPLOADED"}
ACTIVE_STATUSES = {"PENDING", "PROCESSING"}
TERMINAL_STATUSES = {"COMPLETED", "FAILED"}


def normalize_status(project_status: str) -> str:
    return project_status.upper()


def can_start_processing(project: Project) -> bool:
    return normalize_status(project.status) in PROCESSABLE_STATUSES


def create_pending_job(db: Session, project: Project) -> Job:
    now = datetime.now(timezone.utc)
    job = Job(
        user_id=project.user_id,
        status="PENDING",
        original_filename=project.filename,
        original_filepath=project.original_file_path,
        created_at=now,
        updated_at=now,
    )
    project.status = "PENDING"
    db.add(job)
    db.commit()
    db.refresh(job)
    db.refresh(project)
    return job


def separate_audio(wav_path: Path, project_id: uuid.UUID) -> Tuple[Path, Path]:
    """
    Runs Demucs separation on the provided WAV file.
    Saves the output to the processed vocals and instrumental directories with the project ID as filename.
    Returns (vocals_path, instrumental_path).
    """
    logger.info("Demucs started for project_id=%s", project_id)

    temp_demucs_dir = Path(settings.TEMP_DIR) / f"demucs_{project_id}"
    temp_demucs_dir.mkdir(parents=True, exist_ok=True)

    try:
        opts = [
            "-n", "htdemucs",
            "--two-stems", "vocals",
            "-o", str(temp_demucs_dir),
            str(wav_path),
        ]

        logger.info("Running Demucs for project_id=%s with opts=%s", project_id, opts)
        demucs.separate.main(opts)

        track_name = wav_path.stem
        vocals_source = temp_demucs_dir / "htdemucs" / track_name / "vocals.wav"
        instrumental_source = temp_demucs_dir / "htdemucs" / track_name / "no_vocals.wav"

        if not vocals_source.exists() or not instrumental_source.exists():
            raise RuntimeError("Demucs failed to generate output files.")

        vocals_dest = Path(settings.VOCALS_DIR) / f"{project_id}.wav"
        instrumental_dest = Path(settings.INSTRUMENTAL_DIR) / f"{project_id}.wav"

        vocals_dest.parent.mkdir(parents=True, exist_ok=True)
        instrumental_dest.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy(vocals_source, vocals_dest)
        shutil.copy(instrumental_source, instrumental_dest)

        logger.info("Demucs completed for project_id=%s", project_id)
        return vocals_dest, instrumental_dest

    except Exception as e:
        logger.exception("Demucs failed for project_id=%s", project_id)
        raise RuntimeError(f"Demucs separation failed: {str(e)}")
    finally:
        if temp_demucs_dir.exists():
            shutil.rmtree(temp_demucs_dir, ignore_errors=True)


def process_project(db: Session, project_id: uuid.UUID, job_id: uuid.UUID | None = None) -> Project:
    """
    Main audio processing pipeline workflow.
    1. Validate uploaded file
    2. Detect audio/video
    3. Extract audio if video
    4. Convert audio to WAV
    5. Run Demucs separation
    6. Generate vocals.wav and instrumental.wav
    7. Save output files
    8. Update database records
    9. Update job status
    """
    logger.info("Processing started for project_id=%s", project_id)

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found.")

    logger.info(
        "Upload started for project_id=%s user_id=%s original_file_path=%s",
        project_id,
        project.user_id,
        project.original_file_path,
    )

    if job_id is None:
        job = create_pending_job(db, project)
    else:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found.")
    job_id = job.id

    job.status = "PROCESSING"
    job.started_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)

    project.status = "PROCESSING"
    db.commit()
    db.refresh(project)
    db.refresh(job)

    original_path = Path(project.original_file_path)
    temp_audio_path: Optional[Path] = None
    temp_wav_path: Optional[Path] = None

    try:
        audio_utils.validate_media_file(original_path)

        is_video = audio_utils.is_video_file(original_path)

        if is_video:
            logger.info("Audio extraction started for project_id=%s user_id=%s", project_id, project.user_id)
            extracted_filename = f"extracted_{project_id}{original_path.suffix}"
            temp_audio_path = Path(settings.TEMP_DIR) / extracted_filename
            audio_utils.extract_audio_from_video(original_path, temp_audio_path)
            logger.info("Audio extraction completed for project_id=%s user_id=%s", project_id, project.user_id)
            audio_to_convert = temp_audio_path
        else:
            audio_to_convert = original_path

        temp_wav_path = Path(settings.TEMP_DIR) / f"converted_{project_id}.wav"
        audio_utils.convert_to_wav(audio_to_convert, temp_wav_path)

        vocals_path, instrumental_path = separate_audio(temp_wav_path, project_id)

        project.vocals_url = f"/api/v1/projects/file/vocals/{project_id}.wav"
        project.instrumental_url = f"/api/v1/projects/file/instrumental/{project_id}.wav"
        project.status = "COMPLETED"

        job.status = "COMPLETED"
        job.vocals_filepath = str(vocals_path)
        job.instrumental_filepath = str(instrumental_path)
        job.completed_at = datetime.now(timezone.utc)
        job.updated_at = job.completed_at

        db.commit()
        db.refresh(project)
        db.refresh(job)

        logger.info(
            "Processing completed for project_id=%s user_id=%s job_id=%s",
            project_id,
            project.user_id,
            job_id,
        )
        return project

    except Exception as e:
        logger.exception(
            "Processing failed for project_id=%s user_id=%s job_id=%s",
            project_id,
            project.user_id,
            job_id,
        )
        if not db.is_active:
            db.rollback()

        completed_at = datetime.now(timezone.utc)
        try:
            failed_project = db.get(Project, project_id)
            failed_job = db.get(Job, job_id)

            if failed_project is not None:
                failed_project.status = "FAILED"

            if failed_job is not None:
                failed_job.status = "FAILED"
                failed_job.error_message = str(e)
                failed_job.completed_at = completed_at
                failed_job.updated_at = completed_at

            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.critical(
                "Failed to save failure status for project_id=%s job_id=%s: %s",
                project_id,
                job_id,
                str(db_err),
                exc_info=True,
            )

        raise
    finally:
        if temp_audio_path and temp_audio_path.exists():
            try:
                temp_audio_path.unlink()
            except Exception:
                logger.exception("Failed to remove temp file %s", temp_audio_path)
        if temp_wav_path and temp_wav_path.exists():
            try:
                temp_wav_path.unlink()
            except Exception:
                logger.exception("Failed to remove temp file %s", temp_wav_path)
