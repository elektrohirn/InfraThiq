import time
import threading
from datetime import datetime
from simulation import simulate_environment
from control import apply_control, temp_setpoints
from actuator import Actuator
from logger import log
from sps import connect, disconnect, push_actuators, pull_sensors, is_connected, reconnect_if_needed
from attendance import check_in, check_out, get_present, get_summary
from presence import confirm, leave, get_all_confirmed, ROOM_ASSIGNMENTS
from adaptive import record, record_absence, apply_adaptive, get_memory_summary, record_manual_vent, record_no_vent
import webserver

from roomstore import load_rooms, add_room, delete_room
building_state, actuator_state = load_rooms()

outside_light    = 0
sun_position     = 90
cloud_cover      = 0.3
direct_radiation = 0
hour             = 8
minute           = 0

ACTUATORS = ["vent", "heat", "cool", "blind"]

connect()
webserver.start(building_state, actuator_state)

def get_rooms():
    return list(building_state.keys())

def print_dashboard():
    sps_status = "SPS: Verbunden" if is_connected() else "SPS: Simulation"
    confirmed  = {e["room"]: e["name"] for e in get_all_confirmed()}
    print(f"\nUhrzeit: {hour:02d}:{minute:02d} | Sonne: {sun_position:.0f}° | Wolken: {cloud_cover:.2f} | Außenlicht: {outside_light:.0f} | Strahlung: {direct_radiation:.0f} | {sps_status}")
    print(f"{'Raum':<14}{'CO2':<7}{'Temp':<7}{'Licht':<7}{'Lueft':<7}{'Heiz':<7}{'Kuehl':<7}{'Jalousie':<10}{'Pers':<6}{'Bestaetigt':<12}")
    print("-" * 85)
    for room in building_state:
        s         = building_state[room]
        a         = actuator_state[room]
        vent_str  = str(a['vent'].get_value())  + (' [M]' if a['vent'].mode  == 'manual' else '')
        heat_str  = str(a['heat'].get_value())  + (' [M]' if a['heat'].mode  == 'manual' else '')
        cool_str  = str(a['cool'].get_value())  + (' [M]' if a['cool'].mode  == 'manual' else '')
        blind_str = str(a['blind'].get_value()) + (' [M]' if a['blind'].mode == 'manual' else '')
        best      = confirmed.get(room, "-")
        print(f"{room:<14}{int(s['co2']):<7}{s['temp']:<7.1f}{s['light']:<7}{vent_str:<7}{heat_str:<7}{cool_str:<7}{blind_str:<10}{s['occupancy']:<6}{best:<12}")
    print("\nBefehle: 'heat Buero 100' | 'cool Buero 50' | 'confirm Buero' | 'leave Buero' | 'anwesend' | 'tagesbericht' | 'gedaechtnis'")

def handle_input():
    while True:
        try:
            cmd = input().strip().lower().split()
            if not cmd:
                continue

            if cmd == ['auto', 'all']:
                for room in actuator_state:
                    for act in actuator_state[room].values():
                        act.set_auto()
                log("Automatik wiederhergestellt", detail="Alle Aktuatoren")
                print(">> Alle Aktuatoren auf Automatik gesetzt.")
                continue

            if len(cmd) == 3 and cmd[0] == 'auto':
                rooms = get_rooms()
                room  = next((r for r in rooms if r.lower() == cmd[1]), None)
                act   = cmd[2]
                if room and act in ACTUATORS:
                    actuator_state[room][act].set_auto()
                    log("Automatik wiederhergestellt", room, act)
                    print(f">> {room} / {act} auf Automatik gesetzt.")
                else:
                    print(">> Unbekannter Raum oder Aktuator.")
                continue

            if len(cmd) == 3 and cmd[0] in ACTUATORS:
                act   = cmd[0]
                rooms = get_rooms()
                room  = next((r for r in rooms if r.lower() == cmd[1]), None)
                try:
                    value = int(cmd[2])
                except ValueError:
                    print(">> Wert muss eine Zahl sein.")
                    continue
                if room:
                    actuator_state[room][act].set_manual(value)
                    log("Manueller Eingriff", room, f"{act} auf {value} gesetzt")
                    print(f">> {room} / {act} manuell auf {value} gesetzt.")
                else:
                    print(">> Unbekannter Raum.")
                continue

            if len(cmd) == 2 and cmd[0] == 'confirm':
                rooms = get_rooms()
                room  = next((r for r in rooms if r.lower() == cmd[1]), None)
                if room:
                    ok = confirm(room)
                    if not ok:
                        print(f">> Kein Mitarbeiter fuer {room} zugewiesen.")
                else:
                    print(">> Unbekannter Raum.")
                continue

            if len(cmd) == 2 and cmd[0] == 'leave':
                rooms = get_rooms()
                room  = next((r for r in rooms if r.lower() == cmd[1]), None)
                if room:
                    leave(room)
                else:
                    print(">> Unbekannter Raum.")
                continue

            if len(cmd) >= 3 and cmd[0] == 'checkin':
                emp_id = cmd[1]
                name   = cmd[2]
                check_in(emp_id, name, "Eingang")
                continue

            if len(cmd) == 2 and cmd[0] == 'checkout':
                check_out(cmd[1])
                continue

            if cmd == ['anwesend']:
                present        = get_present()
                confirmed_list = get_all_confirmed()
                print("-- Zeiterfassung --")
                if present:
                    for p in present:
                        print(f"  {p['name']} | seit {p['check_in']}")
                else:
                    print("  Niemand eingecheckt.")
                print("-- Raumbestaetigt --")
                if confirmed_list:
                    for p in confirmed_list:
                        print(f"  {p['name']} | {p['room']} | seit {p['confirmed']} | {p['duration_minutes']} Min")
                else:
                    print("  Niemand bestaetigt.")
                continue

            if cmd == ['tagesbericht']:
                summary = get_summary()
                if summary:
                    for s in summary:
                        print(f"  {s['name']} | {s['check_in']} -> {s['check_out']} | {s['duration']}")
                else:
                    print(">> Keine Eintraege heute.")
                continue

            if cmd == ['gedaechtnis']:
                summary = get_memory_summary()
                if summary:
                    for e in summary:
                        print(f"  {e['name']} ({e['employee_id']}) | {e['type']} | {e['day']} {e['hour']:02d}:00 | {e['probability']:.0%} | Messungen: {e['samples']}")
                else:
                    print(">> Noch nicht genug Daten (mind. 20 Messungen pro Zeitslot).")
                continue

            print(">> Unbekannter Befehl.")

        except EOFError:
            break

input_thread = threading.Thread(target=handle_input, daemon=True)
input_thread.start()

try:
    while True:
        if not webserver.is_paused():
            reconnect_if_needed()

            building_state = pull_sensors(building_state)

            building_state, outside_light, sun_position, cloud_cover, direct_radiation = simulate_environment(
                building_state, actuator_state, outside_light, sun_position, cloud_cover, hour, minute
            )

            actuator_state = apply_control(
                building_state, actuator_state, outside_light, sun_position, cloud_cover, hour, direct_radiation
            )

            push_actuators(actuator_state)

            weekday       = datetime.now().weekday()
            confirmed_now = get_all_confirmed()
            record(confirmed_now, weekday, hour)

            for room, assignment in ROOM_ASSIGNMENTS.items():
                emp_id = assignment.get("employee_id")
                name   = assignment.get("name", "")
                if not emp_id:
                    continue
                if actuator_state[room]["vent"].mode == "manual":
                    record_manual_vent(emp_id, name, weekday, hour)
                else:
                    record_no_vent(emp_id, name, weekday, hour)

            confirmed_ids = {e["id"] for e in confirmed_now}
            for room, assignment in ROOM_ASSIGNMENTS.items():
                emp_id = assignment.get("employee_id")
                name   = assignment.get("name", "")
                if emp_id and emp_id not in confirmed_ids:
                    record_absence(emp_id, name, weekday, hour)

            actuator_state = apply_adaptive(
                building_state, actuator_state, weekday, hour, temp_setpoints, ROOM_ASSIGNMENTS
            )

        webserver.update(
            building_state, actuator_state, outside_light, sun_position,
            cloud_cover, direct_radiation, hour, minute
        )

        print_dashboard()

        minute += 10
        if minute >= 60:
            minute = 0
            hour   = (hour + 1) % 24

        time.sleep(2)

except KeyboardInterrupt:
    disconnect()
    log("System", detail="Programm beendet")
    print("\n>> System beendet.")