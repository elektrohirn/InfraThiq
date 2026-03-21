import json
import os
from actuator import Actuator
from control import temp_setpoints, room_orientation

ROOMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rooms.json")

DEFAULT_ROOMS = {
    "Buero":       {"setpoint": 21, "orientation": 180},
    "Meetingraum": {"setpoint": 21, "orientation": 270},
    "Serverraum":  {"setpoint": 19, "orientation": 0},
}

def _load_config():
    if not os.path.exists(ROOMS_FILE):
        return DEFAULT_ROOMS
    with open(ROOMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_config(config):
    with open(ROOMS_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_rooms():
    config = _load_config()
    building_state = {}
    actuator_state = {}
    for room, cfg in config.items():
        building_state[room] = {
            "co2": 500, "temp": cfg["setpoint"],
            "light": 0, "occupancy": 0, "light_sensor": 50,
        }
        actuator_state[room] = {
            "vent":  Actuator(f"{room}_vent"),
            "heat":  Actuator(f"{room}_heat"),
            "cool":  Actuator(f"{room}_cool"),
            "blind": Actuator(f"{room}_blind"),
        }
        temp_setpoints[room]   = cfg["setpoint"]
        room_orientation[room] = cfg["orientation"]
    return building_state, actuator_state

def add_room(room, setpoint=21, orientation=180):
    config = _load_config()
    if room in config:
        return False
    config[room] = {"setpoint": setpoint, "orientation": orientation}
    _save_config(config)
    return True

def delete_room(room):
    protected = ["Buero", "Meetingraum", "Serverraum"]
    if room in protected:
        return False
    config = _load_config()
    if room in config:
        del config[room]
        _save_config(config)
    return True