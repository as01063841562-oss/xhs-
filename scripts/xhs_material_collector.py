#!/usr/bin/env python3
"""Collect local Xiaohongshu material snapshots for a customer workflow."""

from __future__ import annotations

import argparse
import json
import ssl
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import common

DEFAULT_CLIENT = "wuhan-tutoring"
DEFAULT_LIMIT_NOTES = 5
DEFAULT_CDP_URL = "http://127.0.0.1:9227"
PROFILE_CARD_ACCESS = "profile_card"
FULL_NOTE_ACCESS = "full_note"
COLLECTED_VIA = "chrome_cdp_profile_cards"
PROFILE_CARD_NOTE = (
    "full body was not accessible without login; this snapshot records only the "
    "visible profile-card metadata and cover image reference."
)

CollectorFunc = Callable[[str, int, str], dict[str, Any]]
DownloaderFunc = Callable[[str], bytes]
ProbeFunc = Callable[[str], bool]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Wuhan XHS customer materials.")
    parser.add_argument("--client", default=DEFAULT_CLIENT)
    parser.add_argument("--limit-notes", type=int, default=DEFAULT_LIMIT_NOTES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    return parser.parse_args(argv)


def load_source_profiles(client_slug: str) -> list[str]:
    workflow = common.load_yaml_file(common.get_client_workflow_path(client_slug))
    profiles = workflow.get("materials", {}).get("source_profiles") or []
    normalized: list[str] = []
    for profile in profiles:
        if isinstance(profile, dict):
            candidate = str(profile.get("url") or profile.get("share_url") or "").strip()
        elif isinstance(profile, str):
            candidate = profile.strip()
        else:
            candidate = ""
        if candidate:
            normalized.append(candidate)
    return normalized


def _jsonish(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _profile_key(source_profile_url: str) -> str:
    parsed = urlparse(source_profile_url)
    candidate = parsed.path.rstrip("/").split("/")[-1]
    if candidate:
        return common.slugify(candidate, limit=40)
    return common.slugify(parsed.netloc or "profile", limit=40)


def _image_extension(image_url: str | None) -> str:
    if not image_url:
        return ".jpg"
    suffix = Path(urlparse(image_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def build_note_record(
    client_slug: str,
    note: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    title = (note.get("title") or "untitled-note").strip()
    image_url = note.get("image_url")
    stem = f"{_profile_key(note.get('source_profile_url', 'profile'))}-{index:02d}-{common.slugify(title, limit=48)}"
    article_path = Path("clients") / client_slug / "references" / "article" / f"{stem}.md"
    image_path = None
    if image_url:
        image_path = (
            Path("clients")
            / client_slug
            / "references"
            / "images"
            / f"{stem}{_image_extension(str(image_url))}"
        )

    record = dict(note)
    record.setdefault("collected_via", COLLECTED_VIA)
    record.setdefault("access_level", PROFILE_CARD_ACCESS)
    record.setdefault("collection_note", PROFILE_CARD_NOTE)
    record["article_snapshot_path"] = article_path.as_posix()
    record["image_path"] = image_path.as_posix() if image_path else None
    return record


def build_note_markdown(note: dict[str, Any]) -> str:
    title = note.get("title") or "Untitled note snapshot"
    lines = [
        f"# {title}",
        "",
        f"- title: {_jsonish(note.get('title'))}",
        f"- author: {_jsonish(note.get('author'))}",
        f"- source_profile_url: {_jsonish(note.get('source_profile_url'))}",
        f"- collected_via: {_jsonish(note.get('collected_via'))}",
        f"- access_level: {_jsonish(note.get('access_level'))}",
        f"- note_url: {_jsonish(note.get('note_url'))}",
        f"- image_url: {_jsonish(note.get('image_url'))}",
        "",
        "## Collection Note",
        note.get("collection_note") or PROFILE_CARD_NOTE,
        "",
    ]
    return "\n".join(lines)


def _root_join(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    return common.ROOT_DIR / relative_path


def download_binary(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.read()
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        reason_text = str(reason)
        is_cert_error = isinstance(reason, ssl.SSLCertVerificationError) or (
            "CERTIFICATE_VERIFY_FAILED" in reason_text
            or "certificate verify failed" in reason_text.lower()
            or "self-signed certificate" in reason_text.lower()
        )
        if not is_cert_error:
            raise

    fallback_context = ssl._create_unverified_context()
    with urlopen(request, timeout=20, context=fallback_context) as response:
        return response.read()


def persist_note_record(
    note: dict[str, Any],
    downloader: DownloaderFunc = download_binary,
) -> dict[str, Any]:
    article_path = _root_join(note.get("article_snapshot_path"))
    if article_path is None:
        raise ValueError("note record missing article_snapshot_path")

    persisted = dict(note)
    common.save_text_file(article_path, build_note_markdown(persisted))

    image_path = _root_join(persisted.get("image_path"))
    image_url = persisted.get("image_url")
    if image_path and image_url:
        try:
            image_bytes = downloader(str(image_url))
            common.ensure_dir(image_path.parent)
            image_path.write_bytes(image_bytes)
            persisted["image_downloaded"] = True
        except Exception as exc:
            persisted["image_downloaded"] = False
            persisted["image_download_error"] = str(exc)
    else:
        persisted["image_downloaded"] = False

    return persisted


def determine_fetch_state(
    profile_results: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> str:
    states = {result.get("fetch_state") for result in profile_results}
    if notes:
        if any(note.get("access_level") != FULL_NOTE_ACCESS for note in notes):
            return "partial"
        if "blocked" in states or "partial" in states:
            return "partial"
        return "success"
    if "partial" in states:
        return "partial"
    if states and states <= {"blocked"}:
        return "blocked"
    return "blocked"


def build_source_index(
    configured_profiles: list[str],
    profile_results: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    updated_at: str,
) -> dict[str, Any]:
    return {
        "configured_profiles": configured_profiles,
        "profiles": profile_results,
        "notes": notes,
        "fetch_state": determine_fetch_state(profile_results, notes),
        "updated_at": updated_at,
    }


def is_cdp_available(cdp_url: str) -> bool:
    probe_url = cdp_url.rstrip("/")
    if not probe_url.endswith("/json/version"):
        probe_url = f"{probe_url}/json/version"
    try:
        with urlopen(probe_url, timeout=2):
            return True
    except (HTTPError, URLError, OSError):
        return False


def _extract_profile_cards(page: Any, limit_notes: int) -> list[dict[str, Any]]:
    script = """
    (limit) => {
      const normalize = (value) => {
        if (!value) return null;
        const text = String(value).replace(/\\s+/g, ' ').trim();
        return text || null;
      };
      const absolute = (value) => {
        if (!value) return null;
        try {
          return new URL(value, window.location.href).toString();
        } catch (_error) {
          return null;
        }
      };
      const cards = [];
      const seen = new Set();
      const sections = Array.from(document.querySelectorAll('section.note-item'));
      for (const section of sections) {
        const lines = (section.innerText || '')
          .split('\\n')
          .map((value) => normalize(value))
          .filter(Boolean);
        const title = lines[0] || null;
        const imageUrl = Array.from(section.querySelectorAll('img'))
          .map((img) => absolute(img.currentSrc || img.getAttribute('src') || img.getAttribute('data-src')))
          .find((url) => url && !url.startsWith('data:')) || null;
        const noteUrl = Array.from(section.querySelectorAll('a[href]'))
          .map((anchor) => absolute(anchor.getAttribute('href')))
          .find((url) => url && !/\\/explore\\/?$/i.test(url) && !/user\\/profile/i.test(url))
          || null;
        if (!title && !imageUrl) continue;

        const key = imageUrl || title || noteUrl;
        if (seen.has(key)) continue;
        seen.add(key);
        cards.push({
          title,
          note_url: noteUrl,
          image_url: imageUrl,
        });
        if (cards.length >= limit) break;
      }
      return cards;
    }
    """

    for _ in range(3):
        cards = page.evaluate(script, limit_notes) or []
        if len(cards) >= limit_notes:
            return cards[:limit_notes]
        page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 1200));")
        page.wait_for_timeout(800)
    return (cards or [])[:limit_notes]


def _extract_profile_author(page: Any) -> str | None:
    script = """
    () => {
      const normalize = (value) => {
        if (!value) return null;
        const text = String(value).replace(/\\s+/g, ' ').trim();
        return text || null;
      };
      const candidates = [
        document.querySelector('h1'),
        document.querySelector('[class*="user-name"]'),
        document.querySelector('[class*="username"]'),
        document.querySelector('[data-e2e="user-name"]'),
        document.querySelector('title'),
      ];
      for (const node of candidates) {
        if (!node) continue;
        const value = normalize(node.innerText || node.textContent);
        if (value) return value.replace(/\\s*[-|].*$/, '');
      }
      return null;
    }
    """
    return page.evaluate(script)


def _page_requires_login(page: Any) -> bool:
    script = """
    () => {
      const body = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
      const noteItems = document.querySelectorAll('section.note-item').length;
      return noteItems === 0 && /登录|立即登录|注册登录/i.test(body);
    }
    """
    return bool(page.evaluate(script))


def collect_profile_cards(
    profile_url: str,
    limit_notes: int,
    cdp_url: str,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - dependency failure
        return {
            "source_profile_url": profile_url,
            "fetch_state": "blocked",
            "blocked_reason": f"playwright_unavailable: {exc}",
            "notes": [],
        }

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            return {
                "source_profile_url": profile_url,
                "fetch_state": "blocked",
                "blocked_reason": "no_browser_context",
                "notes": [],
            }

        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2_000)
            cards = _extract_profile_cards(page, limit_notes)
            author = _extract_profile_author(page)
            current_url = page.url
            if not cards:
                blocked_reason = (
                    "login_required"
                    if "login" in current_url or _page_requires_login(page)
                    else "no_visible_profile_cards"
                )
                return {
                    "source_profile_url": profile_url,
                    "resolved_profile_url": current_url,
                    "author": author,
                    "fetch_state": "blocked",
                    "blocked_reason": blocked_reason,
                    "notes": [],
                }

            notes = []
            for card in cards:
                notes.append(
                    {
                        "title": card.get("title"),
                        "author": author,
                        "source_profile_url": profile_url,
                        "resolved_profile_url": current_url,
                        "collected_via": COLLECTED_VIA,
                        "access_level": PROFILE_CARD_ACCESS,
                        "note_url": card.get("note_url"),
                        "image_url": card.get("image_url"),
                        "collection_note": PROFILE_CARD_NOTE,
                    }
                )

            return {
                "source_profile_url": profile_url,
                "resolved_profile_url": current_url,
                "author": author,
                "fetch_state": "partial",
                "collected_via": COLLECTED_VIA,
                "notes": notes,
            }
        finally:
            page.close()


def _blocked_summary(
    client_slug: str,
    configured_profiles: list[str],
    blocked_reason: str,
    updated_at: str,
    dry_run: bool,
) -> dict[str, Any]:
    profiles = [
        {
            "source_profile_url": profile_url,
            "fetch_state": "blocked",
            "blocked_reason": blocked_reason,
            "notes": [],
        }
        for profile_url in configured_profiles
    ]
    return {
        "client": client_slug,
        "configured_profiles": configured_profiles,
        "profiles": profiles,
        "notes": [],
        "fetch_state": "blocked",
        "updated_at": updated_at,
        "dry_run": dry_run,
    }


def collect_materials(
    client_slug: str = DEFAULT_CLIENT,
    limit_notes: int = DEFAULT_LIMIT_NOTES,
    dry_run: bool = False,
    cdp_url: str = DEFAULT_CDP_URL,
    collector: CollectorFunc = collect_profile_cards,
    downloader: DownloaderFunc = download_binary,
    cdp_probe: ProbeFunc = is_cdp_available,
) -> dict[str, Any]:
    configured_profiles = load_source_profiles(client_slug)
    updated_at = common.timestamp()
    if not configured_profiles:
        return _blocked_summary(client_slug, [], "no_source_profiles", updated_at, dry_run)

    if not cdp_probe(cdp_url):
        return _blocked_summary(
            client_slug,
            configured_profiles,
            "cdp_unavailable",
            updated_at,
            dry_run,
        )

    profile_results: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for profile_url in configured_profiles:
        try:
            result = collector(profile_url, limit_notes, cdp_url)
        except Exception as exc:
            result = {
                "source_profile_url": profile_url,
                "fetch_state": "blocked",
                "blocked_reason": f"collector_error: {exc}",
                "notes": [],
            }
        profile_results.append(result)

        profile_notes = result.get("notes") or []
        if not isinstance(profile_notes, list):
            continue
        for index, note in enumerate(profile_notes, start=1):
            notes.append(build_note_record(client_slug, note, index))

    summary = build_source_index(configured_profiles, profile_results, notes, updated_at)
    summary["client"] = client_slug
    summary["dry_run"] = dry_run

    if dry_run or summary["fetch_state"] == "blocked":
        return summary

    persisted_notes = [persist_note_record(note, downloader=downloader) for note in notes]
    source_index = build_source_index(
        configured_profiles,
        profile_results,
        persisted_notes,
        updated_at,
    )
    source_index["client"] = client_slug
    source_index["dry_run"] = False

    source_index_path = common.get_client_root(client_slug) / "references" / "source-index.json"
    common.save_json_file(source_index_path, source_index)
    return source_index


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = collect_materials(
        client_slug=args.client,
        limit_notes=args.limit_notes,
        dry_run=args.dry_run,
        cdp_url=args.cdp_url,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["fetch_state"] == "blocked" and not args.dry_run:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
