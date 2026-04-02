import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from datetime import datetime
import os

# Always find serviceAccountKey.json relative to this file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_PATH = os.path.join(BASE_DIR, "serviceAccountKey.json")

if not firebase_admin._apps:
    cred = credentials.Certificate(KEY_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()


class MemoryManager:
    def __init__(self, uid: str):
        self.uid = uid
        self.ref = db.collection("users").document(uid)

    def init_user(self, name: str, timezone: str = "Asia/Kolkata"):
        """Create user doc on first login. Skips if already exists."""
        if not self.ref.get().exists:
            self.ref.set({
                "uid": self.uid,
                "name": name,
                "timezone": timezone,
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_active": firestore.SERVER_TIMESTAMP,
                "memory": {
                    "current_projects": [],
                    "work_style": "",
                    "pain_points": [],
                    "personality_tags": []
                }
            })
        else:
            # Always update last_active on login
            self.ref.update({"last_active": firestore.SERVER_TIMESTAMP})

    def get_context(self) -> dict:
        """Load full user memory for agent system prompt."""
        user_doc = self.ref.get()
        if not user_doc.exists:
            return {}
        user = user_doc.to_dict()

        # Fixed: use FieldFilter instead of positional args
        goals = [g.to_dict() for g in
                 self.ref.collection("goals")
                 .where(filter=FieldFilter("status", "==", "active"))
                 .stream()]

        habits = [h.to_dict() for h in
                  self.ref.collection("habits").stream()]

        # Last 10 interactions for conversation continuity
        history = [i.to_dict() for i in
                   self.ref.collection("interactions")
                   .order_by("timestamp",
                             direction=firestore.Query.DESCENDING)
                   .limit(10).stream()]

        return {
            "user": user,
            "goals": goals,
            "habits": habits,
            "history": list(reversed(history))
        }

    def update_memory(self, key: str, value):
        """Update a field inside the memory object."""
        self.ref.update({
            f"memory.{key}": value,
            "last_active": firestore.SERVER_TIMESTAMP
        })

    def add_goal(self, title: str, domain: str, deadline=None):
        """Add a new goal. Prevents duplicates by checking title."""
        existing = self.ref.collection("goals")\
                            .where(filter=FieldFilter("title", "==", title))\
                            .get()
        if existing:
            # Update existing instead of duplicating
            existing[0].reference.update({
                "status": "active",
                "domain": domain
            })
            return

        self.ref.collection("goals").add({
            "title": title,
            "domain": domain,
            "deadline": deadline,
            "progress": 0,
            "status": "active",
            "milestones": [],
            "created_at": firestore.SERVER_TIMESTAMP
        })

    def update_goal_progress(self, title: str, progress: int):
        """Update progress on a goal (0-100)."""
        goals = self.ref.collection("goals")\
                        .where(filter=FieldFilter("title", "==", title))\
                        .get()
        if goals:
            goals[0].reference.update({"progress": max(0, min(100, progress))})
            return True
        return False

    def complete_goal(self, title: str):
        """Mark a goal as completed."""
        goals = self.ref.collection("goals")\
                        .where(filter=FieldFilter("title", "==", title))\
                        .get()
        if goals:
            goals[0].reference.update({
                "status": "completed",
                "progress": 100,
                "completed_at": firestore.SERVER_TIMESTAMP
            })
            return True
        return False

    def add_habit(self, name: str, domain: str, frequency: str = "daily"):
        """Add a habit. Prevents duplicates."""
        existing = self.ref.collection("habits")\
                            .where(filter=FieldFilter("name", "==", name))\
                            .get()
        if existing:
            return  # Already exists, skip

        self.ref.collection("habits").add({
            "name": name,
            "domain": domain,
            "frequency": frequency,
            "streak": 0,
            "best_streak": 0,
            "last_logged": None,
            "nudge_threshold": 2,
            "created_at": firestore.SERVER_TIMESTAMP
        })

    def log_habit(self, habit_name: str) -> bool:
        """Log a habit as done today. Updates streak and best_streak."""
        habits = self.ref.collection("habits")\
                         .where(filter=FieldFilter("name", "==", habit_name))\
                         .get()
        if not habits:
            return False

        habit_ref = habits[0].reference
        habit_data = habits[0].to_dict()
        current_streak = habit_data.get("streak", 0) + 1
        best_streak = max(current_streak, habit_data.get("best_streak", 0))

        habit_ref.update({
            "streak": current_streak,
            "best_streak": best_streak,
            "last_logged": firestore.SERVER_TIMESTAMP
        })
        return True

    def reset_habit_streak(self, habit_name: str) -> bool:
        """Reset streak for a missed habit."""
        habits = self.ref.collection("habits")\
                         .where(filter=FieldFilter("name", "==", habit_name))\
                         .get()
        if habits:
            habits[0].reference.update({"streak": 0})
            return True
        return False

    def log_interaction(self, role: str, content: str, domain: str = "general"):
        """Append a message to conversation history."""
        self.ref.collection("interactions").add({
            "role": role,
            "content": content,
            "domain": domain,
            "timestamp": firestore.SERVER_TIMESTAMP
        })

    def get_stats(self) -> dict:
        """Get summary stats for the user."""
        goals = self.ref.collection("goals")\
                        .where(filter=FieldFilter("status", "==", "active"))\
                        .get()
        completed = self.ref.collection("goals")\
                            .where(filter=FieldFilter("status", "==", "completed"))\
                            .get()
        habits = self.ref.collection("habits").get()
        total_streak = sum(h.to_dict().get("streak", 0) for h in habits)

        return {
            "active_goals": len(goals),
            "completed_goals": len(completed),
            "total_habits": len(habits),
            "total_streak_days": total_streak
        }