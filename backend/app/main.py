"""Single-origin backend API and explicitly approved frontend assets."""
import re
import sqlite3
import uuid
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException

from .ai import OpenAIWebAdapter
from .config import ROOT, Settings
from .database import database_ready
from .discovery import DiscoveryService
from .errors import DiscoveryError
from .evidence import EvidenceValidator, SourceFetcher
from .repository import Repository
from .schemas import DiscoverRequest, DiscoveryResponse, ErrorResponse, HealthResponse, ScopedSearchRequest, DirectorySearchResponse, StoredSearchRequest
from .search import search, reveal

FRONTEND = ROOT / 'frontend'
ASSETS = {
    '', 'index.html', 'app.js', 'styles.css', 'macos-tokens.css', 'centers.json',
    'vendor/leaflet/leaflet.js', 'vendor/leaflet/leaflet.css', 'vendor/leaflet/LICENSE',
}


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}})


class BodyLimit:
    """Bound API request bodies before JSON parsing, including chunked requests."""
    def __init__(self, app, limit=8192):
        self.app, self.limit = app, limit
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > self.limit:
                return await error_response(413, 'request_too_large', 'Request exceeds the server size limit.')(scope, receive, send)
            messages.append(message)
            if not message.get('more_body', False):
                break
        pending = iter(messages)
        async def replay():
            return next(pending, None) or await receive()
        await self.app(scope, replay, send)


def create_app(settings: Settings | None = None, discovery_service=None) -> FastAPI:
    settings = settings or Settings.from_env()
    application = FastAPI(title='Care & Learn API', version='0.2.0')
    application.state.settings = settings
    application.state.discovery = discovery_service or DiscoveryService(
        Repository(settings.database_path), OpenAIWebAdapter(settings, fetch_source=SourceFetcher(settings.source_domains)), EvidenceValidator(allowed_domains=settings.source_domains),
        timeout_seconds=settings.ai_timeout_seconds, max_results=settings.ai_max_results,
        max_requests_per_minute=settings.ai_requests_per_minute, max_inflight=settings.ai_max_inflight,
        ttl_seconds=settings.cache_ttl_seconds)
    application.add_middleware(BodyLimit)
    api = APIRouter(prefix='/api')

    @api.get('/health', response_model=HealthResponse, responses={503: {'model': ErrorResponse}})
    def health():
        if not database_ready(application.state.settings.database_path):
            return error_response(503, 'database_unavailable', 'Provider database is not ready.')
        return HealthResponse()

    @api.post('/discover', response_model=DiscoveryResponse,
              responses={409: {'model': ErrorResponse}, 429: {'model': ErrorResponse}, 503: {'model': ErrorResponse}, 502: {'model': ErrorResponse}, 504: {'model': ErrorResponse}})
    async def discover(body: DiscoverRequest, request: Request, response: Response):
        session = request.cookies.get('care_learn_session', '')
        if not re.fullmatch(r'[a-f0-9]{32}', session):
            # First requests are guarded together until the browser has its session cookie.
            session = 'anonymous'
            response.set_cookie('care_learn_session', uuid.uuid4().hex, httponly=True, samesite='strict', secure=request.url.scheme == 'https')
        return await application.state.discovery.discover(body, session)

    @api.post('/reveal', response_model=DiscoveryResponse)
    def reveal_saved(body: StoredSearchRequest):
        return reveal(Repository(settings.database_path), body, settings.cache_ttl_seconds)

    @api.post('/search', response_model=DirectorySearchResponse)
    def search_providers(body: ScopedSearchRequest):
        return search(Repository(settings.database_path), body)

    # Explicit API routes precede the asset allowlist; no repository directory is mounted.
    application.include_router(api)

    @application.exception_handler(DiscoveryError)
    async def discovery_error(_request: Request, exception: DiscoveryError):
        return error_response(exception.status, exception.code, exception.message)

    @application.exception_handler(sqlite3.Error)
    async def database_error(_request: Request, _exception):
        return error_response(503, 'database_unavailable', 'Provider database is temporarily unavailable.')

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exception: RequestValidationError):
        # Preserve FastAPI's detail envelope without echoing submitted queries/coordinates/secrets.
        detail = [{key: value for key, value in item.items() if key in ('loc', 'msg', 'type')} for item in exception.errors()]
        return JSONResponse(status_code=422, content={'detail': detail})

    @application.exception_handler(HTTPException)
    async def http_error(_request: Request, exception: HTTPException):
        if exception.status_code == 404:
            return error_response(404, 'not_found', 'Resource not found.')
        return JSONResponse(status_code=exception.status_code, content={'detail': exception.detail}, headers=exception.headers)

    @application.get('/{asset_path:path}', include_in_schema=False)
    def frontend_asset(asset_path: str):
        if asset_path not in ASSETS:
            raise HTTPException(status_code=404)
        path = FRONTEND / (asset_path or 'index.html')
        if not path.is_file() or not path.resolve().is_relative_to(FRONTEND.resolve()):
            raise HTTPException(status_code=404)
        return FileResponse(path)

    return application


app = create_app()
