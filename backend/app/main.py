from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import Settings
from app.core.dependencies import DependencyStatus, probe_dependencies
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import UploadSizeLimitMiddleware
from app.database.session import build_engine, build_session_factory


def create_app(
    settings: Settings | None = None,
    dependencies: dict[str, DependencyStatus] | None = None,
) -> FastAPI:
    active_settings = settings or Settings()
    configure_logging(active_settings)
    active_settings.workspace_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title=active_settings.app_name, version="0.1.0")
    app.state.settings = active_settings
    app.state.engine = build_engine(active_settings)
    app.state.session_factory = build_session_factory(app.state.engine)
    app.state.dependencies = dependencies or probe_dependencies(active_settings)

    app.add_middleware(
        UploadSizeLimitMiddleware,
        max_upload_bytes=active_settings.max_upload_bytes,
        max_upload_mb=active_settings.max_upload_mb,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
