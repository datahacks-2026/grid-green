"""Upload `eia_hourly_export.csv` to Databricks DBFS (or run export first).

Requires (same PAT as SQL smoke test, plus SDK):

    pip install databricks-sdk
    pip install python-dotenv   # to read backend/.env

Usage:

    cd backend
    python -m scripts.upload_eia_export_to_databricks --export

Optional: only upload an existing file:

    python -m scripts.upload_eia_export_to_databricks --local data/exports/eia_hourly_export.csv

Env (see backend/.env.example):

    DATABRICKS_SERVER_HOSTNAME   # host only, no https://
    DATABRICKS_TOKEN
    DATABRICKS_DBFS_EXPORT_PATH  # default: /FileStore/gridgreen/eia_hourly_export.csv

In `bronze_eia_raw_bootstrap.py` set CSV_PATH to dbfs:/FileStore/gridgreen/eia_hourly_export.csv
(or the same path you configure here).
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.getcwd()
ROOT = os.path.dirname(HERE)


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


def main() -> int:
    p = argparse.ArgumentParser(description="Export EIA CSV and upload to Databricks DBFS.")
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

    local_path = os.path.normpath(os.path.join(ROOT, args.local) if not os.path.isabs(args.local) else args.local)
    if not os.path.isfile(local_path):
        print(f"Local file not found: {local_path}")
        return 1

    host = _normalize_host(_env("DATABRICKS_SERVER_HOSTNAME") or "")
    token = _env("DATABRICKS_TOKEN") or ""
    remote = _env("DATABRICKS_DBFS_EXPORT_PATH") or "/FileStore/gridgreen/eia_hourly_export.csv"
    if not remote.startswith("/"):
        remote = "/" + remote

    if not host or not token:
        print("Set DATABRICKS_SERVER_HOSTNAME and DATABRICKS_TOKEN in backend/.env")
        return 1

    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        print("Install: pip install databricks-sdk")
        return 1

    url = f"https://{host}"
    client = WorkspaceClient(host=url, token=token)

    parent = os.path.dirname(remote) or "/"
    try:
        client.dbfs.mkdirs(parent)
    except Exception:
        pass

    data = open(local_path, "rb").read()
    client.dbfs.upload(remote, io.BytesIO(data), overwrite=True)
    print(f"Uploaded {len(data)} bytes to dbfs:{remote}")
    print(f"Use in notebook CSV_PATH = \"dbfs:{remote}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
