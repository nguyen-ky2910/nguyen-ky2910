"""Build SVG charts from public GitHub activity."""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import escape, unescape
from pathlib import Path
import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

USER = "nguyen-ky2910"
PROJECTS = {
    "GEMM_32x32_KV260_AI_ACCELERATOR": ("GEMM FPGA", "#82aaff"),
    "GEMM_ASIC_SKY130": ("GEMM ASIC", "#6de4c1"),
    "RISC_V_CPU": ("RISC-V CPU", "#e0a1ff"),
}
OUTPUT = Path(__file__).resolve().parents[1] / "assets"
TODAY = datetime.now(timezone.utc).date()
WEEKS = 16
STATS_PROVIDER = "https://github-readme-stats.vercel.app/api"
STYLE = "theme=tokyonight&hide_border=true"
CARDS = {
    "stats.svg": f"{STATS_PROVIDER}?username={USER}&show_icons=true&rank_icon=github&{STYLE}",
    "languages.svg": f"{STATS_PROVIDER}/top-langs/?username={USER}&layout=compact&langs_count=8&{STYLE}",
    "streak.svg": f"https://streak-stats.demolab.com/?user={USER}&{STYLE}",
}


def fetch(url):
    headers = {"User-Agent": "github-profile-charts"}
    if url.startswith("https://api.github.com/"):
        headers["Accept"] = "application/vnd.github+json"
        if token := os.environ.get("PROFILE_GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=25) as response:
        return response.read().decode("utf-8")


def svg(width, height, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img"><title>{escape(title)}</title>'
        f'<rect width="{width}" height="{height}" rx="16" fill="#111827"/>'
        '<g font-family="system-ui, sans-serif" fill="#cbd5e1">'
        + "".join(body) + "</g></svg>\n"
    )


def label(x, y, value, size=13, anchor="start", color="#cbd5e1"):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="{color}">{escape(str(value))}</text>'
    )


def weekly_activity():
    monday = TODAY - timedelta(days=TODAY.weekday())
    start = monday - timedelta(weeks=WEEKS - 1)
    labels = [start + timedelta(weeks=i) for i in range(WEEKS)]
    series = {}
    for repo in PROJECTS:
        counts = Counter()
        page = 1
        while True:
            url = (
                f"https://api.github.com/repos/{USER}/{repo}/commits"
                f"?since={start}T00:00:00Z&per_page=100&page={page}"
            )
            commits = json.loads(fetch(url))
            if not isinstance(commits, list):
                raise ValueError(f"Unexpected commits response for {repo}")
            for commit in commits:
                day = date.fromisoformat(commit["commit"]["committer"]["date"][:10])
                week = (day - start).days // 7
                if 0 <= week < len(labels):
                    counts[week] += 1
            if len(commits) < 100:
                break
            page += 1
        series[repo] = [counts[i] for i in range(len(labels))]
    return labels, series


def activity_chart(weeks, series):
    peak = max(max(counts) for counts in series.values())
    step = max(1, (peak + 3) // 4)
    chart_height, baseline = 132, 205
    body = [
        label(32, 35, "Commit activity by repository", 22, color="#f1f5f9"),
        label(32, 57, f"Default branches · {WEEKS} weeks · current week in progress"),
    ]
    for tick in range(5):
        y = baseline - chart_height * tick / 4
        body.append(f'<path d="M52 {y}H870" stroke="#344156"/>')
        body.append(label(42, y + 4, tick * step, 12, "end"))
    for i, week in enumerate(weeks):
        x = 61 + i * 51
        if i % 2 == 0:
            body.append(label(x + 18, 228, week.strftime("%d %b"), 12, "middle"))
        for j, (repo, (name, color)) in enumerate(PROJECTS.items()):
            count = series[repo][i]
            if count:
                height = count * chart_height / (4 * step)
                body.append(
                    f'<rect x="{x + j * 13}" y="{baseline - height:.1f}" width="10" '
                    f'height="{height:.1f}" rx="2" fill="{color}">'
                    f'<title>{escape(name)}: {count} commits, week of {week}</title></rect>'
                )
    for j, (name, color) in enumerate(PROJECTS.values()):
        x = 32 + j * 168
        body.append(f'<circle cx="{x + 5}" cy="254" r="5" fill="{color}"/>')
        body.append(label(x + 18, 258, name))
    return svg(900, 278, "Commit activity across selected public repositories", body)


def contribution_days():
    page = fetch(f"https://github.com/users/{USER}/contributions")
    labels = {}
    for attrs, content in re.findall(r"<tool-tip\b([^>]*)>(.*?)</tool-tip>", page, re.S):
        target = re.search(r'\bfor="([^"]+)"', attrs)
        count = re.match(r"\s*(No|[\d,]+) contributions? on\b", unescape(content))
        if target and count:
            value = count.group(1)
            labels[target.group(1)] = 0 if value == "No" else int(value.replace(",", ""))
    counts = {}
    for attrs in re.findall(r"<td\b([^>]*)>", page):
        day = re.search(r'\bdata-date="([\d-]+)"', attrs)
        cell = re.search(r'\bid="([^"]+)"', attrs)
        if day and cell and cell.group(1) in labels:
            counts[date.fromisoformat(day.group(1))] = labels[cell.group(1)]
    if not 360 <= len(counts) <= 372 or (max(counts) - min(counts)).days + 1 != len(counts):
        raise ValueError("Incomplete GitHub contribution calendar")
    return counts


def landscape_chart(counts):
    start, end = min(counts), max(counts)
    sunday = start - timedelta(days=(start.weekday() + 1) % 7)
    peak = max(max(counts.values()), 1)
    body = [
        label(30, 34, "Contribution landscape", 22, color="#f1f5f9"),
        label(30, 56, f"{start:%d %b %Y} – {end:%d %b %Y} · {sum(counts.values())} contributions"),
    ]
    # Draw from back to front so each column can occlude the ones behind it.
    for day in sorted(counts, key=lambda day: (day - sunday).days % 7):
        week, weekday = divmod((day - sunday).days, 7)
        x, y = 32 + 15 * week + 6 * weekday, 141 + 9 * weekday
        count = counts[day]
        top = y - (4 + 49 * (count / peak) ** 0.65 if count else 0)
        cap, front, side = ("#a7f3d0", "#189675", "#106b61") if count else ("#27364a", "", "")
        body.append(f'<g><title>{day}: {count} contributions</title>')
        if count:
            body.append(f'<path d="M{x} {top}l12 0v{y-top}h-12z" fill="{front}"/>')
            body.append(f'<path d="M{x+12} {top}l5 -4v{y-top}l-5 4z" fill="{side}"/>')
        body.append(f'<path d="M{x} {top}l5 -4h12l-5 4z" fill="{cap}"/></g>')
    for day in counts:
        if day.day == 1 and (day - start).days >= 14:
            x = 32 + 15 * ((day - sunday).days // 7)
            body.append(label(x, 221, day.strftime("%b"), 12))
    body.append(label(30, 249, "Each tile represents one day. Taller columns show more contributions.", 12))
    return svg(900, 266, "Annual GitHub contribution activity in 3D", body)


def refresh_cards():
    for name, url in CARDS.items():
        try:
            content = fetch(url)
            root = ElementTree.fromstring(content)
            if root.tag != "{http://www.w3.org/2000/svg}svg":
                raise ValueError("Expected an SVG image")
            if any(
                node.tag.rsplit("}", 1)[-1] in {"script", "foreignObject"}
                or any(
                    key.rsplit("}", 1)[-1].startswith("on")
                    or (key.rsplit("}", 1)[-1] == "href" and not value.startswith("#"))
                    for key, value in node.attrib.items()
                )
                for node in root.iter()
            ):
                raise ValueError("Unexpected active SVG content")
            errors = r"rate limit|something went wrong|maximum retries|please try again|error fetching"
            if re.search(errors, content, re.I):
                raise ValueError("Provider returned an error image")
            normalized = "\n".join(line.rstrip() for line in content.splitlines()).strip() + "\n"
            (OUTPUT / name).write_text(normalized, encoding="utf-8", newline="\n")
        except (URLError, TimeoutError, ElementTree.ParseError, ValueError) as error:
            print(f"Keeping previous {name}: {error}")


def main():
    weeks, series = weekly_activity()
    counts = contribution_days()
    charts = {
        "project-activity.svg": activity_chart(weeks, series),
        "contributions-3d.svg": landscape_chart(counts),
        "project-activity.json": json.dumps(
            {"week_start_utc": [str(week) for week in weeks], "commits": series},
            indent=2,
        ) + "\n",
    }
    OUTPUT.mkdir(exist_ok=True)
    for name, content in charts.items():
        (OUTPUT / name).write_text(content, encoding="utf-8", newline="\n")
    refresh_cards()


if __name__ == "__main__":
    main()
