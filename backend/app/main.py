"""Single-origin Phase 8 API foundation and explicitly approved frontend assets."""
from pathlib import Path
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException

from .config import ROOT, Settings
from .database import database_ready
from .schemas import ErrorResponse, HealthResponse

FRONTEND = ROOT / "frontend"
# Retain the current public JSON preview until the Phase 11 API integration.
ASSETS = {
    "", "index.html", "app.js", "styles.css", "macos-tokens.css", "centers.json",
    "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/leaflet/LICENSE",
}


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title="Care & Learn API", version="0.1.0")
    application.state.settings = settings or Settings.from_env()
    api = APIRouter(prefix="/api")

    @api.get("/health", response_model=HealthResponse, responses={503: {"model": ErrorResponse}})
    def health():
        if not database_ready(application.state.settings.database_path):
            return error_response(503, "database_unavailable", "Provider database is not ready.")
        return HealthResponse()

    # Register API first. The asset allowlist never accepts an /api path.
    application.include_router(api)

    @application.exception_handler(HTTPException)
    async def http_error(_request: Request, exception: HTTPException):
        if exception.status_code == 404:
            return error_response(404, "not_found", "Resource not found.")
        return JSONResponse(status_code=exception.status_code, content={"detail": exception.detail}, headers=exception.headers)

    @application.get("/{asset_path:path}", include_in_schema=False)
    def frontend_asset(asset_path: str):
        if asset_path not in ASSETS:
            raise HTTPException(status_code=404)
        path = FRONTEND / (asset_path or "index.html")
        # Resolve symlinks as well as path names before returning a file.
        if not path.is_file() or not path.resolve().is_relative_to(FRONTEND.resolve()):
            raise HTTPException(status_code=404)
        return FileResponse(path)

    return application


app = create_app()
