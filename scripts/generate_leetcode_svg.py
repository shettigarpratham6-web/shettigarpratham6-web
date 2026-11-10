#!/usr/bin/env python3
"""
generate_leetcode_svg.py
Fetches live LeetCode statistics via the public GraphQL API and generates
a cohesive SVG dashboard styled in the Three Worlds paper & ink design system.
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

FONT_FILES = {
    "serif": ("Instrument Serif", "normal", 400, "serif-400.woff"),
    "serif-i": ("Instrument Serif", "italic", 400, "serif-italic.woff"),
    "sans": ("Geist", "normal", 400, "geist-400.woff"),
    "sans-b": ("Geist", "normal", 600, "geist-600.woff"),
    "mono": ("Geist Mono", "normal", 400, "geistmono-400.woff"),
}


def font_face_css():
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


# Warm paper palette for submission heatmap
PAPER_EMPTY = "#e2e2de"
LEET_ORANGE = ["#fed7aa", "#fb923c", "#f97316", "#ea580c"]


def get_heatmap_color(count: int) -> str:
    """Return paper-themed color based on submission count."""
    if count <= 0:
        return PAPER_EMPTY
    elif count <= 2:
        return LEET_ORANGE[0]
    elif count <= 5:
        return LEET_ORANGE[1]
    elif count <= 9:
        return LEET_ORANGE[2]
    else:
        return LEET_ORANGE[3]


def generate_svg(matched_user: dict, all_questions: list, username: str) -> str:
    """Generate a clean, responsive, editorial paper & ink SVG dashboard matching 880px width."""
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

            # Max streak in past 365 days
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

    # 4. Canvas dimensions & layout - standard 880px matching profile cards
    width = 880
    height = 430

    # Donut Ring (Radius 42, Circumference 263.89)
    circ = 263.8938
    cx, cy = 145, 150
    radius = 42

    donut_elements = []
    if total_solved > 0:
        items = [
            ("Easy", easy_solved, "#10b981"),
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
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{color}" stroke-width="8" '
                f'stroke-dasharray="{arc_len:.2f} {circ:.2f}" stroke-linecap="butt" '
                f'transform="rotate({curr_angle:.2f} {cx} {cy})"/>'
            )
            curr_angle += deg
    else:
        donut_elements.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#e2e2de" stroke-width="8"/>'
        )

    # Progress bars
    bar_full_w = 480
    easy_bar_w = min(bar_full_w, max(4, int((easy_solved / total_easy) * bar_full_w)))
    med_bar_w = min(bar_full_w, max(4, int((med_solved / total_med) * bar_full_w)))
    hard_bar_w = min(bar_full_w, max(4, int((hard_solved / total_hard) * bar_full_w)))

    easy_pct = (easy_solved / total_easy * 100) if total_easy else 0.0
    med_pct = (med_solved / total_med * 100) if total_med else 0.0
    hard_pct = (hard_solved / total_hard * 100) if total_hard else 0.0
    total_pct = (total_solved / total_all * 100) if total_all else 0.0

    # Heatmap Grid (53 weeks x 7 days)
    gh_today_wday = (today.weekday() + 1) % 7
    grid_end = today + timedelta(days=(6 - gh_today_wday))
    grid_start = grid_end - timedelta(days=(53 * 7 - 1))

    month_labels = []
    seen_months = set()
    heatmap_cells = []

    grid_origin_x = 48
    grid_origin_y = 296
    cell_size = 11
    step = 14.8

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
            cell_y = grid_origin_y + row * 13.2

            if curr_d > today:
                fill_color = "transparent"
            else:
                fill_color = get_heatmap_color(cnt)

            cell_date_str = curr_d.strftime("%Y-%m-%d")
            tooltip = f"{cell_date_str}: {cnt} submission{'s' if cnt != 1 else ''}"
            heatmap_cells.append(
                f'<rect x="{cell_x:.1f}" y="{cell_y:.1f}" width="{cell_size}" height="10" rx="2.5" '
                f'fill="{fill_color}"><title>{html.escape(tooltip)}</title></rect>'
            )
            curr_d += timedelta(days=1)

    updated_time_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    profile_url = f"https://leetcode.com/{html.escape(username, quote=True)}"

    css_fonts = font_face_css()
    styles = f"""
    {css_fonts}
    .r{{opacity:0;animation:rise .8s cubic-bezier(.2,.7,.2,1) both}}
    @keyframes rise{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}
    .f{{opacity:0;animation:fade .9s ease-out both}}
    @keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
    .live{{animation:pulse 1.6s ease-in-out infinite}}
    @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
    @media (prefers-reduced-motion: reduce){{.r,.f,.live{{animation:none!important;opacity:1!important}}}}
    """

    # Assemble SVG
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="LeetCode Profile Dashboard for {html.escape(username, quote=True)}">',
        f'  <style>{styles}</style>',
        '  <defs>',
        '    <linearGradient id="easy-grad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '      <stop offset="0%" stop-color="#10b981" /><stop offset="100%" stop-color="#34d399" />',
        '    </linearGradient>',
        '    <linearGradient id="med-grad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '      <stop offset="0%" stop-color="#f59e0b" /><stop offset="100%" stop-color="#fbbf24" />',
        '    </linearGradient>',
        '    <linearGradient id="hard-grad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '      <stop offset="0%" stop-color="#ef4444" /><stop offset="100%" stop-color="#f87171" />',
        '    </linearGradient>',
        '  </defs>',
        '',
        '  <!-- Background Canvas -->',
        f'  <rect width="{width}" height="{height}" rx="14" fill="#f3f3f1" />',
        '',
        '  <!-- Header Bar -->',
        '  <g transform="translate(32, 20)">',
        f'    <a href="{profile_url}" target="_blank">',
        '      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">',
        '        <path d="M16.102 17.93l-2.697 2.607c-.466.467-1.111.72-1.77.72-.66 0-1.305-.253-1.771-.72l-4.102-4.1c-.976-.976-.976-2.56 0-3.536L9.864 8.8c.466-.467 1.111-.72 1.77-.72.66 0 1.305.253 1.771.72l2.697 2.607c.45.435 1.168.423 1.603-.027.435-.45.423-1.168-.027-1.603l-2.697-2.607c-.893-.894-2.126-1.38-3.417-1.38-1.29 0-2.524.486-3.417 1.38L4.048 11.88c-1.884 1.884-1.884 4.94 0 6.824l4.102 4.1c.893.894 2.127 1.38 3.418 1.38 1.29 0 2.524-.486 3.417-1.38l2.697-2.607c.45-.435.462-1.153.027-1.603-.435-.45-1.153-.462-1.607-.027z" fill="#FFA116"/>',
        '        <path d="M20.811 13.01H10.606c-.626 0-1.134-.508-1.134-1.134 0-.626.508-1.134 1.134-1.134h10.205c.626 0 1.134.508 1.134 1.134 0 .626-.508 1.134-1.134 1.134z" fill="#8b949e"/>',
        '      </svg>',
        '    </a>',
        f'    <text x="32" y="18" fill="#111111" font-family="\'Instrument Serif\', Georgia, serif" font-size="22">LeetCode Profile</text>',
        f'    <a href="{profile_url}" target="_blank">',
        f'      <text x="175" y="17" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="12">@{html.escape(username)}</text>',
        '    </a>',
        '',
        '    <!-- Global Rank Badge -->',
        '    <g transform="translate(380, 0)">',
        '      <rect width="170" height="24" rx="6" fill="#ffffff" stroke="#dcdcd7" stroke-width="1"/>',
        '      <circle cx="12" cy="12" r="3.5" fill="#FFA116"/>',
        f'      <text x="22" y="16.5" fill="#3a3a3c" font-family="\'Geist Mono\', monospace" font-size="11.5" font-weight="600">Global Rank: <tspan fill="#FFA116">{rank_str}</tspan></text>',
        '    </g>',
        '',
        '    <!-- Last Updated Time -->',
        f'    <text x="816" y="17" text-anchor="end" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="11">Updated {updated_time_str}</text>',
        '  </g>',
        '',
        '  <!-- Top Metrics Row -->',
        '  <!-- Card 1: Total Solved Donut Chart -->',
        '  <rect x="32" y="60" width="235" height="154" rx="10" fill="#ffffff" stroke="#dcdcd7" stroke-width="1"/>',
        '  <text x="48" y="82" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="11" letter-spacing="1">PROBLEMS SOLVED</text>',
        '  <g>',
        f'    <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#e2e2de" stroke-width="8"/>',
        '    ' + '\n    '.join(donut_elements),
        f'    <text x="{cx}" y="{cy - 2}" text-anchor="middle" fill="#111111" font-family="\'Instrument Serif\', Georgia, serif" font-size="32">{total_solved:,}</text>',
        f'    <text x="{cx}" y="{cy + 15}" text-anchor="middle" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="10.5">/ {total_all:,}</text>',
        f'    <text x="{cx}" y="{cy + 42}" text-anchor="middle" fill="#FFA116" font-family="\'Geist Mono\', monospace" font-size="11" font-weight="600">{total_pct:.1f}% Solved</text>',
        '  </g>',
        '',
        '  <!-- Card 2: Difficulty Breakdown Bars -->',
        '  <rect x="279" y="60" width="569" height="154" rx="10" fill="#ffffff" stroke="#dcdcd7" stroke-width="1"/>',
        '',
        '  <!-- Easy Row -->',
        '  <g transform="translate(299, 74)">',
        '    <rect width="50" height="20" rx="5" fill="rgba(16, 185, 129, 0.12)"/>',
        '    <text x="25" y="14" text-anchor="middle" fill="#10b981" font-family="\'Geist Mono\', monospace" font-size="10.5" font-weight="600">Easy</text>',
        f'    <text x="64" y="15" fill="#111111" font-family="Geist, sans-serif" font-size="12.5" font-weight="600">{easy_solved:,} <tspan fill="#6e6e73" font-weight="400">/ {total_easy:,}</tspan></text>',
        f'    <text x="{bar_full_w + 35}" y="15" text-anchor="end" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="11">{easy_pct:.1f}% · {easy_subs:,} subs</text>',
        f'    <rect x="0" y="26" width="{bar_full_w + 35}" height="7" rx="3.5" fill="#e8e8e4"/>',
        f'    <rect x="0" y="26" width="{min(bar_full_w + 35, easy_bar_w)}" height="7" rx="3.5" fill="url(#easy-grad)"/>',
        '  </g>',
        '',
        '  <!-- Medium Row -->',
        '  <g transform="translate(299, 118)">',
        '    <rect width="64" height="20" rx="5" fill="rgba(245, 158, 11, 0.12)"/>',
        '    <text x="32" y="14" text-anchor="middle" fill="#f59e0b" font-family="\'Geist Mono\', monospace" font-size="10.5" font-weight="600">Medium</text>',
        f'    <text x="78" y="15" fill="#111111" font-family="Geist, sans-serif" font-size="12.5" font-weight="600">{med_solved:,} <tspan fill="#6e6e73" font-weight="400">/ {total_med:,}</tspan></text>',
        f'    <text x="{bar_full_w + 35}" y="15" text-anchor="end" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="11">{med_pct:.1f}% · {med_subs:,} subs</text>',
        f'    <rect x="0" y="26" width="{bar_full_w + 35}" height="7" rx="3.5" fill="#e8e8e4"/>',
        f'    <rect x="0" y="26" width="{min(bar_full_w + 35, med_bar_w)}" height="7" rx="3.5" fill="url(#med-grad)"/>',
        '  </g>',
        '',
        '  <!-- Hard Row -->',
        '  <g transform="translate(299, 162)">',
        '    <rect width="50" height="20" rx="5" fill="rgba(239, 68, 68, 0.12)"/>',
        '    <text x="25" y="14" text-anchor="middle" fill="#ef4444" font-family="\'Geist Mono\', monospace" font-size="10.5" font-weight="600">Hard</text>',
        f'    <text x="64" y="15" fill="#111111" font-family="Geist, sans-serif" font-size="12.5" font-weight="600">{hard_solved:,} <tspan fill="#6e6e73" font-weight="400">/ {total_hard:,}</tspan></text>',
        f'    <text x="{bar_full_w + 35}" y="15" text-anchor="end" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="11">{hard_pct:.1f}% · {hard_subs:,} subs</text>',
        f'    <rect x="0" y="26" width="{bar_full_w + 35}" height="7" rx="3.5" fill="#e8e8e4"/>',
        f'    <rect x="0" y="26" width="{min(bar_full_w + 35, hard_bar_w)}" height="7" rx="3.5" fill="url(#hard-grad)"/>',
        '  </g>',
        '',
        '  <!-- Activity Heatmap Container -->',
        '  <rect x="32" y="226" width="816" height="186" rx="10" fill="#ffffff" stroke="#dcdcd7" stroke-width="1"/>',
        '',
        '  <!-- Heatmap Header -->',
        '  <g transform="translate(48, 244)">',
        '    <text x="0" y="11" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="11" letter-spacing="1">SUBMISSION ACTIVITY</text>',
    ]

    if heatmap_available:
        lines.extend([
            f'    <text x="175" y="11" fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="11">'
            f'<tspan fill="#111111" font-weight="600">{total_subs_year:,}</tspan> submissions  ·  '
            f'<tspan fill="#111111" font-weight="600">{active_days_year}</tspan> active days  ·  '
            f'Current streak: <tspan fill="#FFA116" font-weight="600">{current_streak}d</tspan>  ·  '
            f'Max streak: <tspan fill="#111111">{max_streak}d</tspan>'
            f'</text>',
            '  </g>',
            '',
            '  <!-- Heatmap Grid -->',
            '  <g>',
            '    ' + '\n    '.join(heatmap_cells),
            '  </g>',
            '',
            '  <!-- Month Labels -->',
            '  <g fill="#6e6e73" font-family="\'Geist Mono\', monospace" font-size="10.5">',
        ])
        for x_pos, name in month_labels:
            if x_pos < width - 70:
                lines.append(f'    <text x="{x_pos:.1f}" y="400">{name}</text>')
        lines.append('  </g>')

        # Legend
        legend_x = 730
        lines.extend([
            '  <!-- Legend -->',
            f'  <g transform="translate({legend_x}, 392)" font-family="\'Geist Mono\', monospace" font-size="10" fill="#6e6e73">',
            '    <text x="-6" y="8" text-anchor="end">less</text>',
            f'    <rect x="0" y="0" width="9" height="9" rx="2" fill="{PAPER_EMPTY}" />',
            f'    <rect x="12" y="0" width="9" height="9" rx="2" fill="{LEET_ORANGE[0]}" />',
            f'    <rect x="24" y="0" width="9" height="9" rx="2" fill="{LEET_ORANGE[1]}" />',
            f'    <rect x="36" y="0" width="9" height="9" rx="2" fill="{LEET_ORANGE[2]}" />',
            f'    <rect x="48" y="0" width="9" height="9" rx="2" fill="{LEET_ORANGE[3]}" />',
            '    <text x="63" y="8">more</text>',
            '  </g>',
        ])
    else:
        lines.extend([
            '  </g>',
            '  <text x="440" y="325" fill="#6e6e73" font-family="Geist, sans-serif" font-size="14" text-anchor="middle">Submission calendar data currently unavailable</text>',
        ])

    lines.append('</svg>')
    return '\n'.join(lines)


def main():
    print(f"[Info] Fetching LeetCode stats for '{LEETCODE_USERNAME}'...")
    try:
        matched_user, all_questions = fetch_leetcode_data(LEETCODE_USERNAME)
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
        sys.exit(1)

    print("[Info] Generating SVG dashboard...")
    svg_content = generate_svg(matched_user, all_questions, LEETCODE_USERNAME)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg_content)

    print(f"[Success] Dashboard successfully generated at: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
