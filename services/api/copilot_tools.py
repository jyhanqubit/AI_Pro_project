"""Copilot tool transports: in-process calls or the MCP server over stdio.

The GraphRAG copilot and the rule-based fallback do not touch the replay engine directly; they
ask a :class:`CopilotTools` for context, statistics, metrics, forecasts and pricing. Two
implementations exist:

- :class:`InProcessTools` — calls :mod:`services.mcp.core` directly (the original behaviour).
- :class:`McpStdioTools` — spawns ``python -m services.mcp.server`` once, keeps the session on a
  background event loop, and calls the same tools over the Model Context Protocol.

Both return the tool models serialised with ``model_dump(mode="json")``, so payloads are
identical across transports. ``COPILOT_TOOL_TRANSPORT`` selects the transport; if the MCP
server cannot be spawned or a call fails, the caller degrades to in-process and labels the
answer ``tool_transport="inprocess_fallback"`` — never a fabricated result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from config.settings import get_settings
from contracts.v2.mcp import PricingRules
from services.mcp import core

log = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[2]


class TransportError(RuntimeError):
    """The MCP transport itself failed (spawn, protocol, timeout) — distinct from a tool error."""


class ToolCallError(RuntimeError):
    """The tool ran and reported a structured error (same codes as the HTTP API)."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class CopilotTools(Protocol):
    transport: str

    def graph_context(self, cutoff: datetime, max_events: int = 12) -> dict[str, Any]: ...

    def operator_statistics(self, cutoff: datetime) -> dict[str, Any]: ...

    def metric(self, name: str) -> dict[str, Any]: ...

    def model_forecast(self, top: int = 20) -> dict[str, Any]: ...

    def pricing_quotes(
        self,
        cutoff: datetime,
        *,
        stale: bool = False,
        safety: bool = False,
        rules: PricingRules | None = None,
    ) -> dict[str, Any]: ...


class InProcessTools:
    def __init__(self, engine: Any, transport: str = "inprocess") -> None:
        self._engine = engine
        self.transport = transport

    def _call(self, fn, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(self._engine, *args, **kwargs).model_dump(mode="json")
        except core.ToolFailure as exc:
            raise ToolCallError(exc.payload.error_code, exc.payload.message) from exc

    def graph_context(self, cutoff: datetime, max_events: int = 12) -> dict[str, Any]:
        return self._call(core.graph_context, cutoff, max_events)

    def operator_statistics(self, cutoff: datetime) -> dict[str, Any]:
        return self._call(core.operator_statistics, cutoff)

    def metric(self, name: str) -> dict[str, Any]:
        return self._call(core.metric, name)

    def model_forecast(self, top: int = 20) -> dict[str, Any]:
        return self._call(core.model_forecast, top)

    def pricing_quotes(
        self,
        cutoff: datetime,
        *,
        stale: bool = False,
        safety: bool = False,
        rules: PricingRules | None = None,
    ) -> dict[str, Any]:
        return self._call(core.pricing_quotes, cutoff, stale=stale, safety=safety, rules=rules)


_ERR_JSON = re.compile(r"\{.*\}", re.S)


class McpStdioTools:
    """MCP client over stdio to ``services.mcp.server``; one long-lived session per process."""

    transport = "mcp_stdio"

    def __init__(self, timeout_s: float = 20.0, command: list[str] | None = None) -> None:
        self._timeout = timeout_s
        self._command = command or [sys.executable, "-m", "services.mcp.server"]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: Any = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._stop: asyncio.Event | None = None  # created on the loop thread
        self._lock = threading.Lock()

    # -- lifecycle -------------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, name="mcp-stdio", daemon=True)
            self._thread.start()
            if not self._ready.wait(timeout=max(self._timeout, 60.0)):
                raise TransportError("MCP server did not become ready in time")
            if self._error is not None:
                raise TransportError(f"MCP server failed to start: {self._error!r}")

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 - surfaced to the caller via _error
            self._error = exc
            self._ready.set()
        finally:
            # The loop owns a self-pipe socketpair; leaving it open surfaces later as a
            # ResourceWarning at garbage collection (the test suite treats warnings as errors).
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            finally:
                self._loop.close()

    async def _serve(self) -> None:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        self._stop = asyncio.Event()
        params = StdioServerParameters(
            command=self._command[0],
            args=self._command[1:],
            cwd=str(_REPO_ROOT),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                self._ready.set()
                await self._stop.wait()
        self._session = None

    def close(self) -> None:
        """Stop the server session and release the loop thread (idempotent)."""
        with self._lock:
            loop, thread = self._loop, self._thread
            if loop is None:
                return
            if self._stop is not None and self._session is not None and not loop.is_closed():
                loop.call_soon_threadsafe(self._stop.set)
            if thread is not None:
                thread.join(timeout=5)
            if not loop.is_closed() and (thread is None or not thread.is_alive()):
                loop.close()
            self._loop = None
            self._thread = None
            self._session = None
            self._stop = None
            self._ready.clear()

    # -- calls -----------------------------------------------------------------------------
    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            self.start()
        assert self._loop is not None and self._session is not None
        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments, read_timeout_seconds=self._timeout),
            self._loop,
        )
        try:
            result = fut.result(timeout=self._timeout + 5)
        except Exception as exc:  # noqa: BLE001 - any protocol/timeout failure is a transport error
            raise TransportError(f"MCP call {name} failed: {exc!r}") from exc
        if getattr(result, "is_error", False):
            text = " ".join(getattr(c, "text", "") for c in result.content)
            m = _ERR_JSON.search(text)
            if m:
                try:
                    payload = json.loads(m.group(0))
                    raise ToolCallError(payload["error_code"], payload["message"])
                except (ValueError, KeyError):
                    pass
            # The SDK validates arguments before the tool body runs, so a schema violation
            # arrives as its text rather than our JSON payload; give it the API's code.
            if "validation error" in text:
                raise ToolCallError("validation_error", text)
            raise ToolCallError("tool_error", text)
        if result.structured_content is None:
            raise TransportError(f"MCP tool {name} returned no structured content")
        return result.structured_content

    @staticmethod
    def _iso(cutoff: datetime) -> str:
        return cutoff.isoformat()

    def graph_context(self, cutoff: datetime, max_events: int = 12) -> dict[str, Any]:
        return self._call(
            "get_graph_context", {"cutoff": self._iso(cutoff), "max_events": max_events}
        )

    def operator_statistics(self, cutoff: datetime) -> dict[str, Any]:
        return self._call("get_operator_statistics", {"cutoff": self._iso(cutoff)})

    def metric(self, name: str) -> dict[str, Any]:
        return self._call("get_metric", {"name": name})

    def model_forecast(self, top: int = 20) -> dict[str, Any]:
        return self._call("get_model_forecast", {"top": top})

    def pricing_quotes(
        self,
        cutoff: datetime,
        *,
        stale: bool = False,
        safety: bool = False,
        rules: PricingRules | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"cutoff": self._iso(cutoff), "stale": stale, "safety": safety}
        if rules is not None:
            args["rules"] = rules.model_dump(mode="json")
        return self._call("get_pricing_quotes", args)


# -- factory ------------------------------------------------------------------------------------
_MCP: McpStdioTools | None = None
_MCP_LOCK = threading.Lock()


def mcp_tools() -> McpStdioTools:
    """The process-wide MCP client (spawned on first use)."""
    global _MCP
    with _MCP_LOCK:
        if _MCP is None:
            _MCP = McpStdioTools(timeout_s=get_settings().mcp_tool_timeout_s)
    _MCP.start()
    return _MCP


def get_copilot_tools(engine: Any) -> CopilotTools:
    """Transport chosen by ``COPILOT_TOOL_TRANSPORT``; degrades to in-process if MCP is unusable."""
    if get_settings().copilot_tool_transport == "mcp_stdio":
        try:
            return mcp_tools()
        except TransportError as exc:
            log.warning("MCP transport unavailable, degrading to in-process tools: %s", exc)
            return InProcessTools(engine, transport="inprocess_fallback")
    return InProcessTools(engine)


def warm_tools() -> str:
    """Startup hook: spawn the MCP server early when configured. Never raises."""
    if get_settings().copilot_tool_transport != "mcp_stdio":
        return "inprocess"
    try:
        mcp_tools()
        return "mcp_stdio"
    except TransportError as exc:
        log.warning("MCP server not started at boot (%s); copilot will degrade per request", exc)
        return "inprocess_fallback"
