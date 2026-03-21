import json
import os
from logger import log

ADAPTIVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adaptive_memory.json")

MIN_SAMPLES                = 20
PATTERN_THRESHOLD_EMPTY    = 0.15
PATTERN_THRESHOLD_OCCUPIED = 0.85
VENT_PATTERN_THRESHOLD     = 0.75
CO2_OVERRIDE_THRESHOLD     = 800

def _load():
    if not os.path.exists(ADAPTIVE_FILE):
        return {}
    with open(ADAPTIVE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data):
    with open(ADAPTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _key(employee_id, weekday, hour):
    return f"{employee_id}_{weekday}_{hour}"

def _vent_key(employee_id, weekday, hour):
    return f"vent_{employee_id}_{weekday}_{hour}"

def record(presence_data, weekday, hour, min_duration_minutes=30):
    data = _load()
    for entry in presence_data:
        emp_id   = entry["id"]
        duration = entry.get("duration_minutes", 0)
        if duration < min_duration_minutes:
            continue
        k = _key(emp_id, weekday, hour)
        if k not in data:
            data[k] = {"occupied": 0, "total": 0, "name": entry.get("name", "")}
        data[k]["total"]    += 1
        data[k]["occupied"] += 1
    _save(data)

def record_absence(employee_id, name, weekday, hour):
    data = _load()
    k = _key(employee_id, weekday, hour)
    if k not in data:
        data[k] = {"occupied": 0, "total": 0, "name": name}
    data[k]["total"] += 1
    _save(data)

def record_manual_vent(employee_id, name, weekday, hour):
    data = _load()
    k = _vent_key(employee_id, weekday, hour)
    if k not in data:
        data[k] = {"triggered": 0, "total": 0, "name": name, "type": "vent"}
    data[k]["triggered"] += 1
    data[k]["total"]     += 1
    _save(data)

def record_no_vent(employee_id, name, weekday, hour):
    data = _load()
    k = _vent_key(employee_id, weekday, hour)
    if k not in data:
        data[k] = {"triggered": 0, "total": 0, "name": name, "type": "vent"}
    data[k]["total"] += 1
    _save(data)

def get_probability(employee_id, weekday, hour):
    data = _load()
    k = _key(employee_id, weekday, hour)
    if k not in data:
        return None
    entry = data[k]
    if entry["total"] < MIN_SAMPLES:
        return None
    return entry["occupied"] / entry["total"]

def get_vent_probability(employee_id, weekday, hour):
    data = _load()
    k = _vent_key(employee_id, weekday, hour)
    if k not in data:
        return None
    entry = data[k]
    if entry["total"] < MIN_SAMPLES:
        return None
    return entry["triggered"] / entry["total"]

def apply_adaptive(building_state, actuator_state, weekday, hour, temp_setpoints, room_assignments):
    for room, assignment in room_assignments.items():
        emp_id = assignment.get("employee_id")
        name   = assignment.get("name", "")
        if not emp_id:
            continue

        co2       = building_state[room]["co2"]
        next_hour = (hour + 1) % 24

        prob = get_probability(emp_id, weekday, next_hour)
        if prob is not None:
            if prob <= PATTERN_THRESHOLD_EMPTY:
                if actuator_state[room]["heat"].mode == "auto":
                    actuator_state[room]["heat"].update_auto(0)
                    log("Adaptiv - Drosseln", room,
                        f"{name} | {prob:.0%} Belegung erwartet | Heizung gedrosselt")
                if actuator_state[room]["vent"].mode == "auto":
                    if co2 < CO2_OVERRIDE_THRESHOLD and actuator_state[room]["vent"].get_value() > 30:
                        actuator_state[room]["vent"].update_auto(30)
                        log("Adaptiv - Drosseln", room,
                            f"{name} | {prob:.0%} Belegung erwartet | Lueftung reduziert")
            elif prob >= PATTERN_THRESHOLD_OCCUPIED:
                temp     = building_state[room]["temp"]
                setpoint = temp_setpoints.get(room, 21)
                if actuator_state[room]["heat"].mode == "auto" and temp < setpoint - 0.5:
                    actuator_state[room]["heat"].update_auto(70)
                    log("Adaptiv - Vorheizen", room,
                        f"{name} | {prob:.0%} Belegung erwartet | Vorheizen aktiv")

        vent_prob = get_vent_probability(emp_id, weekday, hour)
        if vent_prob is not None and vent_prob >= VENT_PATTERN_THRESHOLD:
            if actuator_state[room]["vent"].mode == "auto":
                current_vent = actuator_state[room]["vent"].get_value()
                if co2 < CO2_OVERRIDE_THRESHOLD and current_vent < 60:
                    actuator_state[room]["vent"].update_auto(60)
                    log("Adaptiv - Lueftung", room,
                        f"{name} | {vent_prob:.0%} Lüftungsgewohnheit | vorausschauend aktiviert")

    return actuator_state

def get_memory_summary():
    data   = _load()
    days   = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    result = []
    for k, v in data.items():
        if v["total"] < MIN_SAMPLES:
            continue
        if v.get("type") == "vent":
            parts   = k.split("_")
            emp_id  = parts[1]
            weekday = int(parts[2])
            hour    = int(parts[3])
            prob    = v["triggered"] / v["total"]
            result.append({
                "employee_id": emp_id,
                "name":        v.get("name", ""),
                "day":         days[weekday],
                "hour":        hour,
                "probability": prob,
                "samples":     v["total"],
                "type":        "Lueftung",
            })
        else:
            parts   = k.split("_")
            emp_id  = parts[0]
            weekday = int(parts[1])
            hour    = int(parts[2])
            prob    = v["occupied"] / v["total"]
            result.append({
                "employee_id": emp_id,
                "name":        v.get("name", ""),
                "day":         days[weekday],
                "hour":        hour,
                "probability": prob,
                "samples":     v["total"],
                "type":        "Anwesenheit",
            })
    result.sort(key=lambda x: (x["employee_id"], x["type"], x["day"], x["hour"]))
    return result