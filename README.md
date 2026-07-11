# Aurafy Backend

AI-powered Vocal Remover and Audio Separation Platform.

## Tech Stack

- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- JWT Authentication
- FFmpeg
- Demucs
- Docker

## Features

- User Authentication
- Audio/Video Upload
- Vocal Separation
- Instrumental Extraction
- Processing History
- Download Processed Files

## Setup

```bash
pip install -r requirements.txt
python -m alembic upgrade head
uvicorn app.main:app --reload
```

## Windows Notes

- Install FFmpeg as the **full-shared** build, not the minimal essentials build.
- TorchCodec requires shared FFmpeg DLLs such as `avutil-*.dll`, `avcodec-*.dll`, `avformat-*.dll`, `avfilter-*.dll`, `swscale-*.dll`, and `swresample-*.dll`.
- Set `FFMPEG_BIN` if your FFmpeg binaries live outside the default path in `app/core/config.py`.
