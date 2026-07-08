from datetime import datetime
import calendar
import re

# Get today's date
today = datetime.now()

year = today.year

# Check leap year
days_in_year = 366 if calendar.isleap(year) else 365

# Current day number
current_day = today.timetuple().tm_yday

# Remaining days
remaining_days = days_in_year - current_day

# Percentage completed
percentage = (current_day / days_in_year) * 100

# Progress bar
bar_length = 30
filled = round((current_day / days_in_year) * bar_length)

progress_bar = "█" * filled + "░" * (bar_length - filled)

content = f"""
## 📅 Year Progress

```text
{progress_bar}

{percentage:.2f}% Complete

📆 {current_day}/{days_in_year} Days Completed
⏳ {remaining_days} Days Remaining
