"""Fetch a public GitHub repo and stream its source files for analysis.

Strategy: download the repo's zipball via the GitHub REST API
(`/repos/{owner}/{repo}/zipball/{ref}`) — works for any public repo without
cloning. Optional `GITHUB_TOKEN` env var raises the rate limit and unlocks
private repos owned by the token.

We deliberately keep this dependency-light (httpx + zipfile from stdlib) and
hard-cap fetched bytes / files so a malicious URL can't OOM the server.
"""

from __future__ import annotations

import io
import logging
import os
import re
import zipfile
from dataclasses import dataclass
from typing import Iterable, List

import httpx

logger = logging.getLogger(__name__)


_GITHUB_URL_RE = re.compile(
    r"""^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[\w.\-]+)/(?P<repo>[\w.\-]+?)(?:\.git)?(?:/.*)?$""",
    re.IGNORECASE,
)

# Conservative caps. GitHub's zipball is gzip'd; uncompressed limits matter more.
_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024       # 50 MiB compressed
_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MiB total
_MAX_FILE_BYTES = 1 * 1024 * 1024            # 1 MiB per source file
_MAX_FILES = 200
_DEFAULT_EXTENSIONS = (".py", ".ipynb")


@dataclass(frozen=True)
class RepoFile:
    path: str          # repo-relative path, e.g. "src/train.py"
    content: str


class RepoFetchError(RuntimeError):
    """Raised when we can't safely fetch / unpack the repo."""


def parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) for a github URL or raise RepoFetchError."""
    m = _GITHUB_URL_RE.match(url.strip())
    if not m:
        raise RepoFetchError(
            "Expected a GitHub URL like https://github.com/owner/repo"
        )
    return m.group("owner"), m.group("repo")


def fetch_repo_files(
    url: str,
    *,
    ref: str | None = None,
    extensions: Iterable[str] = _DEFAULT_EXTENSIONS,
    timeout_s: float = 20.0,
    max_files: int = _MAX_FILES,
) -> List[RepoFile]:
    """Download a public GitHub repo and return source files matching `extensions`.

    Raises RepoFetchError on bad URL, network failure, oversized payload, or
    if the archive contains paths trying to escape the working directory.
    """
    owner, repo = parse_github_url(url)
    archive_ref = (ref or "HEAD").strip() or "HEAD"
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{archive_ref}"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gridgreen/repo-fetcher",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=True, verify=False) as client:
            resp = client.get(api_url, headers=headers)
    except httpx.HTTPError as exc:
        raise RepoFetchError(f"GitHub fetch failed: {exc}") from exc

    if resp.status_code == 404:
        raise RepoFetchError(
            f"Repo not found or private without GITHUB_TOKEN: {owner}/{repo}"
        )
    if resp.status_code == 403:
        raise RepoFetchError(
            "GitHub rate limit hit (set GITHUB_TOKEN to raise the cap)."
        )
    if resp.status_code >= 400:
        raise RepoFetchError(f"GitHub returned HTTP {resp.status_code}")

    body = resp.content
    if len(body) > _MAX_DOWNLOAD_BYTES:
        raise RepoFetchError(
            f"Repo zipball is {len(body) / 1e6:.1f} MB (cap {_MAX_DOWNLOAD_BYTES / 1e6:.0f} MB)."
        )

    return list(_extract_source_files(body, extensions, max_files))


def _extract_source_files(
    zip_bytes: bytes,
    extensions: Iterable[str],
    max_files: int,
) -> Iterable[RepoFile]:
    ext_lower = tuple(e.lower() for e in extensions)
    total_unpacked = 0
    emitted = 0
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                if emitted >= max_files:
                    break
                name = info.filename
                if info.is_dir() or name.endswith("/"):
                    continue
                # GitHub zipballs always have a top-level dir like
                # "owner-repo-<sha>/path/to/file" — strip it.
                rel = name.split("/", 1)[1] if "/" in name else name
                if not rel:
                    continue
                if rel.startswith(("../", "/")) or "/.." in rel:
                    raise RepoFetchError("Refusing to extract escaping path.")
                if not rel.lower().endswith(ext_lower):
                    continue
                if info.file_size > _MAX_FILE_BYTES:
                    logger.info("Skipping oversized file %s (%d bytes)", rel, info.file_size)
                    continue
                total_unpacked += info.file_size
                if total_unpacked > _MAX_UNCOMPRESSED_BYTES:
                    raise RepoFetchError(
                        f"Repo too large to analyze (>{_MAX_UNCOMPRESSED_BYTES / 1e6:.0f} MB uncompressed)."
                    )
                try:
                    raw = zf.read(info)
                except zipfile.BadZipFile as exc:
                    logger.warning("Bad zip entry %s: %s", rel, exc)
                    continue
                try:
                    content = raw.decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    continue
                emitted += 1
                yield RepoFile(path=rel, content=content)
    except zipfile.BadZipFile as exc:
        raise RepoFetchError(f"GitHub returned a non-zip body: {exc}") from exc


def extract_python_from_notebook(content: str) -> str:
    """Best-effort: pull code cells out of a .ipynb so detection still runs.

    Returns the original content if it doesn't look like a notebook — the
    detector is regex-based so it survives random JSON noise either way.
    """
    import json

    try:
        nb = json.loads(content)
    except Exception:  # noqa: BLE001
        return content
    cells = nb.get("cells")
    if not isinstance(cells, list):
        return content
    chunks: List[str] = []
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source")
        if isinstance(src, list):
            chunks.append("".join(src))
        elif isinstance(src, str):
            chunks.append(src)
    return "\n\n".join(chunks)
