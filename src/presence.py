import json
import os
from datetime import datetime
from logger import log

PRESENCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presence.json")

ROOM_ASSIGNMENTS = {
    "Buero":       {"employee_id": "E001", "name": "Schneider"},
    "Meetingraum": {"employee_id": None,   "name": None},
    "Serverraum":  {"employee_id": None,   "name": None},
}

def _load():
    if not os.path.exists(PRESENCE_FILE):
        return {}
    with open(PRESENCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data):
    with open(PRESENCE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def confirm(room):
    assignment = ROOM_ASSIGNMENTS.get(room)
    if not assignment or not assignment["employee_id"]:
        log("Presence", room, "Kein Mitarbeiter zugewiesen")
        return False
    data   = _load()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    emp_id = assignment["employee_id"]
    data[emp_id] = {
        "name":      assignment["name"],
        "room":      room,
        "confirmed": now,
        "left":      None,
    }
    _save(data)
    log("Presence bestaetigt", room, f"{assignment['name']} ({emp_id})")
    return True

def leave(room):
    assignment = ROOM_ASSIGNMENTS.get(room)
    if not assignment or not assignment["employee_id"]:
        return
    data   = _load()
    emp_id = assignment["employee_id"]
    if emp_id in data and data[emp_id]["left"] is None:
        data[emp_id]["left"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save(data)
        log("Presence verlassen", room, f"{assignment['name']} ({emp_id})")

def get_confirmed(room):
    assignment = ROOM_ASSIGNMENTS.get(room)
    if not assignment or not assignment["employee_id"]:
        return None
    data   = _load()
    emp_id = assignment["employee_id"]
    if emp_id not in data:
        return None
    entry = data[emp_id]
    if entry["room"] == room and entry["left"] is None:
        return entry
    return None

def get_all_confirmed():
    data   = _load()
    result = []
    for emp_id, entry in data.items():
        if entry["left"] is None:
            duration = 0
            try:
                fmt      = "%Y-%m-%d %H:%M:%S"
                ci       = datetime.strptime(entry["confirmed"], fmt)
                duration = int((datetime.now() - ci).total_seconds() / 60)
            except Exception:
                pass
            result.append({
                "id":               emp_id,
                "name":             entry["name"],
                "room":             entry["room"],
                "confirmed":        entry["confirmed"],
                "duration_minutes": duration,
            })
    return result

def get_session_duration_minutes(room):
    entry = get_confirmed(room)
    if not entry:
        return 0
    fmt = "%Y-%m-%d %H:%M:%S"
    ci  = datetime.strptime(entry["confirmed"], fmt)
    return int((datetime.now() - ci).total_seconds() / 60)