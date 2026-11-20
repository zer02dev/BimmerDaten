"""
app_update.py
App version and the check for a newer BimmerDaten release on GitHub.

Only the GitHub API is contacted (no user data is sent). The newest published
release is used; if the repository has no releases, the newest vX.Y.Z tag is.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("bimmerdaten.app_update")

# Single place to change on a release (also update installer/BimmerDaten.iss
# and scripts/build-installer.ps1).
APP_VERSION = "1.2.0"

REPO = "zer02dev/BimmerDaten"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
TAGS_API = f"https://api.github.com/repos/{REPO}/tags?per_page=100"
TIMEOUT_S = 6

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


def parse_version(text: str) -> tuple[int, int, int] | None:
    """'v1.2.0' / '1.2' -> (1, 2, 0); anything else (e.g. 'alpha') -> None."""
    match = _VERSION_RE.match((text or "").strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def is_newer(remote: str, local: str = APP_VERSION) -> bool:
    remote_v, local_v = parse_version(remote), parse_version(local)
    return bool(remote_v and local_v and remote_v > local_v)


def _get_json(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "BimmerDaten-update-check",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_latest_release() -> dict:
    """Return {'tag': 'v1.3.0', 'url': ..., 'name': ...} for the newest release or tag."""
    try:
        data = _get_json(LATEST_RELEASE_API)
        tag = str(data.get("tag_name") or "")
        if parse_version(tag):
            return {
                "tag": tag,
                "url": str(data.get("html_url") or f"{RELEASES_PAGE}/tag/{tag}"),
                "name": str(data.get("name") or tag),
            }
    except urllib.error.HTTPError as exc:
        if exc.code != 404:  # 404 = no published release yet -> try tags
            raise

    tags = [str(t.get("name") or "") for t in _get_json(TAGS_API)]
    versions = [(parse_version(t), t) for t in tags if parse_version(t)]
    if not versions:
        raise RuntimeError("No version tags found on GitHub")
    _, tag = max(versions)
    return {"tag": tag, "url": f"{RELEASES_PAGE}/tag/{tag}", "name": tag}


class AppReleaseCheckWorker(QThread):
    """Background check. Emits `checked(info)` or `failed(message)`."""

    checked = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def run(self):
        try:
            info = fetch_latest_release()
            info["newer"] = is_newer(info["tag"])
            self.checked.emit(info)
        except Exception as exc:
            logger.info("App release check failed: %s", exc)
            self.failed.emit(str(exc))
