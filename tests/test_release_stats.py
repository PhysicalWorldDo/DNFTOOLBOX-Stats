from scripts import refresh_stats


def test_parse_github_release_asset_url() -> None:
    parsed = refresh_stats.parse_github_release_asset_url(
        "https://github.com/PhysicalWorldDo/DNF-IMG-Replacer/"
        "releases/download/v1.0.1/dnf_img_replacer-1.0.1-win-x64.zip"
    )

    assert parsed.owner == "PhysicalWorldDo"
    assert parsed.repo == "DNF-IMG-Replacer"
    assert parsed.tag == "v1.0.1"
    assert parsed.asset == "dnf_img_replacer-1.0.1-win-x64.zip"


def test_parse_github_release_asset_url_handles_encoded_asset_names() -> None:
    parsed = refresh_stats.parse_github_release_asset_url(
        "https://github.com/org/repo/releases/download/v2.0.0/tool%20package.zip"
    )

    assert parsed.asset == "tool package.zip"


def test_compute_daily_delta_matches_previous_asset() -> None:
    current = refresh_stats.StatRow(
        tool_id="dnf_img_replacer",
        name="DNF IMG Replacer",
        category="IMG",
        version="1.0.1",
        channel="stable",
        package_url="https://github.com/org/repo/releases/download/v1/tool.zip",
        repo="org/repo",
        tag="v1",
        asset="tool.zip",
        downloads=150,
        size=1000,
        status="ok",
        error="",
    )
    previous = [
        {
            "tool_id": "dnf_img_replacer",
            "version": "1.0.1",
            "asset": "tool.zip",
            "downloads": 120,
        }
    ]

    assert refresh_stats.compute_daily_delta(current, previous) == 30


def test_compute_daily_delta_never_goes_negative() -> None:
    current = refresh_stats.StatRow(
        tool_id="dnf_img_replacer",
        name="DNF IMG Replacer",
        category="IMG",
        version="1.0.1",
        channel="stable",
        package_url="https://github.com/org/repo/releases/download/v1/tool.zip",
        repo="org/repo",
        tag="v1",
        asset="tool.zip",
        downloads=80,
        size=1000,
        status="ok",
        error="",
    )
    previous = [
        {
            "tool_id": "dnf_img_replacer",
            "version": "1.0.1",
            "asset": "tool.zip",
            "downloads": 120,
        }
    ]

    assert refresh_stats.compute_daily_delta(current, previous) == 0


def test_build_summary_totals_and_top_lists() -> None:
    rows = [
        refresh_stats.StatRow(
            tool_id="a",
            name="Tool A",
            category="Cat",
            version="1.0.0",
            channel="stable",
            package_url="https://github.com/org/a/releases/download/v1/a.zip",
            repo="org/a",
            tag="v1",
            asset="a.zip",
            downloads=200,
            daily_delta=40,
            size=100,
            status="ok",
            error="",
        ),
        refresh_stats.StatRow(
            tool_id="b",
            name="Tool B",
            category="Cat",
            version="1.0.0",
            channel="stable",
            package_url="https://github.com/org/b/releases/download/v1/b.zip",
            repo="org/b",
            tag="v1",
            asset="b.zip",
            downloads=500,
            daily_delta=10,
            size=100,
            status="ok",
            error="",
        ),
        refresh_stats.StatRow(
            tool_id="bad",
            name="Bad Tool",
            category="Cat",
            version="1.0.0",
            channel="stable",
            package_url="",
            repo="",
            tag="",
            asset="",
            downloads=0,
            daily_delta=0,
            size=None,
            status="skipped",
            error="empty packageUrl",
        ),
    ]

    summary = refresh_stats.build_summary(rows, generated_at="2026-06-28T09:00:00+08:00")

    assert summary["tool_count"] == 3
    assert summary["version_count"] == 3
    assert summary["total_downloads"] == 700
    assert summary["daily_downloads"] == 50
    assert summary["issue_count"] == 1
    assert summary["top_daily"][0]["tool_id"] == "a"
    assert summary["top_total"][0]["tool_id"] == "b"


def test_fetch_repo_release_assets_reads_all_pages(monkeypatch) -> None:
    calls = []

    def fake_load_json_http(url: str, *, token: str = ""):
        calls.append(url)
        if url.endswith("page=1"):
            return [
                {
                    "tag_name": "v2",
                    "assets": [
                        {
                            "name": "new.zip",
                            "download_count": 20,
                            "size": 200,
                            "browser_download_url": "https://github.com/org/repo/releases/download/v2/new.zip",
                        }
                    ],
                }
            ]
        if url.endswith("page=2"):
            return [
                {
                    "tag_name": "v1",
                    "assets": [
                        {
                            "name": "old.zip",
                            "download_count": 5,
                            "size": 100,
                            "browser_download_url": "https://github.com/org/repo/releases/download/v1/old.zip",
                        }
                    ],
                }
            ]
        return []

    monkeypatch.setattr(refresh_stats, "load_json_http", fake_load_json_http)

    assets = refresh_stats.fetch_repo_release_assets("org/repo")

    assert assets[("v2", "new.zip")]["downloads"] == 20
    assert assets[("v1", "old.zip")]["downloads"] == 5
    assert calls == [
        "https://api.github.com/repos/org/repo/releases?per_page=100&page=1",
        "https://api.github.com/repos/org/repo/releases?per_page=100&page=2",
        "https://api.github.com/repos/org/repo/releases?per_page=100&page=3",
    ]
