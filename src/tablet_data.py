import json
import os

TABLET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tablet_data.json")

DEFAULT_SCENES = [
    {"id": "presentation", "name": "Präsentation", "light": 100, "blind": 80},
    {"id": "focus",        "name": "Fokus",         "light": 70,  "blind": 50},
    {"id": "relaxed",      "name": "Entspannt",      "light": 40,  "blind": 0},
]

DEFAULT_RADIO = [
    {"id": "radiobob", "name": "Radio Bob – Best of Rock", "url": "https://streams.radiobob.de/bob-acdc/mp3-192/mediaplayer"},
    {"id": "wdr2",     "name": "WDR 2",                    "url": "https://wdr-wdr2-aachenundregion.icecastssl.wdr.de/wdr/wdr2/aachenundregion/mp3/128/stream.mp3"},
]

DEFAULT_CANTEEN = [
    {"id": "1", "name": "Tagessuppe",          "price": 2.50, "category": "Suppe"},
    {"id": "2", "name": "Schnitzel mit Pommes", "price": 6.90, "category": "Hauptgericht"},
    {"id": "3", "name": "Veggie Bowl",          "price": 5.90, "category": "Hauptgericht"},
    {"id": "4", "name": "Kaffee",               "price": 1.20, "category": "Getränk"},
    {"id": "5", "name": "Wasser 0.5L",          "price": 0.80, "category": "Getränk"},
]

def _load():
    if not os.path.exists(TABLET_FILE):
        return {}
    with open(TABLET_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data):
    with open(TABLET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_profile(employee_id):
    data     = _load()
    profiles = data.get("profiles", {})
    if employee_id not in profiles:
        return {
            "employee_id":   employee_id,
            "temp":          21,
            "vent":          0,
            "light":         100,
            "blind":         0,
            "auto_media":    False,
            "auto_media_id": None,
            "scenes":        DEFAULT_SCENES.copy(),
            "radio_favs":    ["radiobob"],
        }
    return profiles[employee_id]

def save_profile(employee_id, profile):
    data = _load()
    if "profiles" not in data:
        data["profiles"] = {}
    data["profiles"][employee_id] = profile
    _save(data)

def get_scenes(employee_id):
    profile = get_profile(employee_id)
    return profile.get("scenes", DEFAULT_SCENES.copy())

def save_scene(employee_id, scene):
    profile = get_profile(employee_id)
    scenes  = profile.get("scenes", DEFAULT_SCENES.copy())
    for i, s in enumerate(scenes):
        if s["id"] == scene["id"]:
            scenes[i] = scene
            break
    else:
        scenes.append(scene)
    profile["scenes"] = scenes
    save_profile(employee_id, profile)

def get_meetings(room=None):
    data     = _load()
    meetings = data.get("meetings", [])
    if room:
        meetings = [m for m in meetings if m["room"] == room]
    return meetings

def book_meeting(meeting):
    import uuid
    data = _load()
    if "meetings" not in data:
        data["meetings"] = []
    meeting["id"] = str(uuid.uuid4())[:8]
    data["meetings"].append(meeting)
    _save(data)
    return meeting["id"]

def cancel_meeting(meeting_id):
    data     = _load()
    meetings = data.get("meetings", [])
    data["meetings"] = [m for m in meetings if m["id"] != meeting_id]
    _save(data)

def get_canteen_menu():
    return DEFAULT_CANTEEN

def get_canteen_orders():
    data = _load()
    return data.get("canteen_orders", [])

def place_canteen_order(employee_id, name, items):
    import uuid
    from datetime import datetime
    data = _load()
    if "canteen_orders" not in data:
        data["canteen_orders"] = []
    order = {
        "id":          str(uuid.uuid4())[:8],
        "employee_id": employee_id,
        "name":        name,
        "items":       items,
        "total":       sum(i["price"] * i.get("qty", 1) for i in items),
        "time":        datetime.now().strftime("%H:%M"),
        "status":      "bestellt",
    }
    data["canteen_orders"].append(order)
    _save(data)
    return order

def get_radio_stations(employee_id=None):
    stations = DEFAULT_RADIO.copy()
    if employee_id:
        profile = get_profile(employee_id)
        fav_ids = profile.get("radio_favs", [])
        for s in stations:
            s["favorite"] = s["id"] in fav_ids
    return stations

def toggle_radio_fav(employee_id, station_id):
    profile = get_profile(employee_id)
    favs    = profile.get("radio_favs", [])
    if station_id in favs:
        favs.remove(station_id)
    else:
        favs.append(station_id)
    profile["radio_favs"] = favs
    save_profile(employee_id, profile)
    return favs

_quick_settings = {}

def set_quick(room, key, value):
    if room not in _quick_settings:
        _quick_settings[room] = {}
    _quick_settings[room][key] = value

def get_quick(room):
    return _quick_settings.get(room, {})

def clear_quick(room):
    if room in _quick_settings:
        del _quick_settings[room]