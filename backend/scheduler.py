from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from agent.core import LifeOSAgent
from agent.memory import MemoryManager
from firebase_admin import firestore
import requests, os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def get_all_user_ids() -> list:
    db = firestore.client()
    return [doc.id for doc in db.collection("users").stream()]

def send_morning_briefings():
    print("⏰ Sending morning briefings...")
    for uid in get_all_user_ids():
        try:
            agent = LifeOSAgent(uid)
            briefing = agent.generate_morning_briefing()
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": uid, "text": briefing, "parse_mode": "HTML"},
                timeout=10
            )
            print(f"✅ Briefing sent to {uid}")
        except Exception as e:
            print(f"❌ Briefing error for {uid}: {e}")

def send_habit_nudges():
    print("🔔 Sending habit nudges...")
    for uid in get_all_user_ids():
        try:
            mm = MemoryManager(uid)
            ctx = mm.get_context()
            stale = [h['name'] for h in ctx['habits'] if h.get('streak', 0) == 0]
            if stale:
                msg = "⚡ <b>Habit Check!</b>\n\nYou haven't logged today:\n"
                msg += "\n".join([f"  • {h}" for h in stale[:3]])
                msg += "\n\n<i>Use /log to check them off!</i>"
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": uid, "text": msg, "parse_mode": "HTML"},
                    timeout=10
                )
                print(f"✅ Nudge sent to {uid}")
        except Exception as e:
            print(f"❌ Nudge error for {uid}: {e}")

def send_weekly_reviews():
    print("📊 Sending weekly reviews...")
    for uid in get_all_user_ids():
        try:
            agent = LifeOSAgent(uid)
            review = agent.generate_weekly_review()
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": uid, "text": review, "parse_mode": "HTML"},
                timeout=10
            )
            print(f"✅ Review sent to {uid}")
        except Exception as e:
            print(f"❌ Review error for {uid}: {e}")

def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(send_morning_briefings, CronTrigger(hour=9, minute=0))
    scheduler.add_job(send_habit_nudges, CronTrigger(hour=20, minute=0))
    scheduler.add_job(send_weekly_reviews, CronTrigger(day_of_week='sun', hour=9))
    scheduler.start()
    print("✅ Scheduler running — 9AM briefings, 8PM nudges, Sunday reviews")
    return scheduler