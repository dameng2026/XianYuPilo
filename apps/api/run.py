import os
from pathlib import Path

import uvicorn

CURRENT_DIR = Path(__file__).resolve().parent
RELOAD_ENABLED = os.getenv("API_RELOAD", "").strip().lower() in {"1", "true", "yes", "on"}

if __name__ == "__main__":
    os.chdir(CURRENT_DIR)
    from app.core.config import settings

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=RELOAD_ENABLED,
        app_dir=str(CURRENT_DIR),
        reload_dirs=[str(CURRENT_DIR)] if RELOAD_ENABLED else None,
    )
