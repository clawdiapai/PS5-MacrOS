"""Graph JSON persistence under data/graphs/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.config import settings

router = APIRouter(prefix="/api/graphs", tags=["graphs"])

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


class GraphDocument(BaseModel):
    """LiteGraph-compatible document wrapper (nodes/links opaque until Phase 1.5)."""

    name: str = Field(min_length=1, max_length=64)
    version: int = 1
    graph: dict[str, Any] = Field(default_factory=dict)


def _graphs_dir() -> Path:
    settings.graphs_dir.mkdir(parents=True, exist_ok=True)
    return settings.graphs_dir


def _path_for(name: str) -> Path:
    if not _SAFE_NAME.match(name):
        raise HTTPException(
            status_code=400,
            detail="name must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}",
        )
    return _graphs_dir() / f"{name}.json"


@router.get("")
async def list_graphs() -> dict[str, Any]:
    names = sorted(p.stem for p in _graphs_dir().glob("*.json"))
    return {"ok": True, "graphs": names}


@router.get("/{name}")
async def get_graph(name: str) -> dict[str, Any]:
    path = _path_for(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="graph not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"corrupt graph: {exc}") from exc
    return {"ok": True, "document": data}


@router.put("/{name}")
async def put_graph(name: str, body: GraphDocument) -> dict[str, Any]:
    if body.name != name:
        raise HTTPException(status_code=400, detail="body.name must match path")
    path = _path_for(name)
    payload = body.model_dump()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "name": name, "path": str(path.relative_to(settings.data_dir))}


@router.delete("/{name}")
async def delete_graph(name: str) -> dict[str, Any]:
    path = _path_for(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="graph not found")
    path.unlink()
    return {"ok": True, "deleted": name}


def get_graph_document(name: str) -> dict[str, Any]:
    """Load raw document for RunController (raises FileNotFoundError)."""
    path = _path_for(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    return json.loads(path.read_text(encoding="utf-8"))
