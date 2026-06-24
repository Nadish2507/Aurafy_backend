from fastapi import FastAPI
from app.core.config import settings
from app.api.auth import router as auth_router
from app.api.downloads import router as downloads_router
from app.api.projects import router as projects_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Include routers
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(projects_router, prefix=f"{settings.API_V1_STR}/projects", tags=["projects"])
app.include_router(downloads_router, prefix=f"{settings.API_V1_STR}/downloads", tags=["downloads"])

@app.get("/")
def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}

