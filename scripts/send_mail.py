from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def render_daily_summary_email(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    rows = payload.get("rows", [])
    lines = [
        "DNF 工具箱下载统计日报",
        "",
        f"统计时间：{summary.get('generated_at', '')}",
        f"工具总数：{_format_number(summary.get('tool_count', 0))}",
        f"版本包总数：{_format_number(summary.get('version_count', 0))}",
        f"总下载次数：{_format_number(summary.get('total_downloads', 0))}",
        f"今日新增下载：{_format_number(summary.get('daily_downloads', 0))}",
        f"统计异常：{_format_number(summary.get('issue_count', 0))}",
        "",
        "今日增长 Top 5：",
    ]

    top_daily = summary.get("top_daily", [])
    if top_daily:
        for index, item in enumerate(top_daily[:5], start=1):
            lines.append(
                f"{index}. {item.get('name', '')} {item.get('version', '')} "
                f"+{_format_number(item.get('daily_delta', 0))}"
            )
    else:
        lines.append("暂无新增下载。")

    issues = [row for row in rows if row.get("status") != "ok"]
    lines.extend(["", "异常详情："])
    if issues:
        for item in issues[:10]:
            lines.append(f"- {item.get('name', '')} {item.get('version', '')}: {item.get('error', '')}")
            package_url = item.get("package_url", "")
            if package_url:
                lines.append(f"  packageUrl: {package_url}")
    else:
        lines.append("暂无异常。")

    return "\n".join(lines).strip() + "\n"


def _format_number(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def subject_from_payload(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    return (
        "DNF 工具箱下载统计日报 "
        f"+{_format_number(summary.get('daily_downloads', 0))} / "
        f"{_format_number(summary.get('total_downloads', 0))}"
    )


def smtp_config_from_env() -> dict[str, str]:
    keys = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO"]
    return {key: os.environ.get(key, "") for key in keys}


def config_is_complete(config: dict[str, str]) -> bool:
    return all(config.get(key) for key in ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO"])


def send_email(payload: dict[str, Any], *, config: dict[str, str]) -> bool:
    if not config_is_complete(config):
        print("SMTP secrets are incomplete; skipping email.")
        return False

    message = EmailMessage()
    message["Subject"] = subject_from_payload(payload)
    message["From"] = config["MAIL_FROM"]
    message["To"] = config["MAIL_TO"]
    message.set_content(render_daily_summary_email(payload))

    port = int(config["SMTP_PORT"])
    if port == 465:
        with smtplib.SMTP_SSL(config["SMTP_HOST"], port, timeout=30) as server:
            server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
            server.send_message(message)
    else:
        with smtplib.SMTP(config["SMTP_HOST"], port, timeout=30) as server:
            server.starttls()
            server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
            server.send_message(message)
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send DNF toolbox download statistics email.")
    parser.add_argument("--stats", default="data/stats-latest.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = json.loads(Path(args.stats).read_text(encoding="utf-8"))
    send_email(payload, config=smtp_config_from_env())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
