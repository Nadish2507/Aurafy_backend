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
