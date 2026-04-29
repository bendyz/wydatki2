#!/usr/bin/env python3
"""
Skrypt startowy aplikacji Wydatki 2.0.
Odczytuje host i port z data/config/config.yaml i uruchamia serwer uvicorn.
"""

import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.debug,
    )
