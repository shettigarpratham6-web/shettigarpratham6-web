from datetime import datetime
import calendar
import re

# Current date
today = datetime.now()
year = today.year

# Total days in the year
days_in_year = 366 if calendar.isleap(year) else 365

# Current day of the year
current_day = today.timetuple().tm_yday

# Remaining days
remaining_days = days_in_year - current_day

# Percentage completed
percentage = (current_day / days_in_year) * 100

# Progress bar
bar_length = 30
filled = round((current_day / days_in_year) * bar_length)
progress_bar = "█" * filled + "░" * (bar_length - filled)

# Content to insert into README
content = "\n".join([
    "## 📅 Year Progress",
    "",
    "```text",
    progress_bar,
    "",
    f"{percentage:.2f}% Complete",
    "",
    f"📆 {current_day}/{days_in_year} Days Completed",
    f"⏳ {remaining_days} Days Remaining",
    "```"
])

# Read README
with open("README.md", "r", encoding="utf-8") as file:
    readme = file.read()

# Replace placeholder
pattern = r'<!-- YEAR_PROGRESS_START -->(.*?)<!-- YEAR_PROGRESS_END -->'

replacement = (
    "<!-- YEAR_PROGRESS_START -->\n"
    + content +
    "\n<!-- YEAR_PROGRESS_END -->"
)

readme = re.sub(pattern, replacement, readme, flags=re.DOTALL)

# Write updated README
with open("README.md", "w", encoding="utf-8") as file:
    file.write(readme)

print("✅ README updated successfully!")
