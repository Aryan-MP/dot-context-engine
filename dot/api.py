"""Local REST API, served on localhost:7337.

Endpoints:
    GET    /status         daemon health + project stats
    GET    /context        assembled context for a file/query
    POST   /memory         capture a decision/memory
    GET    /memory         browse memories
    DELETE /memory/{id}    forget a memory
    GET    /graph          dependency graph as JSON
    POST   /ask            natural-language query of the codebase
    POST   /sync           force re-index
    POST   /hooks/git/commit   git post-commit ping (installed by dot init)
    GET    /ui             web dashboard (when dashboard/dist is built)
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dot import __version__
from dot.context.formatter import FORMATS, context_to_dict, format_context

if TYPE_CHECKING:
    from dot.daemon import Daemon

logger = logging.getLogger(__name__)


class MemoryIn(BaseModel):
    content: str = Field(min_length=3)
    kind: Literal["decision", "rejected", "action_item", "note", "conversation"] = "note"
    source: str = "api"
    file_path: str = ""
    tags: list[str] = []
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ConversationIn(BaseModel):
    transcript: str = Field(min_length=10)
    source: str = "conversation"


class AskIn(BaseModel):
    question: str = Field(min_length=3)
    current_file: str | None = None
    fmt: str = "markdown"


class SyncIn(BaseModel):
    force: bool = False


def create_app(daemon: Daemon) -> FastAPI:
    app = FastAPI(
        title="Dot",
        version=__version__,
        description="Local-first AI context memory daemon",
    )
    # The dashboard dev server (vite) runs on another port; same machine only.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/status")
    def status() -> dict:
        return daemon.status()

    @app.get("/context")
    def get_context(
        query: str = "",
        file: str | None = Query(default=None, description="current file path"),
        fmt: str = Query(default="raw", description=f"one of {FORMATS}"),
        token_budget: int | None = Query(default=None, ge=100, le=100_000),
        profile: str | None = None,
    ):
        if fmt not in FORMATS:
            raise HTTPException(422, f"fmt must be one of {FORMATS}")
        context = daemon.assembler.assemble(
            query=query, current_file=file, token_budget=token_budget, profile=profile
        )
        if fmt == "raw":
            return context_to_dict(context)
        return Response(
            content=format_context(context, fmt),
            media_type="text/plain; charset=utf-8",
            headers={"x-dot-assembly-ms": f"{context.assembly_ms:.1f}"},
        )

    @app.post("/memory", status_code=201)
    def add_memory(body: MemoryIn) -> dict:
        memory = daemon.store.add_memory(
            content=body.content,
            kind=body.kind,
            source=body.source,
            file_path=body.file_path,
            tags=body.tags,
            confidence=body.confidence,
        )
        return {"id": memory.memory_id, "kind": memory.kind}

    @app.post("/memory/conversation", status_code=201)
    def capture_conversation(body: ConversationIn) -> dict:
        captured = daemon.decisions.capture_from_conversation(body.transcript, body.source)
        return {"captured": len(captured), "ids": [memory.memory_id for memory in captured]}

    @app.get("/memory")
    def list_memories(
        kind: str | None = None,
        query: str | None = None,
        limit: int = Query(default=50, ge=1, le=1000),
    ) -> dict:
        if query:
            memories = daemon.store.query_memories(query, n=limit)
        else:
            memories = daemon.store.list_memories(kind=kind, limit=limit)
        return {
            "memories": [
                {
                    "id": memory.memory_id,
                    "kind": memory.kind,
                    "content": memory.content,
                    "source": memory.source,
                    "file_path": memory.file_path,
                    "tags": memory.tags,
                    "confidence": memory.confidence,
                    "weight": round(memory.weight, 4),
                    "created_at": memory.created_at.isoformat() if memory.created_at else None,
                }
                for memory in memories
            ]
        }

    @app.get("/memory/export")
    def export_memories() -> dict:
        return {"project": daemon.config.project_name, "memories": daemon.store.export_memories()}

    @app.delete("/memory/{memory_id}")
    def delete_memory(memory_id: str) -> dict:
        if not daemon.store.delete_memory(memory_id):
            raise HTTPException(404, "memory not found")
        return {"deleted": memory_id}

    @app.get("/graph")
    def graph() -> dict:
        return daemon.store.dependency_graph()

    @app.post("/ask")
    def ask(body: AskIn):
        """Natural-language query: returns the most relevant code + decisions.

        Dot is model-agnostic and fully local — it retrieves and ranks; the
        calling tool (Claude, Copilot, a script) does the generation.
        """
        context = daemon.assembler.assemble(body.question, current_file=body.current_file)
        if body.fmt == "raw":
            return context_to_dict(context)
        if body.fmt not in FORMATS:
            raise HTTPException(422, f"fmt must be one of {FORMATS}")
        return Response(
            content=format_context(context, body.fmt),
            media_type="text/plain; charset=utf-8",
        )

    @app.post("/sync", status_code=202)
    def sync(body: SyncIn | None = None) -> dict:
        force = bool(body and body.force)
        thread = threading.Thread(
            target=daemon.full_sync, kwargs={"force": force}, daemon=True, name="dot-api-sync"
        )
        thread.start()
        return {"status": "sync started", "force": force}

    @app.post("/hooks/git/commit")
    def git_commit_hook() -> dict:
        captured = daemon.decisions.mine_git(max_count=5)
        return {"decisions_captured": captured}

    # Serve the built dashboard at /ui when present.
    dist = Path(__file__).resolve().parent.parent / "dashboard" / "dist"
    if dist.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/ui", StaticFiles(directory=str(dist), html=True), name="dashboard")
    else:

        @app.get("/ui")
        def ui_placeholder() -> dict:
            return {
                "message": "dashboard not built — run `npm install && npm run build` in dashboard/",
            }

    return app
