#!/usr/bin/env python3
"""
generate_leetcode_svg.py
Fetches live LeetCode statistics via the public GraphQL API and generates
a clean, minimalist green submission calendar SVG matching the exact style,
layout, and dimensions of the profile's contribution heatmap.
"""

import base64
import html
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

DEFAULT_USERNAME = "_prathamshettigar-123"
LEETCODE_USERNAME = os.environ.get("LEETCODE_USERNAME", DEFAULT_USERNAME).strip()
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
FONTS = os.path.join(REPO_ROOT, "fonts")
OUTPUT_PATH = os.environ.get(
    "OUTPUT_PATH", os.path.join(REPO_ROOT, "assets", "leetcode-dashboard.svg")
)
CARDS_PATH = os.path.join(REPO_ROOT, "cards", "leetcode.svg")

GRAPHQL_URL = "https://leetcode.com/graphql"
GRAPHQL_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    submissionCalendar
  }
}
"""

PAPER = "#f3f3f1"
PAPER_DEEP = "#e2e2de"
INK = "#111111"
MUTED = "#6e6e73"
LEET_GREEN = "#10b981"
W = 880

# 6-level green submission ramp matching Three Worlds paper & ink aesthetic
GREEN_RAMP = [PAPER_DEEP, "#a7f3d0", "#6ee7b7", "#34d399", "#10b981", "#047857"]

SERIF = "'Instrument Serif', Georgia, serif"
MONO = "'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

FONT_FILES = {
    "serif": ("Instrument Serif", "normal", 400, "serif-400.woff"),
    "serif-i": ("Instrument Serif", "italic", 400, "serif-italic.woff"),
    "mono": ("Geist Mono", "normal", 400, "geistmono-400.woff"),
}

BASE_CSS = """
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes pop{0%{opacity:0;transform:scale(.3)}70%{opacity:1;transform:scale(1.15)}100%{opacity:1;transform:none}}
.r{opacity:0;animation:rise .8s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box}
.f{opacity:0;animation:fade .9s ease-out both}
.p{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .4s ease-out both}
@media (prefers-reduced-motion: reduce){.r,.f,.p{animation:none!important;opacity:1!important;transform:none!important}}
"""


def font_face():
    out = []
    for k, (fam, style, weight, fn) in FONT_FILES.items():
        font_path = os.path.join(FONTS, fn)
        if os.path.exists(font_path):
            b64 = base64.b64encode(open(font_path, "rb").read()).decode()
            out.append(
                f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{weight};"
                f"src:url(data:font/woff;base64,{b64}) format('woff')}}"
            )
    return "".join(out)


def fetch_leetcode_data(username: str, max_retries: int = 3) -> dict:
    """Fetch user profile and calendar from LeetCode public GraphQL endpoint."""
    ctx = ssl.create_default_context()
    payload = json.dumps(
        {
            "query": GRAPHQL_QUERY,
            "variables": {"username": username},
        }
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": f"https://leetcode.com/{username}/",
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                GRAPHQL_URL, data=payload, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP status {resp.status}")
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)

            if "errors" in data and not data.get("data", {}).get("matchedUser"):
                raise RuntimeError(f"GraphQL errors: {data['errors']}")

            matched = data.get("data", {}).get("matchedUser")
            if not matched:
                raise ValueError(f"LeetCode user '{username}' was not found.")

            return matched

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as err:
            last_error = err
            print(f"[Warning] Attempt {attempt}/{max_retries} failed: {err}", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Failed to fetch LeetCode data after {max_retries} attempts: {last_error}")


def level_for(c: int) -> int:
    return 0 if c == 0 else 1 if c <= 2 else 2 if c <= 5 else 3 if c <= 10 else 4 if c <= 20 else 5


def generate_green_heatmap(matched_user: dict, username: str) -> str:
    """Generate a clean, pure green submission calendar SVG identical to heatmap.svg."""
    cal_raw = matched_user.get("submissionCalendar")
    cal_by_date = {}
    if cal_raw:
        try:
            cal_dict = json.loads(cal_raw)
            for ts_str, count in cal_dict.items():
                d = datetime.fromtimestamp(int(ts_str), tz=timezone.utc).date()
                cal_by_date[d] = int(count)
        except Exception as e:
            print(f"[Warning] Calendar parsing exception: {e}", file=sys.stderr)

    now = datetime.now(timezone.utc).date()
    days = []
    for i in range(366, -1, -1):
        d = now - timedelta(days=i)
        days.append({"date": d.strftime("%Y-%m-%d"), "count": cal_by_date.get(d, 0)})

    total_submissions = sum(d["count"] for d in days)
    first = date.fromisoformat(days[0]["date"])
    lead = (first.weekday() + 1) % 7  # sunday = 0
    cell, step, gx, gy = 12, 15, 44, 96
    cells, months, seen = [], [], set()

    for i, day in enumerate(days):
        k = i + lead
        col, row = divmod(k, 7)
        date_obj = date.fromisoformat(day["date"])
        if date_obj.day <= 7 and (date_obj.year, date_obj.month) not in seen and row == 0:
            seen.add((date_obj.year, date_obj.month))
            months.append((col, date_obj.strftime("%b")))
        c = day["count"]
        delay = 1.0 + col * 0.03 + row * 0.02
        cells.append(
            f'<rect class="p" style="animation-delay:{delay:.2f}s" x="{gx + col * step}" y="{gy + row * step}" '
            f'width="{cell}" height="{cell}" rx="3" fill="{GREEN_RAMP[level_for(c)]}">'
            f'<title>{day["date"]}: {c} submission{"s" if c != 1 else ""}</title></rect>'
        )

    ncols = (len(days) + lead + 6) // 7
    right = gx + ncols * step - 3
    labels = "".join(
        f'<text x="{gx + col * step}" y="{gy + 7 * step + 16}" font-family="{MONO}" font-size="11" fill="{MUTED}">{m}</text>'
        for col, m in months if col < ncols - 12
    )
    legend_x = right - len(GREEN_RAMP) * 14
    legend = "".join(
        f'<rect x="{legend_x + i * 14}" y="{gy + 7 * step + 6}" width="11" height="11" rx="2.5" fill="{c}"/>'
        for i, c in enumerate(GREEN_RAMP)
    )
    h = gy + 7 * step + 44
    label = f"LeetCode submissions: {total_submissions:,} submissions in the last year"

    css = font_face() + BASE_CSS
    body = f"""
<rect width="{W}" height="{h}" rx="14" fill="{PAPER}"/>
<text class="r" style="animation-delay:0.80s" x="42" y="62" font-family="{SERIF}" font-size="34" fill="{INK}">LeetCode submissions, <tspan font-style="italic" fill="{LEET_GREEN}">in green</tspan></text>
<text class="f" style="animation-delay:0.80s" x="{right}" y="60" text-anchor="end" font-family="{MONO}" font-size="12" letter-spacing="1" fill="{MUTED}">REFRESHED DAILY</text>
{''.join(cells)}
<g class="f" style="animation-delay:2.40s">{labels}
<text x="{legend_x - 8}" y="{gy + 7 * step + 16}" text-anchor="end" font-family="{MONO}" font-size="11" fill="{MUTED}">less</text>
{legend}
<text x="{legend_x + len(GREEN_RAMP) * 14 + 2}" y="{gy + 7 * step + 16}" font-family="{MONO}" font-size="11" fill="{MUTED}">more</text></g>
"""

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
        f'role="img" aria-label="{html.escape(label)}"><title>{html.escape(label)}</title>'
        f"<style>{css}</style>{body}</svg>"
    )


def main():
    print(f"[Info] Fetching LeetCode stats for '{LEETCODE_USERNAME}'...")
    try:
        matched_user = fetch_leetcode_data(LEETCODE_USERNAME)
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
        sys.exit(1)

    print("[Info] Generating green submission calendar SVG...")
    svg_content = generate_green_heatmap(matched_user, LEETCODE_USERNAME)

    # Write to assets/leetcode-dashboard.svg
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"[Success] Written: {OUTPUT_PATH} ({len(svg_content) // 1024} KB)")

    # Also write to cards/leetcode.svg
    os.makedirs(os.path.dirname(CARDS_PATH), exist_ok=True)
    with open(CARDS_PATH, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"[Success] Written: {CARDS_PATH} ({len(svg_content) // 1024} KB)")


if __name__ == "__main__":
    main()
