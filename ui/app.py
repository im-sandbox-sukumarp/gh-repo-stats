"""
Main Starlette Application for gh-repo-stats Web UI

A modern web interface for analyzing GitHub organization repositories.
"""

import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from .routes import routes

# Get the UI directory path
UI_DIR = Path(__file__).parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"

# Debug mode from environment
DEBUG = os.getenv("GH_DEBUG", "").lower() in ("true", "1", "api")


def create_app() -> Starlette:
    """Create and configure the Starlette application."""
    
    # Configure middleware
    middleware = [
        Middleware(
            TrustedHostMiddleware,
            allowed_hosts=["localhost", "127.0.0.1", "*.localhost"],
        ),
        Middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        ),
    ]
    
    # Create app routes including static files
    app_routes = [
        Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
        *routes,
    ]
    
    # Create the application
    app = Starlette(
        debug=DEBUG,
        routes=app_routes,
        middleware=middleware,
        on_startup=[startup],
        on_shutdown=[shutdown],
    )
    
    # Setup Jinja2 templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    
    # Add custom template globals/filters
    templates.env.globals["app_name"] = "gh-repo-stats"
    templates.env.globals["app_version"] = "1.0.0"
    
    # Store templates in app state for access in routes
    app.state.templates = templates
    
    return app


async def startup() -> None:
    """Application startup handler."""
    print("🚀 gh-repo-stats Web UI starting...")
    print(f"   Templates: {TEMPLATES_DIR}")
    print(f"   Static: {STATIC_DIR}")


async def shutdown() -> None:
    """Application shutdown handler."""
    print("👋 gh-repo-stats Web UI shutting down...")


# Create the application instance
app = create_app()


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the development server."""
    import uvicorn
    
    print(f"\n🌐 Starting gh-repo-stats Web UI")
    print(f"   URL: http://{host}:{port}")
    print(f"   Press Ctrl+C to stop\n")
    
    uvicorn.run(
        "ui.app:app",
        host=host,
        port=port,
        reload=DEBUG,
        log_level="info" if DEBUG else "warning",
    )


if __name__ == "__main__":
    run_server()
