"""HTTP / WebSocket route modules."""

from fastapi import APIRouter

from backend.app.api import (
    anchors,
    bridge_routes,
    console,
    graphs,
    macros,
    ocr_targets,
    passthrough,
    preview,
    runs,
    session,
    setup,
    vision,
    ws,
)


def build_api_router() -> APIRouter:
    api = APIRouter()
    api.include_router(setup.router)
    api.include_router(graphs.router)
    api.include_router(runs.router)
    api.include_router(bridge_routes.router)
    api.include_router(session.router)
    api.include_router(console.router)
    api.include_router(anchors.router)
    api.include_router(ocr_targets.router)
    api.include_router(macros.router)
    api.include_router(passthrough.router)
    api.include_router(preview.router)
    api.include_router(vision.router)
    api.include_router(ws.router)
    return api
