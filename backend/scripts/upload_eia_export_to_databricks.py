"""Upload `eia_hourly_export.csv` to Databricks (UC volume preferred, DBFS fallback).

Modern workspaces disable the legacy **public** ``/FileStore`` root. This
script therefore tries, in order:

1. ``DATABRICKS_UC_VOLUME_EXPORT_PATH`` — full path under a UC volume, e.g.
   ``/Volumes/gridgreen/raw/landing/eia_hourly_export.csv``
2. ``DATABRICKS_VOLUME_NAME`` + ``DATABRICKS_BRONZE_TABLE`` — builds
   ``/Volumes/<catalog>/<schema>/<volume>/eia_hourly_export.csv``
3. Heuristic volume names under the bronze catalog/schema (``landing``,
   ``ingest``, ``staging``, …)
4. ``DATABRICKS_DBFS_EXPORT_PATH`` if set (``dbfs.upload`` — legacy DBFS)
5. Last resort: ``/FileStore/gridgreen/eia_hourly_export.csv``

Paths under ``/Volumes/`` use the **Files API** (``WorkspaceClient.files``);
other paths use **DBFS** (``WorkspaceClient.dbfs``).

Requires:

    pip install databricks-sdk python-dotenv

Env:

    DATABRICKS_SERVER_HOSTNAME   # host only, no https://
    DATABRICKS_TOKEN
    DATABRICKS_BRONZE_TABLE      # default gridgreen.raw.eia_raw (catalog.schema.table)
    DATABRICKS_UC_VOLUME_EXPORT_PATH   # optional — full /Volumes/.../file.csv
    DATABRICKS_VOLUME_NAME       # optional — volume name under catalog.schema
    DATABRICKS_WORKSPACE_EXPORT_PATH  # optional — e.g. /Workspace/Shared/me/eia_hourly_export.csv
    DATABRICKS_DBFS_EXPORT_PATH  # optional — legacy DBFS absolute path

Optional (SDK may require for some workspaces):

    DATABRICKS_ENABLE_EXPERIMENTAL_FILES_API_CLIENT=1

Usage::

    cd backend
    python -m scripts.upload_eia_export_to_databricks --export
    python -m scripts.upload_eia_export_to_databricks --local data/exports/eia_hourly_export.csv
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
from typing import List, Tuple

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.getcwd()
ROOT = os.path.dirname(HERE)

# Files API client path (Unity Catalog volumes) — enable before WorkspaceClient().
os.environ.setdefault("DATABRICKS_ENABLE_EXPERIMENTAL_FILES_API_CLIENT", "1")

_GUESSED_VOLUME_NAMES = (
    "landing",
    "ingest",
    "staging",
    "uploads",
    "data",
    "files",
    "raw_data",
    "gridgreen",
)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(os.path.join(ROOT, ".env"))
    load_dotenv(os.path.join(os.getcwd(), ".env"))


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


def _parse_bronze_fqn(fqn: str) -> Tuple[str | None, str | None]:
    """``gridgreen.raw.eia_raw`` → (``gridgreen``, ``raw``)."""
    parts = fqn.strip().replace("`", "").split(".")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def _normalize_remote_path(p: str) -> str:
    p = p.strip()
    if not p.startswith("/"):
        p = "/" + p
    return p


def _candidate_remote_paths() -> List[str]:
    """Ordered remote paths to try (deduped)."""
    seen: set[str] = set()
    out: List[str] = []

    def add(p: str) -> None:
        p = _normalize_remote_path(p)
        if p not in seen:
            seen.add(p)
            out.append(p)

    uc_full = _env("DATABRICKS_UC_VOLUME_EXPORT_PATH")
    if uc_full:
        add(uc_full)

    bronze = _env("DATABRICKS_BRONZE_TABLE") or "gridgreen.raw.eia_raw"
    cat, sch = _parse_bronze_fqn(bronze)

    vol_only = _env("DATABRICKS_VOLUME_NAME")
    if cat and sch and vol_only:
        add(f"/Volumes/{cat}/{sch}/{vol_only}/eia_hourly_export.csv")

    # User-configured legacy DBFS (or any non-/Volumes path) — try before
    # heuristic UC guesses so custom mounts like /mnt/... win quickly.
    legacy = _env("DATABRICKS_DBFS_EXPORT_PATH")
    if legacy:
        add(legacy)

    if cat and sch:
        for vname in _GUESSED_VOLUME_NAMES:
            add(f"/Volumes/{cat}/{sch}/{vname}/eia_hourly_export.csv")

    # Workspace “Shared” tree — often writable when UC /FileStore are locked down.
    # Uses w.workspace.upload (not the UC Files API).
    ws = _env("DATABRICKS_WORKSPACE_EXPORT_PATH")
    if ws:
        add(ws)
    add("/Workspace/Shared/gridgreen/eia_hourly_export.csv")

    if not legacy:
        add("/FileStore/gridgreen/eia_hourly_export.csv")

    return out


def _upload_via_files_api(
    client,
    remote_path: str,
    data: bytes,
    *,
    local_path: str | None = None,
) -> None:
    """Unity Catalog volume path — Files API (not legacy DBFS)."""
    if not hasattr(client, "files") or client.files is None:
        raise RuntimeError(
            "WorkspaceClient has no .files API. Install a recent databricks-sdk and set "
            "DATABRICKS_ENABLE_EXPERIMENTAL_FILES_API_CLIENT=1 (the upload script sets this by default)."
        )

    parent = os.path.dirname(remote_path.rstrip("/")) or "/"
    try:
        client.files.create_directory(parent)
    except Exception:
        # Parent may already exist; upload_from often succeeds anyway.
        pass

    # Prefer upload_from (disk → cloud): fewer stream/seek edge cases than BinaryIO.
    if local_path and os.path.isfile(local_path):
        client.files.upload_from(
            remote_path,
            local_path,
            overwrite=True,
            use_parallel=False,
        )
        return

    stream = io.BytesIO(data)
    stream.seek(0)
    client.files.upload(remote_path, stream, overwrite=True, use_parallel=False)


def _upload_via_workspace_files(
    client,
    remote_path: str,
    data: bytes,
    *,
    local_path: str | None = None,
) -> None:
    """Databricks workspace file (e.g. under ``/Workspace/Shared/...``).

    Uses ``WorkspaceExt.upload`` — works without a Unity Catalog volume.
    """
    from databricks.sdk.service.workspace import ImportFormat

    parent = os.path.dirname(remote_path.rstrip("/")) or "/"
    try:
        client.workspace.mkdirs(parent)
    except Exception:
        pass

    if local_path and os.path.isfile(local_path):
        with open(local_path, "rb") as f:
            client.workspace.upload(
                remote_path, f, format=ImportFormat.AUTO, overwrite=True
            )
        return

    stream = io.BytesIO(data)
    stream.seek(0)
    client.workspace.upload(
        remote_path, stream, format=ImportFormat.AUTO, overwrite=True
    )


def _upload_via_dbfs(client, remote_path: str, data: bytes) -> None:
    parent = os.path.dirname(remote_path) or "/"
    try:
        client.dbfs.mkdirs(parent)
    except Exception:
        pass
    stream = io.BytesIO(data)
    client.dbfs.upload(remote_path, stream, overwrite=True)


def upload_bytes_to_databricks(
    client,
    remote_path: str,
    data: bytes,
    *,
    local_path: str | None = None,
) -> None:
    """Dispatch to UC Files API, workspace upload, or legacy DBFS."""
    if remote_path.startswith("/Volumes/"):
        _upload_via_files_api(client, remote_path, data, local_path=local_path)
    elif remote_path.startswith("/Workspace/"):
        _upload_via_workspace_files(
            client, remote_path, data, local_path=local_path
        )
    else:
        _upload_via_dbfs(client, remote_path, data)


def upload_export_file(local_path: str) -> str:
    """Try candidate paths until one succeeds. Returns the remote path used."""
    host = _normalize_host(_env("DATABRICKS_SERVER_HOSTNAME") or "")
    token = _env("DATABRICKS_TOKEN") or ""
    if not host or not token:
        raise RuntimeError(
            "Set DATABRICKS_SERVER_HOSTNAME and DATABRICKS_TOKEN in backend/.env"
        )

    try:
        from databricks.sdk import WorkspaceClient
    except ImportError as exc:
        raise RuntimeError("Install: pip install databricks-sdk") from exc

    url = f"https://{host}"
    # Prefer explicit Config so the Files API client is enabled even if the
    # process started before this module's setdefault on DATABRICKS_* env.
    try:
        from databricks.sdk.core import Config as DatabricksConfig  # type: ignore

        cfg = DatabricksConfig(host=url, token=token)
        for attr in ("enable_experimental_files_api_client", "enable_experimental_files_api"):
            if hasattr(cfg, attr):
                setattr(cfg, attr, True)
                break
        client = WorkspaceClient(config=cfg)
    except Exception:
        client = WorkspaceClient(host=url, token=token)

    data = open(local_path, "rb").read()
    errors: List[str] = []
    for remote in _candidate_remote_paths():
        try:
            upload_bytes_to_databricks(
                client, remote, data, local_path=local_path
            )
            return remote
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{remote}: {type(exc).__name__}: {exc}")

    hint = (
        "\n\nHint: create a Unity Catalog volume in your bronze catalog/schema, then set "
        "DATABRICKS_UC_VOLUME_EXPORT_PATH=/Volumes/<catalog>/<schema>/<volume>/eia_hourly_export.csv "
        "or DATABRICKS_VOLUME_NAME=<volume> (with DATABRICKS_BRONZE_TABLE=catalog.schema.table)."
    )
    msg = "All upload paths failed:\n  " + "\n  ".join(errors) + hint
    raise RuntimeError(msg)


def main() -> int:
    p = argparse.ArgumentParser(description="Export EIA CSV and upload to Databricks.")
    p.add_argument(
        "--export",
        action="store_true",
        help="Run export_eia_hourly_to_databricks_csv first.",
    )
    p.add_argument(
        "--local",
        default=os.path.join(ROOT, "data", "exports", "eia_hourly_export.csv"),
        help="Local CSV path (default: backend/data/exports/eia_hourly_export.csv).",
    )
    args = p.parse_args()

    _load_dotenv()

    if args.export:
        r = subprocess.run(
            [sys.executable, "-m", "scripts.export_eia_hourly_to_databricks_csv"],
            cwd=ROOT,
        )
        if r.returncode != 0:
            return r.returncode

    local_path = os.path.normpath(
        os.path.join(ROOT, args.local) if not os.path.isabs(args.local) else args.local
    )
    if not os.path.isfile(local_path):
        print(f"Local file not found: {local_path}")
        return 1

    try:
        remote = upload_export_file(local_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Uploaded {os.path.getsize(local_path)} bytes → {remote}")
    if remote.startswith("/Volumes/"):
        print(f"In a notebook use the same path (UC volume): {remote}")
        print("Spark example: spark.read.format('csv').load(f'dbfs:{remote}')")
    else:
        print(f"Use in notebook CSV_PATH = \"dbfs:{remote}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
