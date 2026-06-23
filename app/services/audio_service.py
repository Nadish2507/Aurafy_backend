import os
import shutil
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional

from sqlalchemy.orm import Session
import demucs.separate

from app.core.config import settings
from app.models.project import Project
from app.models.job import Job
from app.utils import audio_utils

logger = logging.getLogger(__name__)

def separate_audio(wav_path: Path, project_id: uuid.UUID) -> Tuple[Path, Path]:
    """
    Runs Demucs separation on the provided WAV file.
    Saves the output to the processed vocals and instrumental directories with the project ID as filename.
    Returns (vocals_path, instrumental_path).
    """
    logger.info("demucs started")
    
    # 1. Create a unique temp folder for Demucs output
    temp_demucs_dir = Path(settings.TEMP_DIR) / f"demucs_{project_id}"
    temp_demucs_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 2. Invoke demucs.separate programmatically
        # htdemucs is the default pretrained model
        # --two-stems vocals splits only into vocals and no_vocals (which is the mixture of other stems)
        opts = [
            "-n", "htdemucs",
            "--two-stems", "vocals",
            "-o", str(temp_demucs_dir),
            str(wav_path)
        ]
        
        logger.info(f"Running Demucs with opts: {opts}")
        demucs.separate.main(opts)
        
        # 3. Locate output files
        # Demucs places files in: {out_dir}/{model_name}/{track_name}/{stem_name}.wav
        track_name = wav_path.stem
        vocals_source = temp_demucs_dir / "htdemucs" / track_name / "vocals.wav"
        instrumental_source = temp_demucs_dir / "htdemucs" / track_name / "no_vocals.wav"
        
        if not vocals_source.exists() or not instrumental_source.exists():
            raise RuntimeError("Demucs failed to generate output files.")
            
        # 4. Define final destinations
        vocals_dest = Path(settings.VOCALS_DIR) / f"{project_id}.wav"
        instrumental_dest = Path(settings.INSTRUMENTAL_DIR) / f"{project_id}.wav"
        
        # Ensure parent directories exist
        vocals_dest.parent.mkdir(parents=True, exist_ok=True)
        instrumental_dest.parent.mkdir(parents=True, exist_ok=True)
        
        # 5. Move/copy files to final locations
        shutil.copy(vocals_source, vocals_dest)
        shutil.copy(instrumental_source, instrumental_dest)
        
        logger.info("demucs completed")
        return vocals_dest, instrumental_dest
        
    except Exception as e:
        logger.error(f"Error during Demucs separation: {str(e)}")
        raise RuntimeError(f"Demucs separation failed: {str(e)}")
    finally:
        # Cleanup temporary demucs output folder
        if temp_demucs_dir.exists():
            shutil.rmtree(temp_demucs_dir, ignore_errors=True)

def process_project(db: Session, project_id: uuid.UUID) -> Project:
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
    logger.info(f"Processing project {project_id}")
    
    # Fetch project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found.")
        
    logger.info(f"upload received for project {project_id}")
    
    # Initialize or fetch a Processing Job
    job = Job(
        user_id=project.user_id,
        status="PENDING",
        original_filename=project.filename,
        original_filepath=project.original_file_path,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    
    # Transition Project status to pending
    project.status = "pending"
    db.commit()
    db.refresh(project)
    
    # Update Job to PROCESSING
    job.status = "PROCESSING"
    job.started_at = datetime.now(timezone.utc)
    job.updated_at = datetime.now(timezone.utc)
    
    project.status = "processing"
    db.commit()
    db.refresh(project)
    
    # Paths for temporary working files
    original_path = Path(project.original_file_path)
    temp_audio_path: Optional[Path] = None
    temp_wav_path: Optional[Path] = None
    
    try:
        # Step 1: Validate uploaded file
        audio_utils.validate_media_file(original_path)
        
        # Step 2: Detect audio/video
        is_video = audio_utils.is_video_file(original_path)
        
        # Step 3: Extract audio if video
        if is_video:
            logger.info("extraction started")
            extracted_filename = f"extracted_{project_id}{original_path.suffix}"
            temp_audio_path = Path(settings.TEMP_DIR) / extracted_filename
            audio_utils.extract_audio_from_video(original_path, temp_audio_path)
            logger.info("extraction completed")
            audio_to_convert = temp_audio_path
        else:
            audio_to_convert = original_path
            
        # Step 4: Convert audio to WAV
        temp_wav_path = Path(settings.TEMP_DIR) / f"converted_{project_id}.wav"
        audio_utils.convert_to_wav(audio_to_convert, temp_wav_path)
        
        # Step 5 & 6: Run Demucs separation & Generate output
        vocals_path, instrumental_path = separate_audio(temp_wav_path, project_id)
        
        # Step 7 & 8: Update database records (Project)
        project.vocals_url = f"/api/v1/projects/file/vocals/{project_id}.wav"
        project.instrumental_url = f"/api/v1/projects/file/instrumental/{project_id}.wav"
        project.status = "completed"
        
        # Step 9: Update Job status
        job.status = "COMPLETED"
        job.vocals_filepath = str(vocals_path)
        job.instrumental_filepath = str(instrumental_path)
        job.completed_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(project)
        db.refresh(job)
        
        logger.info("processing completed")
        return project
        
    except Exception as e:
        logger.error(f"processing failed: {str(e)}")
        if not db.is_active:
            db.rollback()

        completed_at = datetime.now(timezone.utc)
        try:
            failed_project = db.get(Project, project_id)
            failed_job = db.get(Job, job_id)

            if failed_project is not None:
                failed_project.status = "failed"

            if failed_job is not None:
                failed_job.status = "FAILED"
                failed_job.error_message = str(e)
                failed_job.completed_at = completed_at
                failed_job.updated_at = completed_at

            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.critical(f"Failed to save failure status to database: {str(db_err)}")

        raise
    finally:
        # Cleanup temporary files
        if temp_audio_path and temp_audio_path.exists():
            try:
                temp_audio_path.unlink()
            except Exception:
                pass
        if temp_wav_path and temp_wav_path.exists():
            try:
                temp_wav_path.unlink()
            except Exception:
                pass
