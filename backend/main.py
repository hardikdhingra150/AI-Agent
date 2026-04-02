from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from agent.core import LifeOSAgent
from agent.memory import MemoryManager
from google.cloud.firestore_v1.base_query import FieldFilter
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="LifeOS API", version="1.0.0")

app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "http://localhost:3000",
                   "https://your-app.web.app"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ─── Request Models ────────────────────────────────────────────────────────────

class SetupRequest(BaseModel):
    uid: str
    name: str
    timezone: str = "Asia/Kolkata"

class ChatRequest(BaseModel):
    uid: str
    message: str

class GoalRequest(BaseModel):
    uid: str
    title: str
    domain: str = "general"

class ProgressRequest(BaseModel):
    uid: str
    goal_title: str
    progress: int  # 0-100

class HabitRequest(BaseModel):
    uid: str
    name: str
    domain: str = "general"
    frequency: str = "daily"

class LogHabitRequest(BaseModel):
    uid: str
    habit_name: str

class MemoryUpdateRequest(BaseModel):
    uid: str
    key: str
    value: str

# ─── Core Routes ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "LifeOS API running", "version": "1.0.0"}

@app.post("/setup")
async def setup_user(req: SetupRequest):
    mm = MemoryManager(req.uid)
    mm.init_user(name=req.name, timezone=req.timezone)
    return {"status": "ok", "message": f"User {req.name} initialized"}

@app.get("/context/{uid}")
async def get_context(uid: str):
    mm = MemoryManager(uid)
    ctx = mm.get_context()
    if not ctx:
        raise HTTPException(status_code=404, detail="User not found")
    return ctx

# ─── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        agent = LifeOSAgent(req.uid)
        response = agent.run(req.message)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/briefing/{uid}")
async def get_briefing(uid: str):
    try:
        agent = LifeOSAgent(uid)
        briefing = agent.generate_morning_briefing()
        return {"briefing": briefing}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Goals ─────────────────────────────────────────────────────────────────────

@app.post("/goal")
async def add_goal(req: GoalRequest):
    mm = MemoryManager(req.uid)
    mm.add_goal(req.title, req.domain)
    return {"status": "ok", "goal": req.title}

@app.get("/goals/{uid}")
async def get_goals(uid: str):
    mm = MemoryManager(uid)
    from firebase_admin import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
    goals = [g.to_dict() for g in
             mm.ref.collection("goals")
             .where(filter=FieldFilter("status", "==", "active"))
             .stream()]
    return {"goals": goals, "count": len(goals)}

@app.post("/goal/progress")
async def update_goal_progress(req: ProgressRequest):
    if not 0 <= req.progress <= 100:
        raise HTTPException(status_code=400, detail="Progress must be 0-100")
    mm = MemoryManager(req.uid)
    from google.cloud.firestore_v1.base_query import FieldFilter
    goals = mm.ref.collection("goals")\
                  .where(filter=FieldFilter("title", "==", req.goal_title))\
                  .get()
    if not goals:
        raise HTTPException(status_code=404, detail="Goal not found")
    goals[0].reference.update({"progress": req.progress})
    return {"status": "ok", "goal": req.goal_title, "progress": req.progress}

@app.delete("/goal/{uid}/{goal_title}")
async def complete_goal(uid: str, goal_title: str):
    mm = MemoryManager(uid)
    from google.cloud.firestore_v1.base_query import FieldFilter
    goals = mm.ref.collection("goals")\
                  .where(filter=FieldFilter("title", "==", goal_title))\
                  .get()
    if not goals:
        raise HTTPException(status_code=404, detail="Goal not found")
    goals[0].reference.update({"status": "completed"})
    return {"status": "ok", "message": f"Goal '{goal_title}' marked complete 🎉"}

# ─── Habits ────────────────────────────────────────────────────────────────────

@app.post("/habit")
async def add_habit(req: HabitRequest):
    mm = MemoryManager(req.uid)
    mm.add_habit(req.name, req.domain, req.frequency)
    return {"status": "ok", "habit": req.name}

@app.get("/habits/{uid}")
async def get_habits(uid: str):
    mm = MemoryManager(uid)
    habits = [h.to_dict() for h in mm.ref.collection("habits").stream()]
    return {"habits": habits, "count": len(habits)}

@app.post("/habit/log")
async def log_habit(req: LogHabitRequest):
    mm = MemoryManager(req.uid)
    success = mm.log_habit(req.habit_name)
    if not success:
        raise HTTPException(status_code=404,
                            detail=f"Habit '{req.habit_name}' not found")
    return {"status": "ok", "message": f"Logged '{req.habit_name}' 🔥"}

# ─── Memory ────────────────────────────────────────────────────────────────────

@app.post("/memory/update")
async def update_memory(req: MemoryUpdateRequest):
    mm = MemoryManager(req.uid)
    mm.update_memory(req.key, req.value)
    return {"status": "ok", "key": req.key, "value": req.value}

# ─── History ───────────────────────────────────────────────────────────────────

@app.get("/history/{uid}")
async def get_history(uid: str, limit: int = 20):
    mm = MemoryManager(uid)
    from firebase_admin import firestore
    history = [i.to_dict() for i in
               mm.ref.collection("interactions")
               .order_by("timestamp",
                         direction=firestore.Query.DESCENDING)
               .limit(limit).stream()]
    return {"history": list(reversed(history)), "count": len(history)}

@app.delete("/history/{uid}")
async def clear_history(uid: str):
    mm = MemoryManager(uid)
    interactions = mm.ref.collection("interactions").stream()
    for doc in interactions:
        doc.reference.delete()
    return {"status": "ok", "message": "History cleared"}