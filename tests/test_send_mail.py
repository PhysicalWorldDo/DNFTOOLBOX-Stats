from scripts import send_mail


def test_render_daily_summary_email_includes_totals_and_issues() -> None:
    payload = {
        "summary": {
            "generated_at": "2026-06-28T09:00:00+08:00",
            "tool_count": 12,
            "version_count": 34,
            "total_downloads": 15890,
            "daily_downloads": 128,
            "issue_count": 1,
            "top_daily": [
                {"name": "DNF IMG 替换工具", "version": "1.0.1", "daily_delta": 42},
                {"name": "DNF 音乐检测工具", "version": "1.0.0", "daily_delta": 31},
            ],
        },
        "rows": [
            {
                "name": "某个工具",
                "version": "1.0.0",
                "status": "error",
                "error": "asset_not_found",
                "package_url": "https://github.com/org/repo/releases/download/v1/missing.zip",
            }
        ],
    }

    body = send_mail.render_daily_summary_email(payload)

    assert "DNF 工具箱下载统计日报" in body
    assert "总下载次数：15,890" in body
    assert "今日新增下载：128" in body
    assert "DNF IMG 替换工具 1.0.1 +42" in body
    assert "某个工具 1.0.0: asset_not_found" in body
