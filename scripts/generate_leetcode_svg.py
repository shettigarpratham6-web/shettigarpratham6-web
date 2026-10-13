#!/usr/bin/env python3
"""
generate_leetcode_svg.py
Fetches live LeetCode statistics via the public GraphQL API and generates
a premium, responsive, dark-themed SVG dashboard for GitHub profiles.
"""

import html
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

DEFAULT_USERNAME = "_prathamshettigar-123"
LEETCODE_USERNAME = os.environ.get("LEETCODE_USERNAME", DEFAULT_USERNAME).strip()
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.environ.get(
    "OUTPUT_PATH", os.path.join(REPO_ROOT, "assets", "leetcode-dashboard.svg")
)

GRAPHQL_URL = "https://leetcode.com/graphql"
GRAPHQL_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    username
    profile {
      ranking
      realName
    }
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
        submissions
      }
    }
    submissionCalendar
  }
  allQuestionsCount {
    difficulty
    count
  }
}
"""


def fetch_leetcode_data(username: str, max_retries: int = 3) -> tuple[dict, list]:
    """Fetch user profile and question totals from LeetCode public GraphQL endpoint."""
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

            all_questions = data.get("data", {}).get("allQuestionsCount", [])
            return matched, all_questions

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as err:
            last_error = err
            print(f"[Warning] Attempt {attempt}/{max_retries} failed: {err}", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Failed to fetch LeetCode data after {max_retries} attempts: {last_error}")


def get_heatmap_color(count: int) -> str:
    """Return dark-theme GitHub contribution color based on submission count."""
    if count <= 0:
        return "#161b22"
    elif count <= 2:
        return "#0e4429"
    elif count <= 5:
        return "#006d32"
    elif count <= 9:
        return "#26a641"
    else:
        return "#39d353"


def generate_svg(matched_user: dict, all_questions: list, username: str) -> str:
    """Generate a clean, responsive, dark-mode SVG dashboard."""
    # 1. AC Stats & Total Questions
    ac_map = {
        item.get("difficulty"): item
        for item in matched_user.get("submitStatsGlobal", {}).get("acSubmissionNum", [])
    }
    q_map = {item.get("difficulty"): item.get("count", 0) for item in all_questions}

    total_solved = ac_map.get("All", {}).get("count", 0)
    easy_solved = ac_map.get("Easy", {}).get("count", 0)
    med_solved = ac_map.get("Medium", {}).get("count", 0)
    hard_solved = ac_map.get("Hard", {}).get("count", 0)

    total_easy = q_map.get("Easy", 1) or 1
    total_med = q_map.get("Medium", 1) or 1
    total_hard = q_map.get("Hard", 1) or 1
    total_all = q_map.get("All", total_easy + total_med + total_hard) or (
        total_easy + total_med + total_hard
    )

    easy_subs = ac_map.get("Easy", {}).get("submissions", 0)
    med_subs = ac_map.get("Medium", {}).get("submissions", 0)
    hard_subs = ac_map.get("Hard", {}).get("submissions", 0)

    # 2. Ranking & User Info
    ranking = matched_user.get("profile", {}).get("ranking")
    rank_str = f"#{ranking:,}" if (ranking and ranking > 0) else "Unranked"

    # 3. Calendar & Streaks (Last 365 Days)
    cal_raw = matched_user.get("submissionCalendar")
    cal_by_date: dict[date, int] = {}
    heatmap_available = False
    active_days_year = 0
    total_subs_year = 0
    current_streak = 0
    max_streak = 0

    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    if cal_raw:
        try:
            cal_dict = json.loads(cal_raw)
            for ts_str, count in cal_dict.items():
                d = datetime.fromtimestamp(int(ts_str), tz=timezone.utc).date()
                cal_by_date[d] = int(count)
            heatmap_available = True

            days_365 = [today - timedelta(days=i) for i in range(365)]
            active_days_year = sum(1 for d in days_365 if cal_by_date.get(d, 0) > 0)
            total_subs_year = sum(cal_by_date.get(d, 0) for d in days_365)

            # Max streak in the past 365 days
            curr_run = 0
            for i in range(365, -1, -1):
                d = today - timedelta(days=i)
                if cal_by_date.get(d, 0) > 0:
                    curr_run += 1
                    if curr_run > max_streak:
                        max_streak = curr_run
                else:
                    curr_run = 0

            # Current active streak
            chk_d = today
            if cal_by_date.get(chk_d, 0) == 0:
                chk_d = today - timedelta(days=1)
            while cal_by_date.get(chk_d, 0) > 0:
                current_streak += 1
                chk_d -= timedelta(days=1)
        except Exception as e:
            print(f"[Warning] Calendar parsing exception: {e}", file=sys.stderr)
            heatmap_available = False

    # 4. Dimensions & Layout
    width = 820
    height = 430

    # Donut Ring (Radius 44, Circumference 276.46)
    circ = 276.4601
    cx, cy = 134, 150
    radius = 44

    donut_elements = []
    if total_solved > 0:
        items = [
            ("Easy", easy_solved, "#22c55e"),
            ("Medium", med_solved, "#f59e0b"),
            ("Hard", hard_solved, "#ef4444"),
        ]
        curr_angle = -90.0
        for name, cnt, color in items:
            if cnt <= 0:
                continue
            deg = (cnt / total_solved) * 360.0
            arc_len = (deg / 360.0) * circ
            donut_elements.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{color}" stroke-width="9" '
                f'stroke-dasharray="{arc_len:.2f} {circ:.2f}" stroke-linecap="butt" '
                f'transform="rotate({curr_angle:.2f} {cx} {cy})"/>'
            )
            curr_angle += deg
    else:
        donut_elements.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#21262d" stroke-width="9"/>'
        )

    # Progress bars
    bar_full_w = 490
    easy_bar_w = min(bar_full_w, max(2, int((easy_solved / total_easy) * bar_full_w)))
    med_bar_w = min(bar_full_w, max(2, int((med_solved / total_med) * bar_full_w)))
    hard_bar_w = min(bar_full_w, max(2, int((hard_solved / total_hard) * bar_full_w)))

    easy_pct = (easy_solved / total_easy * 100) if total_easy else 0.0
    med_pct = (med_solved / total_med * 100) if total_med else 0.0
    hard_pct = (hard_solved / total_hard * 100) if total_hard else 0.0
    total_pct = (total_solved / total_all * 100) if total_all else 0.0

    # Heatmap Grid (53 weeks x 7 days)
    # Sunday is row 0: gh_weekday = (d.weekday() + 1) % 7
    gh_today_wday = (today.weekday() + 1) % 7
    grid_end = today + timedelta(days=(6 - gh_today_wday))
    grid_start = grid_end - timedelta(days=(53 * 7 - 1))

    month_labels = []
    seen_months = set()
    heatmap_cells = []

    grid_origin_x = 68
    grid_origin_y = 296
    cell_size = 10
    step = 13  # 10px cell + 3px gap

    curr_d = grid_start
    for col in range(53):
        first_day_of_col = curr_d
        m_key = (first_day_of_col.year, first_day_of_col.month)
        if m_key not in seen_months and first_day_of_col.day <= 14:
            seen_months.add(m_key)
            m_name = first_day_of_col.strftime("%b")
            month_labels.append((grid_origin_x + col * step, m_name))

        for row in range(7):
            cnt = cal_by_date.get(curr_d, 0)
            cell_x = grid_origin_x + col * step
            cell_y = grid_origin_y + row * step

            if curr_d > today:
                fill_color = "transparent"
                border_attr = 'stroke="none"'
            else:
                fill_color = get_heatmap_color(cnt)
                border_attr = (
                    'stroke="#21262d" stroke-width="0.5"' if cnt == 0 else 'stroke="none"'
                )

            cell_date_str = curr_d.strftime("%Y-%m-%d")
            tooltip = f"{cell_date_str}: {cnt} submission{'s' if cnt != 1 else ''}"
            heatmap_cells.append(
                f'<rect x="{cell_x}" y="{cell_y}" width="{cell_size}" height="{cell_size}" rx="2" '
                f'fill="{fill_color}" {border_attr}><title>{html.escape(tooltip)}</title></rect>'
            )
            curr_d += timedelta(days=1)

    updated_time_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    profile_url = f"https://leetcode.com/{html.escape(username, quote=True)}"

    # Assemble SVG
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="LeetCode Profile Dashboard for {html.escape(username, quote=True)}">',
        '  <defs>',
        '    <linearGradient id="bg-grad" x1="0%" y1="0%" x2="100%" y2="100%">',
        '      <stop offset="0%" stop-color="#0d1117" />',
        '      <stop offset="100%" stop-color="#141922" />',
        '    </linearGradient>',
        '    <linearGradient id="card-grad" x1="0%" y1="0%" x2="0%" y2="100%">',
        '      <stop offset="0%" stop-color="#161b22" />',
        '      <stop offset="100%" stop-color="#13171f" />',
        '    </linearGradient>',
        '    <linearGradient id="easy-grad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '      <stop offset="0%" stop-color="#22c55e" />',
        '      <stop offset="100%" stop-color="#4ade80" />',
        '    </linearGradient>',
        '    <linearGradient id="med-grad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '      <stop offset="0%" stop-color="#f59e0b" />',
        '      <stop offset="100%" stop-color="#fbbf24" />',
        '    </linearGradient>',
        '    <linearGradient id="hard-grad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '      <stop offset="0%" stop-color="#ef4444" />',
        '      <stop offset="100%" stop-color="#f87171" />',
        '    </linearGradient>',
        '  </defs>',
        '',
        '  <!-- Background Canvas -->',
        f'  <rect width="{width}" height="{height}" rx="14" fill="url(#bg-grad)" stroke="#30363d" stroke-width="1.2" />',
        '',
        '  <!-- Header Bar -->',
        '  <g transform="translate(24, 22)">',
        f'    <a href="{profile_url}" target="_blank">',
        '      <svg width="26" height="26" viewBox="0 0 24 24" fill="none">',
        '        <path d="M16.102 17.93l-2.697 2.607c-.466.467-1.111.72-1.77.72-.66 0-1.305-.253-1.771-.72l-4.102-4.1c-.976-.976-.976-2.56 0-3.536L9.864 8.8c.466-.467 1.111-.72 1.77-.72.66 0 1.305.253 1.771.72l2.697 2.607c.45.435 1.168.423 1.603-.027.435-.45.423-1.168-.027-1.603l-2.697-2.607c-.893-.894-2.126-1.38-3.417-1.38-1.29 0-2.524.486-3.417 1.38L4.048 11.88c-1.884 1.884-1.884 4.94 0 6.824l4.102 4.1c.893.894 2.127 1.38 3.418 1.38 1.29 0 2.524-.486 3.417-1.38l2.697-2.607c.45-.435.462-1.153.027-1.603-.435-.45-1.153-.462-1.607-.027z" fill="#FFA116"/>',
        '        <path d="M20.811 13.01H10.606c-.626 0-1.134-.508-1.134-1.134 0-.626.508-1.134 1.134-1.134h10.205c.626 0 1.134.508 1.134 1.134 0 .626-.508 1.134-1.134 1.134z" fill="#8b949e"/>',
        '      </svg>',
        '    </a>',
        '    <text x="34" y="19" fill="#f0f6fc" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="17" font-weight="700">LeetCode Profile</text>',
        f'    <a href="{profile_url}" target="_blank">',
        f'      <text x="176" y="19" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="12.5" font-weight="500">@{html.escape(username)}</text>',
        '    </a>',
        '',
        '    <!-- Global Rank Badge -->',
        '    <g transform="translate(360, 2)">',
        '      <rect width="168" height="24" rx="12" fill="#21262d" stroke="#30363d" stroke-width="1"/>',
        '      <circle cx="12" cy="12" r="4" fill="#FFA116"/>',
        f'      <text x="24" y="16.5" fill="#f0f6fc" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11.5" font-weight="600">Global Rank: <tspan fill="#FFA116">{rank_str}</tspan></text>',
        '    </g>',
        '',
        '    <!-- Last Updated Time -->',
        f'    <text x="772" y="18" text-anchor="end" fill="#7d8590" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11">Updated {updated_time_str}</text>',
        '  </g>',
        '',
        '  <line x1="24" y1="58" x2="796" y2="58" stroke="#21262d" stroke-width="1"/>',
        '',
        '  <!-- Top Metrics Row -->',
        '  <!-- Card 1: Total Solved Donut Chart -->',
        '  <rect x="24" y="72" width="220" height="150" rx="10" fill="url(#card-grad)" stroke="#30363d" stroke-width="1"/>',
        '  <text x="40" y="94" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11" font-weight="600" letter-spacing="0.5">PROBLEMS SOLVED</text>',
        '  <g>',
        f'    <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#21262d" stroke-width="9"/>',
        '    ' + '\n    '.join(donut_elements),
        f'    <text x="{cx}" y="{cy - 3}" text-anchor="middle" fill="#f0f6fc" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="22" font-weight="700">{total_solved:,}</text>',
        f'    <text x="{cx}" y="{cy + 13}" text-anchor="middle" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="10.5">/ {total_all:,}</text>',
        f'    <text x="{cx}" y="{cy + 42}" text-anchor="middle" fill="#FFA116" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11" font-weight="600">{total_pct:.1f}% Solved</text>',
        '  </g>',
        '',
        '  <!-- Card 2: Difficulty Breakdown Bars -->',
        '  <rect x="256" y="72" width="540" height="150" rx="10" fill="url(#card-grad)" stroke="#30363d" stroke-width="1"/>',
        '',
        '  <!-- Easy Row -->',
        '  <g transform="translate(276, 88)">',
        '    <rect width="52" height="18" rx="9" fill="rgba(34, 197, 94, 0.15)" stroke="rgba(34, 197, 94, 0.3)" stroke-width="1"/>',
        '    <text x="26" y="13" text-anchor="middle" fill="#22c55e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="700">Easy</text>',
        f'    <text x="68" y="14" fill="#f0f6fc" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="12" font-weight="600">{easy_solved:,} <tspan fill="#8b949e" font-weight="400">/ {total_easy:,}</tspan></text>',
        f'    <text x="{bar_full_w}" y="14" text-anchor="end" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11">{easy_pct:.1f}% · {easy_subs:,} subs</text>',
        f'    <rect x="0" y="24" width="{bar_full_w}" height="8" rx="4" fill="#21262d"/>',
        f'    <rect x="0" y="24" width="{easy_bar_w}" height="8" rx="4" fill="url(#easy-grad)"/>',
        '  </g>',
        '',
        '  <!-- Medium Row -->',
        '  <g transform="translate(276, 134)">',
        '    <rect width="64" height="18" rx="9" fill="rgba(245, 158, 11, 0.15)" stroke="rgba(245, 158, 11, 0.3)" stroke-width="1"/>',
        '    <text x="32" y="13" text-anchor="middle" fill="#f59e0b" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="700">Medium</text>',
        f'    <text x="78" y="14" fill="#f0f6fc" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="12" font-weight="600">{med_solved:,} <tspan fill="#8b949e" font-weight="400">/ {total_med:,}</tspan></text>',
        f'    <text x="{bar_full_w}" y="14" text-anchor="end" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11">{med_pct:.1f}% · {med_subs:,} subs</text>',
        f'    <rect x="0" y="24" width="{bar_full_w}" height="8" rx="4" fill="#21262d"/>',
        f'    <rect x="0" y="24" width="{med_bar_w}" height="8" rx="4" fill="url(#med-grad)"/>',
        '  </g>',
        '',
        '  <!-- Hard Row -->',
        '  <g transform="translate(276, 180)">',
        '    <rect width="52" height="18" rx="9" fill="rgba(239, 68, 68, 0.15)" stroke="rgba(239, 68, 68, 0.3)" stroke-width="1"/>',
        '    <text x="26" y="13" text-anchor="middle" fill="#ef4444" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="10.5" font-weight="700">Hard</text>',
        f'    <text x="68" y="14" fill="#f0f6fc" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="12" font-weight="600">{hard_solved:,} <tspan fill="#8b949e" font-weight="400">/ {total_hard:,}</tspan></text>',
        f'    <text x="{bar_full_w}" y="14" text-anchor="end" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11">{hard_pct:.1f}% · {hard_subs:,} subs</text>',
        f'    <rect x="0" y="24" width="{bar_full_w}" height="8" rx="4" fill="#21262d"/>',
        f'    <rect x="0" y="24" width="{hard_bar_w}" height="8" rx="4" fill="url(#hard-grad)"/>',
        '  </g>',
        '',
        '  <!-- Activity Heatmap Container -->',
        '  <rect x="24" y="234" width="772" height="180" rx="10" fill="url(#card-grad)" stroke="#30363d" stroke-width="1"/>',
        '',
        '  <!-- Heatmap Header -->',
        '  <g transform="translate(40, 252)">',
        '    <text x="0" y="11" fill="#f0f6fc" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="12" font-weight="700">SUBMISSION ACTIVITY</text>',
    ]

    if heatmap_available:
        lines.extend([
            f'    <text x="170" y="11" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11">'
            f'<tspan fill="#39d353" font-weight="600">{total_subs_year:,}</tspan> submissions in past year  ·  '
            f'<tspan fill="#f0f6fc" font-weight="600">{active_days_year}</tspan> active days  ·  '
            f'Current streak: <tspan fill="#FFA116" font-weight="600">{current_streak}d</tspan>  ·  '
            f'Max streak: <tspan fill="#f0f6fc">{max_streak}d</tspan>'
            f'</text>',
            '  </g>',
            '',
            '  <!-- Heatmap Month Labels -->',
            '  <g>',
        ])
        for mx, mname in month_labels:
            lines.append(
                f'    <text x="{mx}" y="286" fill="#7d8590" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="9.5">{mname}</text>'
            )
        lines.extend([
            '  </g>',
            '',
            '  <!-- Heatmap Day of Week Labels -->',
            '  <g fill="#7d8590" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="9" text-anchor="end">',
            f'    <text x="60" y="{grid_origin_y + 1 * step + 8}">Mon</text>',
            f'    <text x="60" y="{grid_origin_y + 3 * step + 8}">Wed</text>',
            f'    <text x="60" y="{grid_origin_y + 5 * step + 8}">Fri</text>',
            '  </g>',
            '',
            '  <!-- Heatmap Grid Cells -->',
            '  <g>',
            '    ' + '\n    '.join(heatmap_cells),
            '  </g>',
            '',
            '  <!-- Heatmap Legend -->',
            '  <g transform="translate(620, 396)">',
            '    <text x="-8" y="9" text-anchor="end" fill="#7d8590" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="9.5">Less</text>',
            '    <rect x="0" y="0" width="10" height="10" rx="2" fill="#161b22" stroke="#21262d" stroke-width="0.5"/>',
            '    <rect x="14" y="0" width="10" height="10" rx="2" fill="#0e4429"/>',
            '    <rect x="28" y="0" width="10" height="10" rx="2" fill="#006d32"/>',
            '    <rect x="42" y="0" width="10" height="10" rx="2" fill="#26a641"/>',
            '    <rect x="56" y="0" width="10" height="10" rx="2" fill="#39d353"/>',
            '    <text x="74" y="9" fill="#7d8590" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="9.5">More</text>',
            '  </g>',
        ])
    else:
        lines.extend([
            '    <text x="170" y="11" fill="#8b949e" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="11">Calendar data currently unavailable</text>',
            '  </g>',
            '  <text x="410" y="334" text-anchor="middle" fill="#7d8590" font-family="-apple-system, BlinkMacSystemFont, \'Segoe UI\', Helvetica, Arial, sans-serif" font-size="13">Submission activity heatmap data is not publicly accessible.</text>',
        ])

    lines.append('</svg>')
    return '\n'.join(lines)


def main():
    print(f"[Info] Fetching LeetCode stats for '{LEETCODE_USERNAME}'...")
    try:
        matched, all_questions = fetch_leetcode_data(LEETCODE_USERNAME)
    except Exception as exc:
        print(f"[Error] Failed to fetch LeetCode data: {exc}", file=sys.stderr)
        sys.exit(1)

    print("[Info] Generating SVG dashboard...")
    svg_output = generate_svg(matched, all_questions, LEETCODE_USERNAME)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg_output)

    print(f"[Success] Dashboard successfully generated at: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
