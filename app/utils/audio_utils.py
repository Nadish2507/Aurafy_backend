import os
import logging
from pathlib import Path
import ffmpeg

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}
SUPPORTED_EXTENSIONS = SUPPORTED_AUDIO_EXTENSIONS.union(SUPPORTED_VIDEO_EXTENSIONS)

def validate_media_file(file_path: Path) -> None:
    """
    Validate that the file exists, is not empty, has a supported extension,
    and can be successfully probed by FFmpeg.
    
    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty, has an unsupported extension,
                    or does not contain audio/video streams.
        RuntimeError: If FFmpeg fails to probe the file.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
        
    if file_path.stat().st_size == 0:
        raise ValueError("File is empty.")
        
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: '{suffix}'")
        
    try:
        # Probe the media file to verify it's valid
        probe = ffmpeg.probe(str(file_path))
        streams = probe.get("streams", [])
        
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        has_video = any(s.get("codec_type") == "video" for s in streams)
        
        if not (has_audio or has_video):
            raise ValueError("Media file contains neither audio nor video streams.")
            
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"FFmpeg probe failed for {file_path}: {stderr}")
        raise ValueError(f"Invalid media file structure: {stderr}")
    except Exception as e:
        logger.error(f"Error validating media file {file_path}: {str(e)}")
        raise RuntimeError(f"Error parsing media file: {str(e)}")

def is_video_file(file_path: Path) -> bool:
    """
    Check if the file path has a supported video extension.
    """
    return file_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS

def extract_audio_from_video(video_path: Path, output_audio_path: Path) -> None:
    """
    Extract the audio stream from a video file and save it to the output path.
    The output format is determined by the output file extension.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    # Ensure output parent directory exists
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        logger.info(f"Extracting audio from {video_path} to {output_audio_path}")
        # Disable video and extract audio
        ffmpeg.input(str(video_path)).output(
            str(output_audio_path),
            vn=None
        ).run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
        logger.info(f"Audio successfully extracted to {output_audio_path}")
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"FFmpeg audio extraction failed: {stderr}")
        raise RuntimeError(f"FFmpeg audio extraction failed: {stderr}")
    except Exception as e:
        logger.error(f"Unexpected error during audio extraction: {str(e)}")
        raise RuntimeError(f"Failed to extract audio from video: {str(e)}")

def convert_to_wav(input_audio_path: Path, output_wav_path: Path) -> None:
    """
    Convert any audio file to CD-quality WAV format (PCM 16-bit, 44.1kHz, Stereo).
    """
    if not input_audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_audio_path}")
        
    # Ensure output parent directory exists
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        logger.info(f"Converting {input_audio_path} to WAV at {output_wav_path}")
        # Re-encode to pcm_s16le, 44.1kHz, stereo WAV
        ffmpeg.input(str(input_audio_path)).output(
            str(output_wav_path),
            acodec="pcm_s16le",
            ar="44100",
            ac=2
        ).run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
        logger.info(f"WAV conversion successful: {output_wav_path}")
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"FFmpeg WAV conversion failed: {stderr}")
        raise RuntimeError(f"FFmpeg WAV conversion failed: {stderr}")
    except Exception as e:
        logger.error(f"Unexpected error during WAV conversion: {str(e)}")
        raise RuntimeError(f"Failed to convert audio to WAV: {str(e)}")
