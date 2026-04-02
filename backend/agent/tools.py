from langchain.tools import tool
from github import Github
from datetime import datetime
import threading
import requests
import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# In-memory reminder store
_reminders: dict = {}


# ─── GitHub Tools ─────────────────────────────────────────────────────────────

@tool
def get_github_prs(repo: str) -> str:
    """Get open pull requests for a GitHub repo. Input: 'username/repo-name'"""
    try:
        g = Github(GITHUB_TOKEN)
        r = g.get_repo(repo)
        prs = list(r.get_pulls(state='open'))
        if not prs:
            return f"✅ No open PRs in {repo}"
        return "Open PRs:\n" + "\n".join([
            f"  #{p.number} — {p.title} (by {p.user.login}) "
            f"[{p.created_at.strftime('%b %d')}]"
            for p in prs[:10]
        ])
    except Exception as e:
        return f"GitHub error: {str(e)}"


@tool
def get_github_repo_stats(repo: str) -> str:
    """Get stats (stars, issues, last commit) for a GitHub repo. Input: 'username/repo-name'"""
    try:
        g = Github(GITHUB_TOKEN)
        r = g.get_repo(repo)
        # Get latest commit
        commits = list(r.get_commits()[:1])
        last_commit = commits[0].commit.message[:60] if commits else "N/A"
        return (
            f"📦 {r.full_name}\n"
            f"⭐ Stars: {r.stargazers_count} | 🍴 Forks: {r.forks_count}\n"
            f"🐛 Open Issues: {r.open_issues_count}\n"
            f"📝 Last commit: {last_commit}\n"
            f"🕐 Updated: {r.updated_at.strftime('%Y-%m-%d %H:%M')}"
        )
    except Exception as e:
        return f"GitHub error: {str(e)}"


@tool
def get_github_commits_today(repo: str) -> str:
    """Get today's commits for a GitHub repo. Input: 'username/repo-name'"""
    try:
        g = Github(GITHUB_TOKEN)
        r = g.get_repo(repo)
        today = datetime.now().date()
        commits = [
            c for c in r.get_commits()
            if c.commit.author.date.date() == today
        ]
        if not commits:
            return f"No commits today in {repo}"
        return f"Today's commits in {repo} ({len(commits)} total):\n" + "\n".join([
            f"  • {c.commit.message[:60]} ({c.commit.author.name})"
            for c in commits[:10]
        ])
    except Exception as e:
        return f"GitHub error: {str(e)}"


# ─── Goal & Habit Signal Tools ────────────────────────────────────────────────

@tool
def log_habit_done(habit_name: str) -> str:
    """Log a habit as completed for today. Input: exact habit name."""
    return f"__LOG_HABIT__{habit_name}"


@tool
def add_user_goal(title_and_domain: str) -> str:
    """Add a new goal. Input format: 'goal title | domain'
    Domains: developer, health, learning, finance, social, general"""
    parts = title_and_domain.split("|")
    title = parts[0].strip()
    domain = parts[1].strip() if len(parts) > 1 else "general"
    return f"__ADD_GOAL__{title}|{domain}"

@tool
def create_calendar_event(event_details: str) -> str:
    """Create a Google Calendar event.
    Input: 'title | YYYY-MM-DD | HH:MM | duration_minutes'
    Example: 'Deep work session | 2026-04-03 | 10:00 | 120'"""


@tool
def complete_goal(goal_title: str) -> str:
    """Mark a goal as fully completed. Input: exact goal title."""
    return f"__COMPLETE_GOAL__{goal_title}"


@tool
def update_goal_progress(title_and_progress: str) -> str:
    """Update progress of a goal. Input format: 'goal title | progress_percent'
    Example: 'Ship NFT marketplace | 75'"""
    parts = title_and_progress.split("|")
    if len(parts) < 2:
        return "❌ Format: 'goal title | progress_percent'"
    title = parts[0].strip()
    try:
        progress = int(parts[1].strip().replace("%", ""))
        return f"__UPDATE_PROGRESS__{title}|{progress}"
    except ValueError:
        return "❌ Progress must be a number (0-100)"


# ─── Reminder Tools ───────────────────────────────────────────────────────────

@tool
def set_reminder(reminder_input: str) -> str:
    """Set a reminder at a specific time. 
    Input format: 'HH:MM | reminder message | uid'
    Example: '21:30 | Time to sleep | 123456789'
    Time is in 24h format IST."""
    try:
        parts = reminder_input.split("|")
        if len(parts) < 2:
            return "❌ Format: 'HH:MM | message | uid'"

        time_str = parts[0].strip()
        message = parts[1].strip()
        uid = parts[2].strip() if len(parts) > 2 else ""

        reminder_time = datetime.strptime(time_str, "%H:%M").replace(
            year=datetime.now().year,
            month=datetime.now().month,
            day=datetime.now().day
        )
        now = datetime.now()

        # If time already passed, schedule for tomorrow
        if reminder_time < now:
            from datetime import timedelta
            reminder_time += timedelta(days=1)
            day_label = "tomorrow"
        else:
            day_label = "today"

        delay_seconds = (reminder_time - now).total_seconds()
        minutes_away = int(delay_seconds // 60)

        # Store reminder
        key = f"{uid}_{time_str}_{message[:10]}"
        _reminders[key] = {
            "text": message,
            "time": time_str,
            "uid": uid,
            "set_at": now.isoformat()
        }

        def fire_reminder():
            print(f"⏰ REMINDER [{uid}]: {message}")
            if TELEGRAM_TOKEN and uid:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json={
                            "chat_id": uid,
                            "text": f"⏰ <b>Reminder</b>\n\n{message}",
                            "parse_mode": "HTML"
                        },
                        timeout=10
                    )
                except Exception as e:
                    print(f"Reminder Telegram error: {e}")

        timer = threading.Timer(delay_seconds, fire_reminder)
        timer.daemon = True
        timer.start()

        return (
            f"⏰ Reminder set for {time_str} {day_label}!\n"
            f"Message: '{message}'\n"
            f"Fires in {minutes_away} minutes."
        )

    except ValueError:
        return "❌ Invalid time. Use 24h format HH:MM (e.g. '21:30')"


@tool
def list_reminders(uid: str = "") -> str:
    """List all active reminders. Input: user uid"""
    user_reminders = [
        f"  ⏰ {v['time']} — {v['text']}"
        for k, v in _reminders.items()
        if v.get('uid') == uid
    ]
    if not user_reminders:
        return "No active reminders set."
    return f"Your reminders ({len(user_reminders)}):\n" + "\n".join(user_reminders)


@tool
def cancel_reminder(time_str: str) -> str:
    """Cancel a reminder at a specific time. Input: 'HH:MM'"""
    cancelled = [
        k for k in _reminders
        if time_str in k
    ]
    for key in cancelled:
        del _reminders[key]
    if cancelled:
        return f"✅ Cancelled reminder at {time_str}"
    return f"❌ No reminder found at {time_str}"


# ─── Utility Tools ────────────────────────────────────────────────────────────

@tool
def get_current_datetime(_: str = "") -> str:
    """Get the current date and time."""
    now = datetime.now()
    return (
        f"📅 {now.strftime('%A, %d %B %Y')}\n"
        f"🕐 {now.strftime('%I:%M %p')} IST\n"
        f"24h: {now.strftime('%H:%M')}"
    )


@tool
def calculate_deadline_countdown(deadline_str: str) -> str:
    """Calculate days remaining until a deadline. 
    Input: date in format 'YYYY-MM-DD' or 'DD/MM/YYYY'"""
    try:
        try:
            deadline = datetime.strptime(deadline_str.strip(), "%Y-%m-%d")
        except ValueError:
            deadline = datetime.strptime(deadline_str.strip(), "%d/%m/%Y")

        now = datetime.now()
        diff = deadline - now
        days = diff.days

        if days < 0:
            return f"⚠️ Deadline was {abs(days)} days ago!"
        elif days == 0:
            return "🚨 Deadline is TODAY!"
        elif days <= 3:
            return f"🔴 {days} days left — URGENT!"
        elif days <= 7:
            return f"🟡 {days} days left — this week."
        else:
            return f"🟢 {days} days left until {deadline.strftime('%d %B %Y')}"
    except ValueError:
        return "❌ Invalid date. Use YYYY-MM-DD or DD/MM/YYYY"


@tool
def send_telegram_message(message_and_uid: str) -> str:
    """Send a direct Telegram message to the user.
    Input format: 'uid | message text'"""
    try:
        parts = message_and_uid.split("|", 1)
        if len(parts) < 2:
            return "❌ Format: 'uid | message'"
        uid = parts[0].strip()
        message = parts[1].strip()

        if not TELEGRAM_TOKEN:
            return "❌ TELEGRAM_BOT_TOKEN not set"

        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": uid,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        if resp.json().get("ok"):
            return f"✅ Message sent to {uid}"
        return f"❌ Failed: {resp.json().get('description')}"
    except Exception as e:
        return f"Error: {str(e)}"


# ─── Register All Tools ───────────────────────────────────────────────────────

def get_all_tools():
    return [
        # GitHub
        get_github_prs,
        get_github_repo_stats,
        get_github_commits_today,
        # Goals & Habits
        log_habit_done,
        add_user_goal,
        complete_goal,
        update_goal_progress,
        # Reminders
        set_reminder,
        list_reminders,
        cancel_reminder,
        # Utility
        get_current_datetime,
        calculate_deadline_countdown,
        send_telegram_message,
    ]