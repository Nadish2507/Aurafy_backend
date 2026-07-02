import os
import wave
import struct
import uuid
import shutil
from pathlib import Path
import pytest
import ffmpeg
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.project import Project
from app.models.job import Job
from app.core.config import settings
from app.utils import audio_utils
from app.services import audio_service

# Helper to generate a 0.1-second valid WAV file
def generate_test_wav(path: Path) -> None:
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        num_frames = int(44100 * 0.1)
        data = struct.pack('<' + 'h' * num_frames, *([0] * num_frames))
        w.writeframes(data)

@pytest.fixture
def test_files_dir() -> Path:
    # A temp directory inside the settings.TEMP_DIR for generated test assets
    dir_path = Path(settings.TEMP_DIR) / "test_media_assets"
    dir_path.mkdir(parents=True, exist_ok=True)
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)

@pytest.fixture
def sample_wav(test_files_dir) -> Path:
    path = test_files_dir / "sample.wav"
    generate_test_wav(path)
    return path

@pytest.fixture
def sample_mp3(test_files_dir, sample_wav) -> Path:
    path = test_files_dir / "sample.mp3"
    # Convert WAV to MP3 using FFmpeg
    ffmpeg.input(str(sample_wav)).output(str(path)).run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
    return path

@pytest.fixture
def sample_mp4(test_files_dir, sample_wav) -> Path:
    path = test_files_dir / "sample.mp4"
    # Generate a black dummy video with the WAV audio using FFmpeg
    video_input = ffmpeg.input("color=c=black:s=640x480:d=0.1", f="lavfi")
    audio_input = ffmpeg.input(str(sample_wav))
    ffmpeg.output(
        video_input,
        audio_input,
        str(path),
        vcodec="mpeg4",
        acodec="aac",
        shortest=None,
    ).run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
    return path

@pytest.fixture
def test_user(db: Session) -> User:
    user = User(
        email=f"tester_{uuid.uuid4().hex}@example.com",
        hashed_password="somehashpassword123"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def test_is_video_file():
    assert audio_utils.is_video_file(Path("test.mp4")) is True
    assert audio_utils.is_video_file(Path("test.mov")) is True
    assert audio_utils.is_video_file(Path("test.avi")) is True
    assert audio_utils.is_video_file(Path("test.mp3")) is False
    assert audio_utils.is_video_file(Path("test.wav")) is False

def test_validate_media_file_success(sample_wav, sample_mp3, sample_mp4):
    # Valid files should not raise exceptions
    audio_utils.validate_media_file(sample_wav)
    audio_utils.validate_media_file(sample_mp3)
    audio_utils.validate_media_file(sample_mp4)

def test_validate_media_file_not_found():
    with pytest.raises(FileNotFoundError):
        audio_utils.validate_media_file(Path("non_existent_file.wav"))

def test_validate_media_file_empty(test_files_dir):
    empty_file = test_files_dir / "empty.wav"
    empty_file.touch()
    with pytest.raises(ValueError, match="empty"):
        audio_utils.validate_media_file(empty_file)

def test_validate_media_file_unsupported_ext(test_files_dir):
    txt_file = test_files_dir / "text.txt"
    txt_file.write_text("not media")
    with pytest.raises(ValueError, match="Unsupported"):
        audio_utils.validate_media_file(txt_file)

def test_validate_media_file_corrupt(test_files_dir):
    corrupt_wav = test_files_dir / "corrupt.wav"
    corrupt_wav.write_text("RIFFxxxxWAVEfmt corrupt data here")
    with pytest.raises(ValueError):
        audio_utils.validate_media_file(corrupt_wav)

def test_extract_audio_from_video(sample_mp4, test_files_dir):
    out_audio = test_files_dir / "extracted.wav"
    audio_utils.extract_audio_from_video(sample_mp4, out_audio)
    assert out_audio.exists()
    assert out_audio.stat().st_size > 0
    # Make sure we can probe it as a valid audio
    probe = ffmpeg.probe(str(out_audio))
    assert any(s.get("codec_type") == "audio" for s in probe.get("streams", []))

def test_convert_to_wav(sample_mp3, test_files_dir):
    out_wav = test_files_dir / "converted.wav"
    audio_utils.convert_to_wav(sample_mp3, out_wav)
    assert out_wav.exists()
    assert out_wav.stat().st_size > 0
    
    probe = ffmpeg.probe(str(out_wav))
    audio_stream = next(s for s in probe.get("streams", []) if s.get("codec_type") == "audio")
    assert audio_stream.get("codec_name") == "pcm_s16le"
    assert int(audio_stream.get("sample_rate")) == 44100
    assert int(audio_stream.get("channels")) == 2

def test_separate_audio_mocked(sample_wav, monkeypatch):
    project_id = uuid.uuid4()
    
    # Mock demucs.separate.main to simulate file creation
    def mock_main(opts):
        # opts = ["-n", "htdemucs", "--two-stems", "vocals", "-o", temp_demucs_dir, wav_path]
        out_dir = Path(opts[5])
        wav_path = Path(opts[6])
        track_name = wav_path.stem
        
        # Create output dirs mimicking Demucs structure
        vocals_dir = out_dir / "htdemucs" / track_name
        vocals_dir.mkdir(parents=True, exist_ok=True)
        
        # Write fake vocals and no_vocals files
        (vocals_dir / "vocals.wav").write_bytes(b"mock vocals")
        (vocals_dir / "no_vocals.wav").write_bytes(b"mock instrumental")

    monkeypatch.setattr(audio_service.demucs.separate, "main", mock_main)
    
    vocals_dest, instrumental_dest = audio_service.separate_audio(sample_wav, project_id)
    
    assert vocals_dest.exists()
    assert instrumental_dest.exists()
    assert vocals_dest == Path(settings.VOCALS_DIR) / f"{project_id}.wav"
    assert instrumental_dest == Path(settings.INSTRUMENTAL_DIR) / f"{project_id}.wav"
    assert vocals_dest.read_bytes() == b"mock vocals"
    assert instrumental_dest.read_bytes() == b"mock instrumental"
    
    # Cleanup files
    vocals_dest.unlink(missing_ok=True)
    instrumental_dest.unlink(missing_ok=True)

def test_process_project_workflow_success(db: Session, test_user, sample_mp3, monkeypatch):
    project_id = uuid.uuid4()
    
    # Copy sample MP3 to expected upload location
    upload_path = Path(settings.UPLOAD_DIR) / f"upload_{project_id}.mp3"
    shutil.copy(sample_mp3, upload_path)
    
    project = Project(
        id=project_id,
        user_id=test_user.id,
        filename="test_song.mp3",
        original_file_path=str(upload_path),
        original_file_url=f"/api/v1/projects/file/upload_{project_id}.mp3",
        status="UPLOADED"
    )
    db.add(project)
    db.commit()
    
    # Mock Demucs
    def mock_main(opts):
        out_dir = Path(opts[5])
        wav_path = Path(opts[6])
        track_name = wav_path.stem
        vocals_dir = out_dir / "htdemucs" / track_name
        vocals_dir.mkdir(parents=True, exist_ok=True)
        (vocals_dir / "vocals.wav").write_bytes(b"mock vocals data")
        (vocals_dir / "no_vocals.wav").write_bytes(b"mock instrumental data")
        
    monkeypatch.setattr(audio_service.demucs.separate, "main", mock_main)
    
    # Process
    processed_project = audio_service.process_project(db, project_id)
    
    assert processed_project.status == "COMPLETED"
    assert processed_project.vocals_url == f"/api/v1/projects/file/vocals/{project_id}.wav"
    assert processed_project.instrumental_url == f"/api/v1/projects/file/instrumental/{project_id}.wav"
    
    # Verify Job record
    job = db.query(Job).filter(Job.original_filepath == str(upload_path)).first()
    assert job is not None
    assert job.status == "COMPLETED"
    assert job.vocals_filepath == str(Path(settings.VOCALS_DIR) / f"{project_id}.wav")
    assert job.instrumental_filepath == str(Path(settings.INSTRUMENTAL_DIR) / f"{project_id}.wav")
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.started_at <= job.completed_at
    
    # Cleanup physical files
    upload_path.unlink(missing_ok=True)
    Path(job.vocals_filepath).unlink(missing_ok=True)
    Path(job.instrumental_filepath).unlink(missing_ok=True)

def test_process_project_workflow_failure(db: Session, test_user, test_files_dir):
    project_id = uuid.uuid4()
    
    # Create invalid (empty) media file to trigger validation failure
    invalid_path = test_files_dir / "invalid.mp3"
    invalid_path.touch()
    
    project = Project(
        id=project_id,
        user_id=test_user.id,
        filename="corrupt_song.mp3",
        original_file_path=str(invalid_path),
        original_file_url=f"/api/v1/projects/file/invalid.mp3",
        status="UPLOADED"
    )
    db.add(project)
    db.commit()
    
    # Processing should raise error and project status should become failed
    with pytest.raises(Exception):
        audio_service.process_project(db, project_id)
        
    db.refresh(project)
    assert project.status == "FAILED"
    
    # Verify Job record is failed
    job = db.query(Job).filter(Job.original_filepath == str(invalid_path)).first()
    assert job is not None
    assert job.status == "FAILED"
    assert job.error_message is not None
    assert job.started_at is not None
    assert job.completed_at is not None

def test_process_project_status_transitions(db: Session, test_user, sample_mp3, monkeypatch):
    project_id = uuid.uuid4()
    upload_path = Path(settings.UPLOAD_DIR) / f"upload_{project_id}.mp3"
    shutil.copy(sample_mp3, upload_path)

    project = Project(
        id=project_id,
        user_id=test_user.id,
        filename="status_song.mp3",
        original_file_path=str(upload_path),
        original_file_url=f"/api/v1/projects/file/upload_{project_id}.mp3",
        status="UPLOADED"
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    observed_statuses = [project.status]
    job = audio_service.create_pending_job(db, project)
    observed_statuses.append(project.status)

    original_convert_to_wav = audio_utils.convert_to_wav

    def tracking_convert_to_wav(audio_to_convert: Path, temp_wav_path: Path) -> None:
        db.refresh(project)
        observed_statuses.append(project.status)
        original_convert_to_wav(audio_to_convert, temp_wav_path)

    def mock_main(opts):
        out_dir = Path(opts[5])
        wav_path = Path(opts[6])
        track_name = wav_path.stem
        vocals_dir = out_dir / "htdemucs" / track_name
        vocals_dir.mkdir(parents=True, exist_ok=True)
        (vocals_dir / "vocals.wav").write_bytes(b"mock vocals data")
        (vocals_dir / "no_vocals.wav").write_bytes(b"mock instrumental data")

    monkeypatch.setattr(audio_utils, "convert_to_wav", tracking_convert_to_wav)
    monkeypatch.setattr(audio_service.demucs.separate, "main", mock_main)

    processed_project = audio_service.process_project(db, project_id, job.id)
    observed_statuses.append(processed_project.status)

    assert observed_statuses == ["UPLOADED", "PENDING", "PROCESSING", "COMPLETED"]

    db.refresh(job)
    assert job.status == "COMPLETED"
    upload_path.unlink(missing_ok=True)
    Path(job.vocals_filepath).unlink(missing_ok=True)
    Path(job.instrumental_filepath).unlink(missing_ok=True)
