from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor
from langchain.agents import create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from agent.memory import MemoryManager
from agent import tools as tool_module
from datetime import datetime
import os
import re
from dotenv import load_dotenv

load_dotenv()


class LifeOSAgent:
    def __init__(self, uid: str):
        self.uid = uid
        self.memory = MemoryManager(uid)
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.4,
        )
        self.tools = tool_module.get_all_tools()

    # ─── System Prompt ────────────────────────────────────────────────────────

    def _build_system_prompt(self, ctx: dict) -> str:
        user = ctx.get("user", {})
        goals = ctx.get("goals", [])
        habits = ctx.get("habits", [])
        mem = user.get("memory", {})
        now = datetime.now().strftime("%A, %d %B %Y — %I:%M %p")

        goals_str = "\n".join([
            f"  • [{g.get('domain','?')}] {g.get('title')} — {g.get('progress',0)}% done"
            for g in goals
        ]) or "  None set yet."

        habits_str = "\n".join([
            f"  • {h.get('name')} ({h.get('frequency')}) "
            f"— streak: {h.get('streak',0)} days 🔥 "
            f"| best: {h.get('best_streak',0)} days"
            for h in habits
        ]) or "  None set yet."

        # Detect habits not logged recently for nudge
        nudge_habits = [
            h.get('name') for h in habits
            if h.get('streak', 0) == 0 or h.get('last_logged') is None
        ]
        nudge_str = (
            f"\n⚠️  NUDGE: User hasn't logged these habits recently: "
            f"{', '.join(nudge_habits[:3])}"
            if nudge_habits else ""
        )

        # Low progress goals
        low_goals = [
            g.get('title') for g in goals
            if g.get('progress', 0) < 20
        ]
        low_str = (
            f"\n📌 ATTENTION: These goals have very low progress: "
            f"{', '.join(low_goals[:3])}"
            if low_goals else ""
        )

        return f"""You are LifeOS — a proactive personal AI agent for {user.get('name', 'the user')}.
Current time: {now}

MEMORY CONTEXT:
━━━━━━━━━━━━━━
Active Goals:
{goals_str}

Tracked Habits:
{habits_str}

Projects: {', '.join(mem.get('current_projects', [])) or 'None'}
Work Style: {mem.get('work_style', 'Not set')}
Pain Points: {', '.join(mem.get('pain_points', [])) or 'None'}
Timezone: {user.get('timezone', 'Asia/Kolkata')}
{nudge_str}
{low_str}

BEHAVIOR RULES:
━━━━━━━━━━━━━━
1. Be PROACTIVE — surface relevant insights without being asked
2. Be CONCISE — bullet points over long paragraphs
3. Use tools when user asks for real actions
4. AUTO-UPDATE GOALS: When user says they finished/started/deployed something,
   detect which goal it matches and call update_goal_progress tool immediately.
   Infer progress: "just started"=10%, "working on it"=35%, "halfway"=50%,
   "almost done"=80%, "tested/deployed"=75%, "finished/completed/done"=100%
5. Always confirm after updating: "Updated [goal] to X% ✅"
6. When user seems overwhelmed, suggest ONE thing to focus on
7. Developer-friendly tone — no corporate speak
8. If it's past midnight, remind user to rest if they mention coding
9. Celebrate streaks and goal completions enthusiastically


REMINDER RULES:
- When user says "remind me", "set a reminder", "wake me at", "alert me" etc.
  ALWAYS call set_reminder tool immediately — never say you can't.
- For sleep reminders: set_reminder(reminder_text="Time to sleep! 😴", time_str="HH:MM", uid=self.uid)
- ALWAYS pass the uid to set_reminder so Telegram notification fires correctly.
- Confirm with: "⏰ Reminder set for HH:MM ✅"


GOAL AUTO-UPDATE EXAMPLES:
━━━━━━━━━━━━━━━━━━━━━━━━━
User: "I finished the smart contract" → find matching goal → set to 100%
User: "Just started working on frontend" → find matching goal → set to 10%
User: "Deployed the API today" → find matching goal → set to 80%
User: "Halfway through my NFT marketplace" → set to 50%
"""



    # ─── Chat History ─────────────────────────────────────────────────────────

    def _build_chat_history(self, history: list) -> list:
        messages = []
        for item in history[-8:]:  # Last 4 exchanges
            if item["role"] == "user":
                messages.append(HumanMessage(content=item["content"]))
            else:
                messages.append(AIMessage(content=item["content"]))
        return messages

    # ─── Smart Progress Detection ─────────────────────────────────────────────

    def _detect_and_update_progress(self, message: str, ctx: dict) -> str | None:
        """Detect progress signals in message and auto-update matching goals."""
        goals = ctx.get("goals", [])
        if not goals:
            return None

        msg_lower = message.lower()

        # Progress keyword map
        progress_signals = {
            "finished": 100, "completed": 100, "done": 100,
            "shipped": 100, "launched": 100, "deployed": 80,
            "tested": 75, "built": 65, "implemented": 60,
            "almost done": 90, "nearly finished": 85, "almost finished": 88,
            "halfway": 50, "half done": 50, "50%": 50,
            "good progress": 55, "making progress": 40,
            "started": 10, "just started": 10, "beginning": 10,
            "planning": 5, "designed": 30, "working on": 35,
        }

        detected_progress = None
        for keyword, progress in progress_signals.items():
            if keyword in msg_lower:
                detected_progress = progress
                break

        # Check for explicit percentage: "updated to 60%" or "60% done"
        pct_match = re.search(r'(\d+)\s*%', msg_lower)
        if pct_match:
            detected_progress = int(pct_match.group(1))

        if not detected_progress:
            return None

        # Match to most relevant goal
        updated = []
        for goal in goals:
            title_words = [
                w for w in goal["title"].lower().split()
                if len(w) > 3
            ]
            if any(word in msg_lower for word in title_words):
                self.memory.update_goal_progress(goal["title"], detected_progress)
                updated.append(f"**{goal['title']}** → {detected_progress}%")

        if updated:
            emoji = "🎉" if detected_progress == 100 else "📈"
            return f"{emoji} Auto-updated: {', '.join(updated)}"
        return None

    # ─── Main Run ─────────────────────────────────────────────────────────────

    def run(self, user_message: str) -> str:
        ctx = self.memory.get_context()
        system_prompt = self._build_system_prompt(ctx)
        chat_history = self._build_chat_history(ctx.get("history", []))

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=False,
            max_iterations=6,
            handle_parsing_errors=True
        )

        result = executor.invoke({
            "input": user_message,
            "chat_history": chat_history
        })

        response = result["output"]

        # Smart auto-progress detection
        progress_update = self._detect_and_update_progress(user_message, ctx)
        if progress_update:
            response = f"{response}\n\n{progress_update}"

        # Handle special tool signals
        if "__LOG_HABIT__" in response:
            habit_name = response.replace("__LOG_HABIT__", "").strip()
            success = self.memory.log_habit(habit_name)
            response = (
                f"✅ Logged **{habit_name}**! Streak updated. 🔥"
                if success
                else f"❌ Habit '{habit_name}' not found. Use /habit to add it first."
            )

        if "__ADD_GOAL__" in response:
            parts = response.replace("__ADD_GOAL__", "").split("|")
            title = parts[0].strip()
            domain = parts[1].strip() if len(parts) > 1 else "general"
            self.memory.add_goal(title, domain)
            response = f"🎯 Goal added: **{title}** [{domain}]"

        if "__COMPLETE_GOAL__" in response:
            title = response.replace("__COMPLETE_GOAL__", "").strip()
            self.memory.complete_goal(title)
            response = f"🎉 Goal completed: **{title}**! Amazing work!"

        # Late night nudge
        hour = datetime.now().hour
        if hour >= 1 and hour <= 4:
            response += "\n\n🌙 *It's late — remember to rest. Your best code comes after sleep.*"

        # Log to Firebase
        self.memory.log_interaction("user", user_message)
        self.memory.log_interaction("agent", response)

        return response

    # ─── Morning Briefing ─────────────────────────────────────────────────────

    def generate_morning_briefing(self) -> str:
        ctx = self.memory.get_context()
        goals = ctx.get("goals", [])
        habits = ctx.get("habits", [])
        user = ctx.get("user", {})
        stats = self.memory.get_stats()
        now = datetime.now().strftime("%A, %d %B")

        # Find top priority (lowest progress active goal)
        top_goal = min(goals, key=lambda g: g.get("progress", 0)) if goals else None
        top_goal_str = (
            f"{top_goal['title']} ({top_goal.get('progress',0)}% done)"
            if top_goal else "No goals set yet"
        )

        # Habits needing attention
        stale_habits = [
            h['name'] for h in habits
            if h.get('streak', 0) == 0
        ]

        prompt = f"""Generate a short, punchy morning briefing for {user.get('name', 'there')}.
Date: {now}

Stats:
- Active goals: {stats['active_goals']} | Completed: {stats['completed_goals']}
- Total habits: {stats['total_habits']} | Combined streak days: {stats['total_streak_days']}
- Top priority goal: {top_goal_str}
- Habits needing attention: {stale_habits[:3] or 'All on track!'}

Goals: {[f"{g['title']} ({g.get('progress',0)}%)" for g in goals[:4]]}
Habit streaks: {[f"{h['name']}: {h.get('streak',0)}🔥" for h in habits[:4]]}

Write in this exact format:
🌅 Good morning, {user.get('name','there')}! ({now})

🎯 Top Priority: [single most important thing today]

📊 Goals:
[2-3 bullet points with progress]

🔥 Habits:
[which ones to do today, call out any streaks]

⚡ Dev Tip: [one specific, actionable developer insight]

🧠 Insight: [one proactive observation about their progress patterns]

Keep under 180 words. Motivating but honest. No fluff."""

        response = self.llm.invoke(prompt)
        return response.content

    # ─── Weekly Review ────────────────────────────────────────────────────────

    def generate_weekly_review(self) -> str:
        ctx = self.memory.get_context()
        goals = ctx.get("goals", [])
        habits = ctx.get("habits", [])
        user = ctx.get("user", {})
        history = ctx.get("history", [])
        stats = self.memory.get_stats()

        prompt = f"""Generate a weekly review for {user.get('name', 'the user')}.

Goals progress: {[f"{g['title']}: {g.get('progress',0)}%" for g in goals]}
Habit streaks: {[f"{h['name']}: {h.get('streak',0)} days" for h in habits]}
Completed goals this week: {stats['completed_goals']}
Total interactions: {len(history)}

Format:
📅 Weekly Review

✅ Wins: [what went well]
📈 Progress: [goal updates]
🔥 Habit Performance: [streaks summary]
⚠️ Watch Out: [what needs attention next week]
🎯 Next Week Focus: [top 3 priorities]

Be specific, honest, and encouraging. Under 200 words."""

        response = self.llm.invoke(prompt)

        # Log that review was generated
        self.memory.log_interaction("agent", "Weekly review generated", "review")
        return response.content