# scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from agent.core import LifeOSAgent
from agent.memory import MemoryManager
import requests, os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def send_morning_briefing_to_all():
    """Runs every day at 9AM — sends briefing to every user."""
    db_users = MemoryManager.get_all_users()  # add this method
    for uid in db_users:
        agent = LifeOSAgent(uid)
        briefing = agent.generate_morning_briefing()
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": uid, "text": briefing, "parse_mode": "HTML"}
        )

def send_habit_nudges():
    """Runs every evening at 8PM — nudges users with zero streak."""
    db_users = MemoryManager.get_all_users()
    for uid in db_users:
        mm = MemoryManager(uid)
        ctx = mm.get_context()
        stale = [h['name'] for h in ctx['habits'] if h.get('streak', 0) == 0]
        if stale:
            msg = f"⚡ Hey! You haven't logged these today:\n"
            msg += "\n".join([f"  • {h}" for h in stale[:3]])
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": uid, "text": msg}
            )

# Add to main.py startup
def start_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_morning_briefing_to_all,
                      CronTrigger(hour=9, minute=0))
    scheduler.add_job(send_habit_nudges,
                      CronTrigger(hour=20, minute=0))
    scheduler.start()
    return scheduler