from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, url2pathname, urlopen


DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/PhysicalWorldDo/DNFTOOLBOX-Registry/main/index.json"
USER_AGENT = "DNFTOOLBOX-Stats/1.0"
REQUEST_TIMEOUT_SECONDS = 30
CHINA_TIMEZONE = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class ReleaseAssetRef:
    owner: str
    repo: str
    tag: str
    asset: str


@dataclass
class StatRow:
    tool_id: str
    name: str
    category: str
    version: str
    channel: str
    package_url: str
    repo: str = ""
    tag: str = ""
    asset: str = ""
    downloads: int = 0
    daily_delta: int = 0
    size: int | None = None
    status: str = "pending"
    error: str = ""


def parse_github_release_asset_url(url: str) -> ReleaseAssetRef:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise ValueError("unsupported GitHub release URL")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 6 or parts[2:4] != ["releases", "download"]:
        raise ValueError("URL is not a GitHub release asset download URL")

    owner, repo, tag = parts[0], parts[1], parts[4]
    asset = "/".join(parts[5:])
    if not owner or not repo or not tag or not asset:
        raise ValueError("incomplete GitHub release asset URL")
    return ReleaseAssetRef(owner=owner, repo=repo, tag=tag, asset=asset)


def compute_daily_delta(current: StatRow, previous_rows: list[dict[str, Any]]) -> int:
    for previous in previous_rows:
        if (
            previous.get("tool_id") == current.tool_id
            and previous.get("version") == current.version
            and previous.get("asset") == current.asset
        ):
            previous_downloads = int(previous.get("downloads") or 0)
            return max(0, current.downloads - previous_downloads)
    return 0


def build_summary(rows: list[StatRow], generated_at: str) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.status == "ok"]
    issue_rows = [row for row in rows if row.status != "ok"]
    top_daily = sorted(ok_rows, key=lambda row: row.daily_delta, reverse=True)[:5]
    top_total = sorted(ok_rows, key=lambda row: row.downloads, reverse=True)[:5]
    return {
        "generated_at": generated_at,
        "tool_count": len({row.tool_id for row in rows}),
        "version_count": len(rows),
        "total_downloads": sum(row.downloads for row in ok_rows),
        "daily_downloads": sum(row.daily_delta for row in ok_rows),
        "issue_count": len(issue_rows),
        "top_daily": [stat_row_to_dict(row) for row in top_daily],
        "top_total": [stat_row_to_dict(row) for row in top_total],
    }


def stat_row_to_dict(row: StatRow) -> dict[str, Any]:
    return dataclasses.asdict(row)


def load_json_url(url: str, *, token: str = "") -> Any:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        return load_json_http(url, token=token)
    if parsed.scheme == "file":
        return json.loads(Path(url2pathname(parsed.path)).read_text(encoding="utf-8"))
    return json.loads(Path(url).read_text(encoding="utf-8"))


def load_json_http(url: str, *, token: str = "") -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(encoding))


def resolve_url(base_url: str, child_url: str) -> str:
    if urlparse(child_url).scheme:
        return child_url
    parsed = urlparse(base_url)
    if parsed.scheme in {"http", "https", "file"}:
        return urljoin(base_url, child_url)
    return str((Path(base_url).parent / child_url).resolve())


def collect_manifest_urls(index_data: dict[str, Any], index_url: str) -> list[dict[str, str]]:
    tools = []
    for item in index_data.get("tools", []):
        manifest_url = resolve_url(index_url, str(item["manifestUrl"]))
        tools.append(
            {
                "id": str(item["id"]),
                "name": str(item["name"]),
                "category": str(item.get("category", "")),
                "manifest_url": manifest_url,
            }
        )
    return tools


def rows_from_manifest(manifest: dict[str, Any]) -> list[StatRow]:
    rows: list[StatRow] = []
    for version in manifest.get("versions", []):
        rows.append(
            StatRow(
                tool_id=str(manifest.get("id", "")),
                name=str(manifest.get("name", "")),
                category=str(manifest.get("category", "")),
                version=str(version.get("version", "")),
                channel=str(version.get("channel", "stable")),
                package_url=str(version.get("packageUrl", "")),
                size=version.get("size"),
            )
        )
    return rows


def github_api_releases_url(repo: str, page: int = 1) -> str:
    owner, repo_name = repo.split("/", 1)
    return f"https://api.github.com/repos/{owner}/{repo_name}/releases?per_page=100&page={page}"


def fetch_repo_release_assets(repo: str, *, token: str = "") -> dict[tuple[str, str], dict[str, Any]]:
    assets: dict[tuple[str, str], dict[str, Any]] = {}
    page = 1
    while True:
        releases = load_json_http(github_api_releases_url(repo, page=page), token=token)
        if not releases:
            break
        for release in releases:
            tag = str(release.get("tag_name", ""))
            for asset in release.get("assets", []):
                asset_name = str(asset.get("name", ""))
                assets[(tag, asset_name)] = {
                    "downloads": int(asset.get("download_count") or 0),
                    "size": asset.get("size"),
                    "browser_download_url": asset.get("browser_download_url", ""),
                }
        page += 1
    return assets


def attach_release_stats(rows: list[StatRow], *, token: str = "") -> list[StatRow]:
    repo_cache: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for row in rows:
        if not row.package_url:
            row.status = "skipped"
            row.error = "empty packageUrl"
            continue

        try:
            parsed = parse_github_release_asset_url(row.package_url)
            row.repo = f"{parsed.owner}/{parsed.repo}"
            row.tag = parsed.tag
            row.asset = parsed.asset
        except ValueError as exc:
            row.status = "skipped"
            row.error = str(exc)
            continue

        try:
            if row.repo not in repo_cache:
                repo_cache[row.repo] = fetch_repo_release_assets(row.repo, token=token)
                time.sleep(0.1)
            asset = repo_cache[row.repo].get((row.tag, row.asset))
            if asset is None:
                row.status = "error"
                row.error = "asset_not_found"
                continue
            row.downloads = int(asset.get("downloads") or 0)
            row.size = asset.get("size") or row.size
            row.status = "ok"
            row.error = ""
        except HTTPError as exc:
            row.status = "error"
            row.error = f"github_http_{exc.code}"
        except (URLError, TimeoutError) as exc:
            row.status = "error"
            row.error = str(exc)
    return rows


def load_previous_rows(latest_path: Path) -> list[dict[str, Any]]:
    if not latest_path.exists():
        return []
    try:
        data = json.loads(latest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    rows = data.get("rows", [])
    return rows if isinstance(rows, list) else []


def apply_daily_deltas(rows: list[StatRow], previous_rows: list[dict[str, Any]]) -> None:
    for row in rows:
        row.daily_delta = compute_daily_delta(row, previous_rows)


def build_payload(rows: list[StatRow], generated_at: str) -> dict[str, Any]:
    return {
        "summary": build_summary(rows, generated_at=generated_at),
        "rows": [stat_row_to_dict(row) for row in rows],
    }


def write_payload(payload: dict[str, Any], *, data_dir: Path, public_dir: Path, generated_date: str) -> None:
    history_dir = data_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    public_dir.mkdir(parents=True, exist_ok=True)

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    (data_dir / "stats-latest.json").write_text(rendered + "\n", encoding="utf-8")
    (history_dir / f"{generated_date}.json").write_text(rendered + "\n", encoding="utf-8")
    (public_dir / "stats-latest.json").write_text(rendered + "\n", encoding="utf-8")


def refresh(index_url: str, *, data_dir: Path, public_dir: Path, token: str = "") -> dict[str, Any]:
    generated_at = datetime.now(CHINA_TIMEZONE).isoformat(timespec="seconds")
    generated_date = generated_at[:10]

    previous_rows = load_previous_rows(data_dir / "stats-latest.json")
    index_data = load_json_url(index_url, token=token)
    manifest_refs = collect_manifest_urls(index_data, index_url)

    rows: list[StatRow] = []
    for manifest_ref in manifest_refs:
        try:
            manifest = load_json_url(manifest_ref["manifest_url"], token=token)
            rows.extend(rows_from_manifest(manifest))
        except Exception as exc:
            rows.append(
                StatRow(
                    tool_id=manifest_ref["id"],
                    name=manifest_ref["name"],
                    category=manifest_ref["category"],
                    version="",
                    channel="",
                    package_url="",
                    status="error",
                    error=f"manifest_load_failed: {exc}",
                )
            )

    attach_release_stats(rows, token=token)
    apply_daily_deltas(rows, previous_rows)
    rows.sort(key=lambda row: (row.status != "ok", -row.downloads, row.name, row.version))

    payload = build_payload(rows, generated_at)
    write_payload(payload, data_dir=data_dir, public_dir=public_dir, generated_date=generated_date)
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh DNF toolbox release download statistics.")
    parser.add_argument("--index-url", default=os.environ.get("REGISTRY_INDEX_URL", DEFAULT_INDEX_URL))
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--public-dir", default="public")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = refresh(
        args.index_url,
        data_dir=Path(args.data_dir),
        public_dir=Path(args.public_dir),
        token=args.token,
    )
    summary = payload["summary"]
    print(
        "refreshed "
        f"{summary['version_count']} versions, "
        f"{summary['total_downloads']} total downloads, "
        f"{summary['daily_downloads']} daily downloads"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
