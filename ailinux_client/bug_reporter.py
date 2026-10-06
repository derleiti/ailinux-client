"""Shared AILinux crash, startup self-test and manual diagnostics reporter.

The client never contains SMTP credentials. Reports are redacted locally, queued
when offline and POSTed to the fixed TriForce HTTPS endpoint.
"""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import platform
import re
import sys
import threading
import traceback
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
import uuid

ENDPOINT = "https://api.ailinux.me/v1/bugs/report"
MAX_LOG_LINES = 250
MAX_LOG_BYTES = 768 * 1024
MAX_PENDING = 20
_SECRET_KEYS = {
    "authorization", "api_key", "apikey", "token", "access_token", "refresh_token",
    "secret", "password", "passwd", "resume_token", "workspace_token", "pair_code",
}

_config = {"app": "AICoder", "repo": "ai-coder", "version": "unknown", "channel": "desktop"}
_ring: deque[str] = deque(maxlen=MAX_LOG_LINES)
_lock = threading.RLock()
_installed = False
_original_sys_hook = sys.excepthook
_original_thread_hook = getattr(threading, "excepthook", None)


def _state_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
        return base / "AILinux" / "diagnostics" / _config["repo"]
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AILinux" / "diagnostics" / _config["repo"]
    base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return base / "ailinux" / "diagnostics" / _config["repo"]


def _log_path() -> Path: return _state_root() / "runtime.jsonl"
def _pending_path() -> Path: return _state_root() / "pending-reports.json"
def _install_id_path() -> Path: return _state_root() / "install-id"


def redact(value: Any, limit: int = 48_000) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:api[_-]?key|token|secret|password|passwd|resume[_-]?token|pair[_-]?code)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)\b[A-F0-9]{4}(?:-[A-F0-9]{4}){5}\b", "[REDACTED]", text)
    text = re.sub(r"(?i)([?&](?:token|key|secret|password|code)=)[^&#\s]+", r"\1[REDACTED]", text)
    return text[:limit]


def scrub(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:200]:
            name = str(key)[:128]
            normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            out[name] = "[REDACTED]" if normalized in _SECRET_KEYS else scrub(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub(item, depth + 1) for item in list(value)[:250]]
    if isinstance(value, str):
        return redact(value, 8_000)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(value, 2_000)


def _ensure_dir() -> None:
    _state_root().mkdir(parents=True, exist_ok=True, mode=0o700)


def _rotate_log() -> None:
    path = _log_path()
    try:
        if not path.exists() or path.stat().st_size <= MAX_LOG_BYTES:
            return
        previous = path.with_suffix(".previous.jsonl")
        previous.unlink(missing_ok=True)
        path.replace(previous)
    except OSError:
        pass


def log_event(event: str, detail: Any = None, *, level: str = "info") -> None:
    record = scrub({"ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "level": level, "event": event, "detail": detail})
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _lock:
        _ring.append(line)
        try:
            _ensure_dir(); _rotate_log()
            with _log_path().open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass


def _collect_logs() -> list[str]:
    rows: deque[str] = deque(maxlen=MAX_LOG_LINES)
    try:
        with _log_path().open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip(): rows.append(redact(line.rstrip("\n"), 2_000))
    except OSError:
        pass
    with _lock:
        rows.extend(_ring)
    return list(rows)[-MAX_LOG_LINES:]


def _install_id() -> str:
    try:
        _ensure_dir()
        path = _install_id_path()
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()[:128]
        value = str(uuid.uuid4())
        path.write_text(value + "\n", encoding="utf-8")
        try: path.chmod(0o600)
        except OSError: pass
        return value
    except OSError:
        return ""


def _payload(event_type: str, delivery: str) -> dict[str, Any]:
    return {
        "app": _config["app"], "repo": _config["repo"], "version": _config["version"],
        "platform": sys.platform, "os_version": platform.platform(), "arch": platform.machine(),
        "channel": _config["channel"], "event_type": event_type, "delivery": delivery,
        "install_id": _install_id(), "logs": _collect_logs(),
        "metadata": scrub({"python": sys.version.split()[0], "implementation": platform.python_implementation()}),
    }


def _read_pending() -> list[dict[str, Any]]:
    try:
        value = json.loads(_pending_path().read_text(encoding="utf-8"))
        return value[-MAX_PENDING:] if isinstance(value, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _write_pending(rows: list[dict[str, Any]]) -> None:
    _ensure_dir()
    path = _pending_path(); tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows[-MAX_PENDING:], ensure_ascii=False), encoding="utf-8")
    try: tmp.chmod(0o600)
    except OSError: pass
    tmp.replace(path)


def _queue(payload: dict[str, Any]) -> str:
    with _lock:
        rows = _read_pending(); local_id = str(uuid.uuid4()); rows.append({**scrub(payload), "_local_id": local_id}); _write_pending(rows)
        return local_id


def _post(payload: dict[str, Any], timeout: float = 4.0) -> bool:
    clean = dict(scrub(payload)); clean.pop("_local_id", None)
    body = json.dumps(clean, ensure_ascii=False).encode("utf-8")
    request = Request(ENDPOINT, data=body, method="POST", headers={"Content-Type": "application/json", "User-Agent": f"AILinux-{_config['repo']}/{_config['version']}"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS endpoint
            return 200 <= int(response.status) < 300
    except (OSError, URLError, ValueError):
        return False


def flush_pending() -> dict[str, int]:
    with _lock:
        rows = _read_pending(); keep: list[dict[str, Any]] = []; sent = 0
        for row in rows:
            if _post(row): sent += 1
            else: keep.append(row)
        try: _write_pending(keep)
        except OSError: pass
        return {"sent": sent, "remaining": len(keep)}


def submit_exception(error: BaseException, *, origin: str = "uncaught", event_type: str = "crash") -> bool:
    payload = _payload(event_type, "automatic")
    payload.update({
        "exception_type": type(error).__name__, "exception_message": redact(error),
        "stack": redact("".join(traceback.format_exception(type(error), error, error.__traceback__))),
    })
    payload["metadata"]["origin"] = redact(origin)
    local_id = _queue(payload)
    ok = _post(payload)
    if ok:
        with _lock:
            try: _write_pending([row for row in _read_pending() if row.get("_local_id") != local_id])
            except OSError: pass
    log_event("exception_report", {"type": type(error).__name__, "submitted": ok, "queued": not ok}, level="error")
    return ok


def submit_manual(message: str = "") -> dict[str, bool]:
    payload = _payload("manual", "manual"); payload["user_message"] = redact(message, 8_000)
    ok = _post(payload)
    if not ok: _queue(payload)
    log_event("manual_report", {"submitted": ok, "queued": not ok})
    return {"ok": ok, "queued": not ok}


def startup_selftest() -> dict[str, Any]:
    checks: dict[str, Any] = {"python": sys.version.split()[0]}; ok = True
    try:
        _ensure_dir(); probe = _state_root() / ".selftest"; probe.write_text("ok", encoding="utf-8"); probe.unlink(); checks["state_dir_writable"] = True
    except OSError as exc:
        ok = False; checks["state_dir_writable"] = False; checks["state_dir_error"] = redact(exc)
    checks["threading_hook"] = hasattr(threading, "excepthook")
    log_event("startup_selftest", {"ok": ok, "checks": checks})
    if not ok:
        payload = _payload("selftest", "selftest"); payload["selftest"] = checks; payload["exception_message"] = "Startup self-test failed"
        if not _post(payload): _queue(payload)
    return {"ok": ok, "checks": checks}


def install(*, app: str = "AICoder", repo: str = "ai-coder", version: str = "unknown", channel: str = "desktop") -> None:
    global _installed, _config
    _config = {"app": app, "repo": repo, "version": str(version), "channel": channel}
    if _installed: return
    _installed = True

    def sys_hook(exc_type, exc, tb):
        if exc is not None: submit_exception(exc, origin="sys.excepthook")
        _original_sys_hook(exc_type, exc, tb)
    sys.excepthook = sys_hook

    if _original_thread_hook is not None:
        def thread_hook(args):
            if args.exc_value is not None: submit_exception(args.exc_value, origin=f"thread:{getattr(args.thread, 'name', '')}")
            _original_thread_hook(args)
        threading.excepthook = thread_hook

    log_event("reporter_installed", {"version": version, "channel": channel})
    # Cheap local self-test runs synchronously so short-lived CLI commands are
    # checked too. Network delivery is attempted only when the self-test fails.
    startup_selftest()
    threading.Thread(target=flush_pending, name="ailinux-bug-flush", daemon=True).start()
