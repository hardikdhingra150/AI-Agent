from telegram import Update
from telegram.ext import (ApplicationBuilder, CommandHandler,
                           MessageHandler, filters, ContextTypes)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.core import LifeOSAgent
from agent.memory import MemoryManager
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def get_uid(update: Update) -> str:
    return str(update.effective_user.id)


def md_to_html(text: str) -> str:
    """Convert basic markdown to Telegram HTML."""
    import re
    # Bold: **text** or *text* → <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<b>\1</b>', text)
    # Italic: _text_ → <i>text</i>
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    # Code: `text` → <code>text</code>
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    # Escape any leftover < > & that aren't our tags
    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    name = update.effective_user.first_name
    mm = MemoryManager(uid)
    mm.init_user(name=name)
    await update.message.reply_text(
        f"Hey <b>{name}</b>! I'm <b>LifeOS</b> — your personal AI agent.\n\n"
        f"<b>Commands:</b>\n"
        f"/brief — Morning briefing\n"
        f"/goal &lt;text&gt; — Add a goal\n"
        f"/habit &lt;name&gt; — Add a habit\n"
        f"/log &lt;name&gt; — Log habit as done today\n"
        f"/status — Your goals &amp; streaks\n\n"
        f"Or just <i>chat with me naturally!</i>",
        parse_mode="HTML"
    )


async def brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    await update.message.reply_text(" Generating your briefing...")
    try:
        agent = LifeOSAgent(uid)
        briefing = agent.generate_morning_briefing()
        await update.message.reply_text(
            f" <b>Morning Briefing</b>\n\n{md_to_html(briefing)}",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def add_goal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    goal_text = " ".join(context.args)
    if not goal_text:
        await update.message.reply_text(
            "Usage: <code>/goal Ship my NFT marketplace</code>",
            parse_mode="HTML"
        )
        return
    mm = MemoryManager(uid)
    mm.add_goal(title=goal_text, domain="general")
    await update.message.reply_text(
        f"Goal added: <b>{goal_text}</b>",
        parse_mode="HTML"
    )


async def add_habit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    habit_name = " ".join(context.args)
    if not habit_name:
        await update.message.reply_text(
            "Usage: <code>/habit Deep work 2h</code>",
            parse_mode="HTML"
        )
        return
    mm = MemoryManager(uid)
    mm.add_habit(name=habit_name, domain="general")
    await update.message.reply_text(
        f"Habit added: <b>{habit_name}</b>",
        parse_mode="HTML"
    )


async def log_habit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    habit_name = " ".join(context.args)
    if not habit_name:
        await update.message.reply_text(
            "Usage: <code>/log Deep work 2h</code>",
            parse_mode="HTML"
        )
        return
    mm = MemoryManager(uid)
    success = mm.log_habit(habit_name)
    if success:
        await update.message.reply_text(
            f" Logged: <b>{habit_name}</b>! Streak updated!",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f" Habit '<b>{habit_name}</b>' not found.\n"
            f"Add it first: <code>/habit {habit_name}</code>",
            parse_mode="HTML"
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    mm = MemoryManager(uid)
    ctx = mm.get_context()
    goals = ctx.get("goals", [])
    habits = ctx.get("habits", [])
    user = ctx.get("user", {})

    msg = f"📊 <b>LifeOS Status — {user.get('name', 'User')}</b>\n\n"

    msg += "<b>🎯 Active Goals:</b>\n"
    if goals:
        for g in goals[:5]:
            progress = g.get('progress', 0)
            bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
            msg += f"  • {g['title']}\n    {bar} {progress}%\n"
    else:
        msg += "  <i>No goals yet. Use /goal to add one.</i>\n"

    msg += "\n<b>🔥 Habit Streaks:</b>\n"
    if habits:
        for h in habits[:5]:
            streak = h.get('streak', 0)
            flame = "🔥" if streak > 0 else "❄️"
            msg += f"  • {h['name']}: {flame} {streak} days\n"
    else:
        msg += "  <i>No habits yet. Use /habit to add one.</i>\n"

    await update.message.reply_text(msg, parse_mode="HTML")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user_msg = update.message.text
    thinking_msg = await update.message.reply_text("🤔 Thinking...")
    try:
        agent = LifeOSAgent(uid)
        response = agent.run(user_msg)
        # Delete "Thinking..." and send real response
        await thinking_msg.delete()
        await update.message.reply_text(
            md_to_html(response),
            parse_mode="HTML"
        )
    except Exception as e:
        await thinking_msg.delete()
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"⚠️ Bot error: {context.error}")


def run_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("brief", brief))
    app.add_handler(CommandHandler("goal", add_goal_cmd))
    app.add_handler(CommandHandler("habit", add_habit_cmd))
    app.add_handler(CommandHandler("log", log_habit_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_error_handler(error_handler)

    print(" LifeOS Telegram bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()