import os
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "building_log.txt")

def log(event, room=None, detail=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    room_str   = f" | Raum: {room}" if room   else ""
    detail_str = f" | {detail}"      if detail else ""
    line = f"[{now}]{room_str} | {event}{detail_str}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)