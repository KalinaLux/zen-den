"""Zen Den — GitHub release update checker (stdlib only).

Fetches the latest release from the GitHub API and compares it to the bundled
version. Safe to call from the UI: failures never raise.
"""

import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("zen.updater")

CURRENT_VERSION = "2.5.0"
GITHUB_REPO = "KalinaLux/zen-den"
RELEASES_URL = "https://api.github.com/repos/KalinaLux/zen-den/releases/latest"
DOWNLOAD_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"

# ---------------------------------------------------------------------------
# Data directory resolution (PyInstaller-aware)
# ---------------------------------------------------------------------------


def _data_dir() -> Path:
    if getattr(sys, "_MEIPASS", None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


def _strip_version_prefix(version: str) -> str:
    v = version.strip()
    if v.lower().startswith("v"):
        return v[1:].lstrip()
    return v


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse dotted version into ints; non-numeric segments become 0."""
    core = _strip_version_prefix(version)
    parts: list[int] = []
    for segment in core.split("."):
        segment = segment.strip()
        if not segment:
            parts.append(0)
            continue
        num = ""
        for ch in segment:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def compare_versions(current: str, latest: str) -> bool:
    """Return True if *latest* is greater than *current* (simple semver ints)."""
    a, b = _version_tuple(current), _version_tuple(latest)
    n = max(len(a), len(b))
    a_pad = a + (0,) * (n - len(a))
    b_pad = b + (0,) * (n - len(b))
    return b_pad > a_pad


def get_current_version() -> str:
    return CURRENT_VERSION


def _failure(error: str) -> dict:
    log.debug("update check failed: %s", error)
    return {
        "update_available": False,
        "current_version": CURRENT_VERSION,
        "error": error,
    }


def check_for_update() -> dict:
    """GET latest GitHub release; return update info or a safe failure dict."""
    req = urllib.request.Request(
        RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ZenDen-UpdateChecker/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return _failure(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        return _failure(str(e.reason if e.reason else e))
    except TimeoutError:
        return _failure("Request timed out")
    except OSError as e:
        return _failure(str(e))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return _failure(f"Invalid JSON: {e}")

    tag_name = data.get("tag_name")
    if not tag_name or not isinstance(tag_name, str):
        return _failure("Missing or invalid tag_name in release payload")

    latest_ver = _strip_version_prefix(tag_name)
    if not compare_versions(CURRENT_VERSION, latest_ver):
        return {
            "update_available": False,
            "current_version": CURRENT_VERSION,
            "latest_version": latest_ver,
        }

    release_name = data.get("name") or tag_name
    release_url = data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/tag/{tag_name}"
    body = data.get("body")
    release_notes = body if isinstance(body, str) else ""
    published_at = data.get("published_at") or ""

    return {
        "update_available": True,
        "current_version": CURRENT_VERSION,
        "latest_version": latest_ver,
        "release_name": release_name,
        "release_url": release_url,
        "download_url": DOWNLOAD_URL,
        "release_notes": release_notes,
        "published_at": published_at,
    }
