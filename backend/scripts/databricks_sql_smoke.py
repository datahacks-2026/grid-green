"""Verify SQL warehouse credentials (SELECT 1).

Does not import `app.config` so it works with only:

  pip install databricks-sql-connector

Optional: `pip install python-dotenv` to load `backend/.env` automatically.

  cd backend
  python -m scripts.databricks_sql_smoke

All status lines use flush=True so you see output immediately (no silent hang).
"""

from __future__ import annotations

import os

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.getcwd()
ROOT = os.path.dirname(HERE)


def _log(msg: str) -> None:
    print(msg, flush=True)


def _load_dotenv() -> bool:
    """Load `backend/.env` then `./.env` from cwd. Returns False if python-dotenv is missing."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    load_dotenv(os.path.join(ROOT, ".env"))
    load_dotenv(os.path.join(os.getcwd(), ".env"))
    return True


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is None:
        return None
    s = v.strip().strip('"').strip("'")
    return s or None


def _normalize_host(host: str) -> str:
    h = host.strip()
    if h.startswith("https://"):
        h = h[len("https://") :]
    if h.startswith("http://"):
        h = h[len("http://") :]
    return h.split("/")[0].strip() or host


def _normalize_http_path(path: str) -> str:
    p = path.strip()
    if p and not p.startswith("/"):
        return "/" + p
    return p


def main() -> int:
    _log("databricks_sql_smoke: starting")
    dotenv_ok = _load_dotenv()
    _log(f"databricks_sql_smoke: dotenv loaded={dotenv_ok}  cwd={os.getcwd()!r}")

    host = _normalize_host(_env("DATABRICKS_SERVER_HOSTNAME") or "")
    path = _normalize_http_path(_env("DATABRICKS_HTTP_PATH") or "")
    token = _env("DATABRICKS_TOKEN") or ""
    if not host or not path or not token:
        missing = [
            n
            for n, v in (
                ("DATABRICKS_SERVER_HOSTNAME", host),
                ("DATABRICKS_HTTP_PATH", path),
                ("DATABRICKS_TOKEN", token),
            )
            if not v
        ]
        env_path = os.path.join(ROOT, ".env")
        _log("Missing or empty: " + ", ".join(missing))
        _log(
            "Add those exact names to backend/.env (see backend/.env.example), "
            "or export them in your shell."
        )
        if not dotenv_ok and os.path.isfile(env_path):
            _log("Also: pip install python-dotenv  (so this script can read backend/.env)")
        return 1

    _log(f"databricks_sql_smoke: host={host!r}  http_path={path!r}  token_len={len(token)}")
    if not token.startswith("dapi") and len(token) < 20:
        _log(
            "Hint: token looks short and does not start with 'dapi'. "
            "Check User settings → Developer → Access tokens."
        )

    try:
        from databricks import sql
    except ImportError:
        _log("Install: pip install databricks-sql-connector")
        return 1

    def _run_select(kw: dict) -> object:
        with sql.connect(**kw) as conn:
            _log("databricks_sql_smoke: connected; running SELECT 1 …")
            cur = conn.cursor()
            cur.execute("SELECT 1")
            return cur.fetchone()

    # Default connector retry count is high; cap it so bad auth fails in reasonable time.
    skip_tls = os.environ.get("DATABRICKS_SKIP_TLS_VERIFY", "").lower() in ("1", "true", "yes")
    if skip_tls:
        _log("databricks_sql_smoke: WARNING — TLS verification disabled (DATABRICKS_SKIP_TLS_VERIFY=1)")
    kw: dict = {
        "server_hostname": host,
        "http_path": path,
        "access_token": token,
        "_retry_stop_after_attempts_count": 6,
        "_socket_timeout": 45,
        "_tls_no_verify": skip_tls,
    }
    _log("databricks_sql_smoke: connecting (socket timeout 45s, max 6 HTTP retries) …")
    row = None
    try:
        row = _run_select(dict(kw))
    except TypeError:
        _log("databricks_sql_smoke: connector rejected an option; retrying with fewer kwargs …")
        kw.pop("_socket_timeout", None)
        try:
            row = _run_select(dict(kw))
        except TypeError:
            kw.pop("_retry_stop_after_attempts_count", None)
            try:
                row = _run_select(dict(kw))
            except Exception as exc:
                _log(f"databricks_sql_smoke: failed: {type(exc).__name__}: {exc}")
                return 1
        except Exception as exc:
            _log(f"databricks_sql_smoke: failed: {type(exc).__name__}: {exc}")
            return 1
    except Exception as exc:
        _log(f"databricks_sql_smoke: failed: {type(exc).__name__}: {exc}")
        return 1

    if row is None:
        _log("databricks_sql_smoke: internal error (no row)")
        return 1

    _log(f"Databricks SQL warehouse OK: {row!r}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        _log("\nInterrupted.")
        raise SystemExit(130)
