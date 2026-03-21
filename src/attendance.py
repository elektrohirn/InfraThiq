import json
import os
from datetime import datetime
from logger import log

ATTENDANCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attendance.json")

def _load():
    if not os.path.exists(ATTENDANCE_FILE):
        return {}
    with open(ATTENDANCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data):
    with open(ATTENDANCE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def check_in(employee_id, name):
    data = _load()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    if employee_id not in data:
        data[employee_id] = {"name": name, "records": []}

    for record in data[employee_id]["records"]:
        if record["date"] == today and record.get("check_out") is None:
            print(f">> {name} ist bereits eingecheckt.")
            return

    data[employee_id]["records"].append({
        "date": today,
        "check_in": now,
        "check_out": None,
    })
    _save(data)
    log("Check-in Gebäude", detail=f"{name} ({employee_id})")
    print(f">> {name} eingecheckt um {now}.")

def check_out(employee_id):
    data = _load()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    if employee_id not in data:
        print(">> Mitarbeiter nicht gefunden.")
        return

    for record in reversed(data[employee_id]["records"]):
        if record["date"] == today and record.get("check_out") is None:
            record["check_out"] = now
            _save(data)
            name = data[employee_id]["name"]
            log("Check-out Gebäude", detail=f"{name} ({employee_id})")
            print(f">> {name} ausgecheckt um {now}.")
            return

    print(">> Kein offener Check-in gefunden.")

def get_present():
    data  = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    present = []
    for emp_id, emp_data in data.items():
        for record in emp_data["records"]:
            if record["date"] == today and record.get("check_out") is None:
                present.append({
                    "id": emp_id,
                    "name": emp_data["name"],
                    "check_in": record["check_in"],
                })
    return present

def get_summary():
    data  = _load()
    today = datetime.now().strftime("%Y-%m-%d")
    summary = []
    for emp_id, emp_data in data.items():
        for record in emp_data["records"]:
            if record["date"] == today:
                duration = None
                if record.get("check_out"):
                    fmt = "%Y-%m-%d %H:%M:%S"
                    ci  = datetime.strptime(record["check_in"],  fmt)
                    co  = datetime.strptime(record["check_out"], fmt)
                    mins = int((co - ci).total_seconds() / 60)
                    duration = f"{mins // 60}h {mins % 60}min"
                summary.append({
                    "name":      emp_data["name"],
                    "check_in":  record["check_in"],
                    "check_out": record.get("check_out", "noch anwesend"),
                    "duration":  duration or "läuft",
                })
    return summary