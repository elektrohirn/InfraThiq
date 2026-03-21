from flask import Flask, jsonify, request, render_template_string, Response
import threading
import os
import logging

app = Flask(__name__)

_building_state   = {}
_actuator_state   = {}
_outside_light    = 0
_sun_position     = 0
_cloud_cover      = 0
_direct_radiation = 0
_hour             = 0
_minute           = 0
_sim_paused       = False
_emergency        = False

def init(building_state, actuator_state):
    global _building_state, _actuator_state
    _building_state = building_state
    _actuator_state = actuator_state

def update(building_state, actuator_state, outside_light, sun_position, cloud_cover, direct_radiation, hour, minute):
    global _building_state, _actuator_state, _outside_light, _sun_position
    global _cloud_cover, _direct_radiation, _hour, _minute
    _building_state   = building_state
    _actuator_state   = actuator_state
    _outside_light    = outside_light
    _sun_position     = sun_position
    _cloud_cover      = cloud_cover
    _direct_radiation = direct_radiation
    _hour             = hour
    _minute           = minute

def is_paused():
    return _sim_paused

def is_emergency():
    return _emergency

def read_log(max_lines=500):
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "building_log.txt")
    if not os.path.exists(log_file):
        return []
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return [l.strip() for l in lines[-max_lines:]][::-1]

@app.route('/api/state')
def api_state():
    from sps import is_connected
    from presence import get_all_confirmed
    confirmed = {e["room"]: e["name"] for e in get_all_confirmed()}
    bs = {}
    for room, s in _building_state.items():
        bs[room] = dict(s)
        bs[room]["confirmed"] = confirmed.get(room)
    acts = {}
    for room, a in _actuator_state.items():
        acts[room] = {
            k: {"value": v.get_value(), "mode": v.mode}
            for k, v in a.items()
        }
    return jsonify({
        "building_state":   bs,
        "actuator_state":   acts,
        "outside_light":    _outside_light,
        "sun_position":     _sun_position,
        "cloud_cover":      _cloud_cover,
        "direct_radiation": _direct_radiation,
        "hour":             _hour,
        "minute":           _minute,
        "sps_connected":    is_connected(),
        "sim_paused":       _sim_paused,
        "emergency":        _emergency,
    })

@app.route('/api/manual', methods=['POST'])
def api_manual():
    data = request.json
    room = data.get('room')
    act  = data.get('actuator')
    val  = data.get('value', 0)
    if room in _actuator_state and act in _actuator_state[room]:
        _actuator_state[room][act].set_manual(val)
        from logger import log
        log("Browser - Manuell", room, f"{act} auf {val}")
    return jsonify({"ok": True})

@app.route('/api/auto', methods=['POST'])
def api_auto():
    data = request.json
    room = data.get('room')
    act  = data.get('actuator')
    if room in _actuator_state and act in _actuator_state[room]:
        _actuator_state[room][act].set_auto()
        from logger import log
        log("Browser - Auto", room, act)
    return jsonify({"ok": True})

@app.route('/api/auto_all', methods=['POST'])
def api_auto_all():
    from logger import log
    for room in _actuator_state:
        for act in _actuator_state[room].values():
            act.set_auto()
    log("Browser - Auto", detail="Alle Aktuatoren")
    return jsonify({"ok": True})

@app.route('/api/system/pause', methods=['POST'])
def api_pause():
    global _sim_paused
    _sim_paused = not _sim_paused
    from logger import log
    log("System", detail=f"Simulation {'pausiert' if _sim_paused else 'fortgesetzt'}")
    return jsonify({"paused": _sim_paused})

@app.route('/api/system/emergency', methods=['POST'])
def api_emergency():
    global _emergency
    _emergency = not _emergency
    from logger import log
    log("System", detail=f"Notfallmodus {'aktiviert' if _emergency else 'deaktiviert'}")
    if _emergency:
        for room in _actuator_state:
            _actuator_state[room]["vent"].set_manual(100)
            _actuator_state[room]["heat"].set_manual(0)
            _actuator_state[room]["cool"].set_manual(0)
            _actuator_state[room]["blind"].set_manual(0)
    return jsonify({"emergency": _emergency})

@app.route('/api/system/settime', methods=['POST'])
def api_settime():
    global _hour, _minute
    data    = request.json
    _hour   = int(data.get('hour',   _hour))
    _minute = int(data.get('minute', _minute))
    from logger import log
    log("System", detail=f"Zeit gesetzt auf {_hour:02d}:{_minute:02d}")
    return jsonify({"ok": True, "hour": _hour, "minute": _minute})

@app.route('/api/sps/status')
def api_sps_status():
    from sps import is_connected
    import sps as sps_module
    return jsonify({
        "connected":  is_connected(),
        "ams_net_id": sps_module.AMS_NET_ID,
        "port":       sps_module.ADS_PORT,
    })

@app.route('/api/sps/reconnect', methods=['POST'])
def api_sps_reconnect():
    from sps import connect
    connect()
    from sps import is_connected
    return jsonify({"connected": is_connected()})

@app.route('/api/sps/config', methods=['POST'])
def api_sps_config():
    import sps as sps_module
    data = request.json
    sps_module.AMS_NET_ID = data.get('ams_net_id', sps_module.AMS_NET_ID)
    sps_module.ADS_PORT   = int(data.get('port', sps_module.ADS_PORT))
    from logger import log
    log("SPS Konfiguration", detail=f"AMS: {sps_module.AMS_NET_ID} Port: {sps_module.ADS_PORT}")
    return jsonify({"ok": True})

@app.route('/api/config/rooms')
def api_rooms():
    from presence import ROOM_ASSIGNMENTS
    return jsonify({"rooms": ROOM_ASSIGNMENTS})

@app.route('/api/config/rooms/add', methods=['POST'])
def api_rooms_add():
    from presence import ROOM_ASSIGNMENTS
    from actuator import Actuator
    from control import temp_setpoints, room_orientation
    from roomstore import add_room
    data   = request.json
    room   = data.get('room')
    sp     = float(data.get('setpoint', 21))
    orient = int(data.get('orientation', 180))
    if not room or room in _building_state:
        return jsonify({"ok": False, "error": "Raum existiert bereits oder Name fehlt"})
    add_room(room, sp, orient)
    _building_state[room] = {"co2": 500, "temp": sp, "light": 0, "occupancy": 0, "light_sensor": 50}
    _actuator_state[room] = {
        "vent":  Actuator(f"{room}_vent"),
        "heat":  Actuator(f"{room}_heat"),
        "cool":  Actuator(f"{room}_cool"),
        "blind": Actuator(f"{room}_blind"),
    }
    ROOM_ASSIGNMENTS[room] = {"employee_id": None, "name": None}
    temp_setpoints[room]   = sp
    room_orientation[room] = orient
    from logger import log
    log("Konfiguration", room, "Raum angelegt")
    return jsonify({"ok": True})

@app.route('/api/config/rooms/delete', methods=['POST'])
def api_rooms_delete():
    from presence import ROOM_ASSIGNMENTS
    from control import temp_setpoints, room_orientation
    from roomstore import delete_room
    data = request.json
    room = data.get('room')
    ok   = delete_room(room)
    if not ok:
        return jsonify({"ok": False, "error": "Standardräume können nicht gelöscht werden"})
    if room in _building_state:  del _building_state[room]
    if room in _actuator_state:  del _actuator_state[room]
    if room in ROOM_ASSIGNMENTS: del ROOM_ASSIGNMENTS[room]
    if room in temp_setpoints:   del temp_setpoints[room]
    if room in room_orientation: del room_orientation[room]
    from logger import log
    log("Konfiguration", room, "Raum geloescht")
    return jsonify({"ok": True})

@app.route('/api/config/setpoints', methods=['GET', 'POST'])
def api_setpoints():
    from control import temp_setpoints
    if request.method == 'POST':
        data = request.json
        for room, val in data.items():
            if room in temp_setpoints:
                temp_setpoints[room] = float(val)
        from logger import log
        log("Konfiguration", detail=f"Sollwerte: {data}")
        return jsonify({"ok": True, "setpoints": temp_setpoints})
    return jsonify({"setpoints": temp_setpoints})

@app.route('/api/config/assign', methods=['POST'])
def api_assign():
    from presence import ROOM_ASSIGNMENTS
    data   = request.json
    room   = data.get('room')
    emp_id = data.get('employee_id')
    name   = data.get('name')
    if room in ROOM_ASSIGNMENTS:
        ROOM_ASSIGNMENTS[room]['employee_id'] = emp_id
        ROOM_ASSIGNMENTS[room]['name']        = name
        from logger import log
        log("Konfiguration", room, f"Mitarbeiter: {name} ({emp_id})")
    return jsonify({"ok": True})

@app.route('/api/diagnostics')
def api_diagnostics():
    warnings = []
    for room, s in _building_state.items():
        if s["co2"] > 1400:
            warnings.append({"room": room, "type": "CO2 kritisch", "value": f"{int(s['co2'])} ppm"})
        if s["temp"] > 27 or s["temp"] < 17:
            warnings.append({"room": room, "type": "Temperatur ausserhalb Toleranz", "value": f"{s['temp']:.1f} C"})
    for room, acts in _actuator_state.items():
        for act_name, act_obj in acts.items():
            if act_obj.mode == "manual":
                warnings.append({"room": room, "type": f"{act_name} im Manualmodus", "value": f"{act_obj.get_value()}%"})
            if act_name == "vent" and act_obj.get_value() == 100:
                warnings.append({"room": room, "type": "Lueftung dauerhaft 100%", "value": "Pruefen"})
    return jsonify({"warnings": warnings})

@app.route('/api/adaptive')
def api_adaptive():
    from adaptive import get_memory_summary
    return jsonify({"patterns": get_memory_summary()})

@app.route('/api/adaptive/min_samples', methods=['POST'])
def api_adaptive_min_samples():
    import adaptive as adp
    data = request.json
    adp.MIN_SAMPLES = int(data.get('min_samples', adp.MIN_SAMPLES))
    from logger import log
    log("Adaptiv", detail=f"Mindestmessungen auf {adp.MIN_SAMPLES} gesetzt")
    return jsonify({"ok": True, "min_samples": adp.MIN_SAMPLES})

@app.route('/api/adaptive/delete', methods=['POST'])
def api_adaptive_delete():
    import adaptive as adp
    data       = request.json
    emp_id     = data.get('employee_id')
    delete_all = data.get('all', False)
    mem        = adp._load()
    if delete_all and emp_id:
        keys = [k for k in mem if emp_id in k]
        for k in keys:
            del mem[k]
        adp._save(mem)
        from logger import log
        log("Adaptiv", detail=f"Alle Muster von {emp_id} geloescht")
    elif 'key' in data:
        k = data['key']
        if k in mem:
            del mem[k]
            adp._save(mem)
    return jsonify({"ok": True})

@app.route('/api/attendance')
def api_attendance():
    from attendance import get_present, get_summary
    return jsonify({
        "present": get_present(),
        "summary": get_summary(),
    })

@app.route('/api/log')
def api_log():
    filter_text = request.args.get('filter', '').lower()
    lines = read_log()
    if filter_text:
        lines = [l for l in lines if filter_text in l.lower()]
    return jsonify({"lines": lines})

@app.route('/api/log/export')
def api_log_export():
    lines = read_log(max_lines=10000)
    csv   = "Zeitstempel,Raum,Ereignis\n"
    for line in reversed(lines):
        csv += line.replace('|', ',') + "\n"
    return Response(csv, mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=building_log.csv"})

@app.route('/api/tablet/state/<room>')
def api_tablet_state(room):
    if room not in _building_state:
        return jsonify({"error": "Raum nicht gefunden"}), 404
    from presence import get_all_confirmed
    confirmed = {e["room"]: {"name": e["name"], "id": e["id"]} for e in get_all_confirmed()}
    s = _building_state[room]
    a = _actuator_state[room]
    return jsonify({
        "room":      room,
        "co2":       round(s["co2"]),
        "temp":      round(s["temp"], 1),
        "light":     s["light"],
        "occupancy": s["occupancy"],
        "confirmed": confirmed.get(room),
        "actuators": {k: {"value": v.get_value(), "mode": v.mode} for k, v in a.items()},
        "hour":      _hour,
        "minute":    _minute,
    })

@app.route('/api/tablet/checkin/<room>', methods=['POST'])
def api_tablet_checkin(room):
    from presence import confirm, ROOM_ASSIGNMENTS
    from tablet_data import get_profile
    ok = confirm(room)
    if not ok:
        return jsonify({"ok": False, "error": "Kein Mitarbeiter zugewiesen"})
    assignment = ROOM_ASSIGNMENTS.get(room, {})
    emp_id     = assignment.get("employee_id")
    profile    = get_profile(emp_id) if emp_id else {}
    from logger import log
    log("Tablet - Checkin", room, assignment.get("name", ""))
    return jsonify({"ok": True, "profile": profile})

@app.route('/api/tablet/checkout/<room>', methods=['POST'])
def api_tablet_checkout(room):
    from presence import leave
    from tablet_data import clear_quick
    leave(room)
    clear_quick(room)
    from logger import log
    log("Tablet - Checkout", room)
    return jsonify({"ok": True})

@app.route('/api/tablet/quick/<room>', methods=['POST'])
def api_tablet_quick(room):
    from tablet_data import set_quick
    data = request.json
    for key, val in data.items():
        set_quick(room, key, val)
        if key == "light" and room in _building_state:
            _building_state[room]["light"] = val
        if key in ("vent", "heat", "cool", "blind") and room in _actuator_state:
            _actuator_state[room][key].set_manual(val)
    return jsonify({"ok": True})

@app.route('/api/tablet/profile/<employee_id>', methods=['GET', 'POST'])
def api_tablet_profile(employee_id):
    from tablet_data import get_profile, save_profile
    if request.method == 'POST':
        profile = request.json
        save_profile(employee_id, profile)
        return jsonify({"ok": True})
    return jsonify(get_profile(employee_id))

@app.route('/api/tablet/scenes/<employee_id>', methods=['GET'])
def api_tablet_scenes(employee_id):
    from tablet_data import get_scenes
    return jsonify({"scenes": get_scenes(employee_id)})

@app.route('/api/tablet/scenes/<employee_id>/activate', methods=['POST'])
def api_tablet_scene_activate(employee_id):
    from tablet_data import get_scenes
    from logger import log
    data     = request.json
    scene_id = data.get("scene_id")
    room     = data.get("room")
    scenes   = get_scenes(employee_id)
    scene    = next((s for s in scenes if s["id"] == scene_id), None)
    if not scene or room not in _actuator_state:
        return jsonify({"ok": False})
    _actuator_state[room]["blind"].set_manual(scene["blind"])
    _building_state[room]["light"] = scene["light"]
    log("Tablet - Szene", room, scene["name"])
    return jsonify({"ok": True, "scene": scene})

@app.route('/api/tablet/scenes/<employee_id>/save', methods=['POST'])
def api_tablet_scene_save(employee_id):
    from tablet_data import save_scene
    scene = request.json
    save_scene(employee_id, scene)
    return jsonify({"ok": True})

@app.route('/api/tablet/radio/<employee_id>', methods=['GET'])
def api_tablet_radio(employee_id):
    from tablet_data import get_radio_stations
    return jsonify({"stations": get_radio_stations(employee_id)})

@app.route('/api/tablet/radio/<employee_id>/fav', methods=['POST'])
def api_tablet_radio_fav(employee_id):
    from tablet_data import toggle_radio_fav
    data       = request.json
    station_id = data.get("station_id")
    favs       = toggle_radio_fav(employee_id, station_id)
    return jsonify({"ok": True, "favs": favs})

@app.route('/api/tablet/meetings', methods=['GET'])
def api_tablet_meetings():
    from tablet_data import get_meetings
    room = request.args.get("room")
    return jsonify({"meetings": get_meetings(room)})

@app.route('/api/tablet/meetings/book', methods=['POST'])
def api_tablet_meetings_book():
    from tablet_data import book_meeting
    from logger import log
    data       = request.json
    meeting_id = book_meeting(data)
    log("Tablet - Meeting", data.get("room"), f"{data.get('title')} um {data.get('time')}")
    return jsonify({"ok": True, "id": meeting_id})

@app.route('/api/tablet/meetings/cancel', methods=['POST'])
def api_tablet_meetings_cancel():
    from tablet_data import cancel_meeting
    cancel_meeting(request.json.get("id"))
    return jsonify({"ok": True})

@app.route('/api/tablet/canteen', methods=['GET'])
def api_tablet_canteen():
    from tablet_data import get_canteen_menu, get_canteen_orders
    return jsonify({"menu": get_canteen_menu(), "orders": get_canteen_orders()})

@app.route('/api/tablet/canteen/order', methods=['POST'])
def api_tablet_canteen_order():
    from tablet_data import place_canteen_order
    from logger import log
    data  = request.json
    order = place_canteen_order(data.get("employee_id"), data.get("name"), data.get("items", []))
    log("Tablet - Kantine", detail=f"{data.get('name')} | {order['total']:.2f}€")
    return jsonify({"ok": True, "order": order})

HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BMS Wartung</title>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@200;300;400&family=Cormorant+Garamond:wght@300;400&display=swap" rel="stylesheet">
<style>
:root{--cream:#F4EFE6;--gold:#B8962E;--gl:rgba(184,150,46,0.15);--text:#2A1F0A;--ts:#7A6840;--tf:#B0A080;--border:rgba(184,150,46,0.25);--warn:#C85050;--wl:rgba(200,80,80,0.1);}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Jost',sans-serif;background:var(--cream);color:var(--text);min-height:100vh;}
header{padding:18px 36px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;background:rgba(244,239,230,0.96);backdrop-filter:blur(8px);z-index:100;}
.htitle{font-family:'Cormorant Garamond',serif;font-size:21px;font-weight:300;}
.hright{display:flex;align-items:center;gap:12px;}
.htime{font-size:14px;font-weight:300;color:var(--ts);font-family:'Cormorant Garamond',serif;}
.hbadge{font-size:9px;letter-spacing:0.14em;text-transform:uppercase;padding:3px 11px;border-radius:11px;border:1px solid var(--border);color:var(--tf);}
.hbadge.on{border-color:rgba(80,160,80,0.4);color:#508050;background:rgba(80,160,80,0.08);}
.hbadge.em{border-color:rgba(200,80,80,0.5);color:var(--warn);background:var(--wl);}
.hbadge.pa{border-color:rgba(184,150,46,0.5);color:var(--gold);background:var(--gl);}
nav{display:flex;border-bottom:1px solid var(--border);padding:0 36px;background:rgba(244,239,230,0.96);position:sticky;top:57px;z-index:99;overflow-x:auto;}
.tab{padding:11px 18px;font-size:10px;font-weight:300;letter-spacing:0.14em;text-transform:uppercase;color:var(--tf);cursor:pointer;border-bottom:2px solid transparent;transition:all 0.2s;white-space:nowrap;}
.tab.active{color:var(--gold);border-bottom-color:var(--gold);}
.tab:hover{color:var(--ts);}
main{padding:26px 36px;max-width:1400px;}
.sec{display:none;}.sec.active{display:block;}
.card{background:rgba(255,252,245,0.7);border:1px solid var(--border);border-radius:13px;padding:20px;margin-bottom:16px;}
.ctitle{font-family:'Cormorant Garamond',serif;font-size:17px;font-weight:300;margin-bottom:13px;padding-bottom:9px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
@media(max-width:900px){.g2{grid-template-columns:1fr;}}
table{width:100%;border-collapse:collapse;font-size:12px;}
th{text-align:left;padding:8px 10px;font-size:9px;font-weight:300;letter-spacing:0.17em;text-transform:uppercase;color:var(--tf);border-bottom:1px solid var(--border);}
td{padding:9px 10px;border-bottom:1px solid rgba(184,150,46,0.08);vertical-align:middle;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:rgba(184,150,46,0.03);}
.b{display:inline-block;padding:2px 9px;border-radius:9px;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;}
.ba{background:var(--gl);color:var(--gold);border:1px solid var(--border);}
.bm{background:var(--wl);color:var(--warn);border:1px solid rgba(200,80,80,0.3);}
.bok{background:rgba(80,160,80,0.1);color:#508050;border:1px solid rgba(80,160,80,0.3);}
.inp{padding:6px 10px;border:1px solid var(--border);border-radius:7px;background:transparent;font-family:'Jost',sans-serif;font-size:12px;color:var(--text);outline:none;}
.inp:focus{border-color:var(--gold);}
.sm{width:80px;}.md{width:150px;}
.btn{padding:6px 13px;border-radius:7px;border:1px solid var(--border);background:transparent;font-family:'Jost',sans-serif;font-size:11px;letter-spacing:0.07em;color:var(--ts);cursor:pointer;transition:all 0.2s;white-space:nowrap;}
.btn:hover{border-color:var(--gold);color:var(--text);}
.btn.p{background:var(--gl);border-color:var(--gold);color:var(--text);}
.btn.d{border-color:rgba(200,80,80,0.4);color:var(--warn);}
.btn.d:hover{background:var(--wl);}
.row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;}
.env-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px;}
.chip{font-size:11px;font-weight:300;color:var(--ts);padding:4px 12px;border:1px solid var(--border);border-radius:14px;background:rgba(184,150,46,0.05);}
.chip span{color:var(--text);}
.wr td{background:rgba(200,80,80,0.04);}
.ll{font-size:11px;font-weight:300;color:var(--ts);padding:5px 0;border-bottom:1px solid rgba(184,150,46,0.07);font-family:monospace;}
.ll:last-child{border-bottom:none;}
.empty{font-size:12px;color:var(--tf);padding:8px 0;}
#toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:rgba(40,30,10,0.9);color:#F4EFE6;padding:8px 20px;border-radius:16px;font-size:12px;font-weight:300;letter-spacing:0.06em;opacity:0;transition:opacity 0.3s;pointer-events:none;z-index:999;}
#toast.show{opacity:1;}
</style>
</head>
<body>
<header>
  <div class="htitle">BMS &nbsp;<span style="font-size:13px;color:var(--tf);font-family:'Jost',sans-serif;font-weight:200;">Wartung & Support</span></div>
  <div class="hright">
    <div class="htime" id="htime">--:--</div>
    <div class="hbadge" id="hsps">SPS: Simulation</div>
    <div class="hbadge em" id="hem" style="display:none">Notfall</div>
    <div class="hbadge pa" id="hpa" style="display:none">Pausiert</div>
  </div>
</header>
<nav>
  <div class="tab active" onclick="show('overview',this)">Übersicht</div>
  <div class="tab" onclick="show('control',this)">Steuerung</div>
  <div class="tab" onclick="show('diagnostics',this)">Diagnose</div>
  <div class="tab" onclick="show('sps',this)">SPS</div>
  <div class="tab" onclick="show('config',this)">Konfiguration</div>
  <div class="tab" onclick="show('adaptive',this)">Adaptiv</div>
  <div class="tab" onclick="show('attendance',this)">Zeiterfassung</div>
  <div class="tab" onclick="show('log',this)">Log</div>
  <div class="tab" onclick="show('system',this)">System</div>
</nav>
<main>
<div class="sec active" id="tab-overview">
  <div class="env-bar" id="envbar"></div>
  <div class="card">
    <div class="ctitle">Raumstatus</div>
    <table><thead><tr>
      <th>Raum</th><th>CO₂</th><th>Temp</th><th>Licht</th>
      <th>Lüftung</th><th>Heizung</th><th>Kühlung</th><th>Jalousie</th><th>Personen</th><th>Bestätigt</th>
    </tr></thead><tbody id="rtable"></tbody></table>
  </div>
</div>
<div class="sec" id="tab-control">
  <div class="card">
    <div class="ctitle">Manuelle Steuerung
      <button class="btn d" onclick="autoAll()">Alle auf Automatik</button>
    </div>
    <table><thead><tr>
      <th>Raum</th><th>Aktuator</th><th>Wert</th><th>Modus</th><th>Aktion</th>
    </tr></thead><tbody id="ctable"></tbody></table>
  </div>
</div>
<div class="sec" id="tab-diagnostics">
  <div class="card"><div class="ctitle">Aktive Warnungen</div><div id="dwarnings"></div></div>
  <div class="card">
    <div class="ctitle">Aktuator-Detail</div>
    <table><thead><tr><th>Raum</th><th>Aktuator</th><th>Wert</th><th>Modus</th><th>Status</th></tr></thead><tbody id="dactuators"></tbody></table>
  </div>
</div>
<div class="sec" id="tab-sps">
  <div class="g2">
    <div class="card">
      <div class="ctitle">Verbindungsstatus</div>
      <div id="sps-disp" style="margin-bottom:14px;"></div>
      <button class="btn p" onclick="spsReconnect()">Verbindung neu aufbauen</button>
    </div>
    <div class="card">
      <div class="ctitle">Konfiguration</div>
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div><div style="font-size:10px;color:var(--tf);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:4px;">AMS Net ID</div><input class="inp md" id="sps-ams" placeholder="192.168.1.5.1.1"></div>
        <div><div style="font-size:10px;color:var(--tf);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:4px;">Port</div><input class="inp sm" id="sps-port" placeholder="851"></div>
        <button class="btn p" onclick="saveSps()" style="align-self:flex-start;">Speichern</button>
      </div>
    </div>
  </div>
</div>
<div class="sec" id="tab-config">
  <div class="g2">
    <div class="card"><div class="ctitle">Solltemperaturen</div><div id="spform"></div></div>
    <div class="card"><div class="ctitle">Raumzuordnung</div><div id="asform"></div></div>
  </div>
  <div class="card">
    <div class="ctitle">Räume verwalten</div>
    <div style="margin-bottom:16px;">
      <div style="font-size:11px;color:var(--tf);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px;">Neuen Raum anlegen</div>
      <div class="row">
        <input class="inp md" id="new-room-name" placeholder="Raumname">
        <input class="inp sm" id="new-room-sp" type="number" placeholder="Solltemp" value="21" step="0.5">
        <span style="font-size:11px;color:var(--tf);">°C</span>
        <select class="inp sm" id="new-room-orient">
          <option value="0">Nord (0°)</option><option value="90">Ost (90°)</option>
          <option value="180" selected>Süd (180°)</option><option value="270">West (270°)</option>
        </select>
        <button class="btn p" onclick="addRoom()">Anlegen</button>
      </div>
    </div>
    <div>
      <div style="font-size:11px;color:var(--tf);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px;">Raum löschen</div>
      <div class="row">
        <select class="inp md" id="del-room-sel"></select>
        <button class="btn d" onclick="delRoom()">Löschen</button>
      </div>
      <div style="font-size:10px;color:var(--tf);margin-top:6px;">Standardräume können nicht gelöscht werden.</div>
    </div>
  </div>
</div>
<div class="sec" id="tab-adaptive">
  <div class="card">
    <div class="ctitle">Gelernte Muster
      <div class="row">
        <span style="font-size:11px;color:var(--tf);">Mindestmessungen:</span>
        <input class="inp sm" id="msinp" value="20">
        <button class="btn" onclick="saveMS()">Setzen</button>
      </div>
    </div>
    <div id="adcontent"></div>
  </div>
</div>
<div class="sec" id="tab-attendance">
  <div class="g2">
    <div class="card"><div class="ctitle">Aktuell anwesend</div><div id="atpresent"></div></div>
    <div class="card">
      <div class="ctitle">Tagesbericht <a href="/api/log/export" class="btn" style="text-decoration:none;">CSV Export</a></div>
      <div id="atsummary"></div>
    </div>
  </div>
</div>
<div class="sec" id="tab-log">
  <div class="card">
    <div class="ctitle">Systemlog
      <div class="row">
        <input class="inp md" id="lfilt" placeholder="Filter..." oninput="filterLog()">
        <select class="inp sm" id="ltype" onchange="filterLog()">
          <option value="">Alle</option><option value="manuell">Manuell</option>
          <option value="adaptiv">Adaptiv</option><option value="presence">Presence</option>
          <option value="sps">SPS</option><option value="system">System</option>
        </select>
        <button class="btn" onclick="loadLog()">Neu laden</button>
        <a href="/api/log/export" class="btn" style="text-decoration:none;">CSV</a>
      </div>
    </div>
    <div id="lcontent"></div>
  </div>
</div>
<div class="sec" id="tab-system">
  <div class="g2">
    <div class="card">
      <div class="ctitle">Simulation</div>
      <div style="display:flex;flex-direction:column;gap:12px;">
        <button class="btn p" id="btnpause" onclick="togglePause()">Simulation pausieren</button>
        <div style="margin-top:6px;">
          <div style="font-size:10px;color:var(--tf);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:8px;">Zeit manuell setzen</div>
          <div class="row">
            <input class="inp sm" id="seth" placeholder="Std" type="number" min="0" max="23">
            <input class="inp sm" id="setm" placeholder="Min" type="number" min="0" max="59">
            <button class="btn" onclick="setTime()">Setzen</button>
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="ctitle">Notfallmodus</div>
      <p style="font-size:12px;color:var(--ts);line-height:1.7;margin-bottom:14px;">Maximale Lüftung, Heizung und Kühlung aus, alle Jalousien offen.</p>
      <button class="btn d" id="btnem" onclick="toggleEmergency()">Notfallmodus aktivieren</button>
    </div>
  </div>
</div>
</main>
<div id="toast"></div>
<script>
let allLog=[];
function show(name,el){document.querySelectorAll('.sec').forEach(s=>s.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById('tab-'+name).classList.add('active');if(el) el.classList.add('active');if(name==='log') loadLog();if(name==='attendance') loadAttendance();if(name==='adaptive') loadAdaptive();if(name==='diagnostics') loadDiag();if(name==='sps') loadSps();if(name==='config') loadConfig();}
function toast(msg,dur=2500){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),dur);}
async function loadOverview(){const r=await fetch('/api/state');const d=await r.json();document.getElementById('htime').textContent=String(d.hour).padStart(2,'0')+':'+String(d.minute).padStart(2,'0');const se=document.getElementById('hsps');se.textContent=d.sps_connected?'SPS: Verbunden':'SPS: Simulation';se.className='hbadge'+(d.sps_connected?' on':'');document.getElementById('hem').style.display=d.emergency?'block':'none';document.getElementById('hpa').style.display=d.sim_paused?'block':'none';document.getElementById('envbar').innerHTML=`<div class="chip">Sonne <span>${Math.round(d.sun_position)}°</span></div><div class="chip">Außenlicht <span>${Math.round(d.outside_light)}</span></div><div class="chip">Strahlung <span>${Math.round(d.direct_radiation)}</span></div><div class="chip">Wolken <span>${(d.cloud_cover*100).toFixed(0)}%</span></div>`;const rt=document.getElementById('rtable');if(rt){rt.innerHTML='';for(const[room,s] of Object.entries(d.building_state)){const a=d.actuator_state[room];rt.innerHTML+=`<tr><td><strong>${room}</strong></td><td>${Math.round(s.co2)}</td><td>${s.temp.toFixed(1)}°C</td><td>${s.light}%</td><td>${a.vent.value}% <span class="b ${a.vent.mode==='manual'?'bm':'ba'}">${a.vent.mode}</span></td><td>${a.heat.value}% <span class="b ${a.heat.mode==='manual'?'bm':'ba'}">${a.heat.mode}</span></td><td>${a.cool.value}% <span class="b ${a.cool.mode==='manual'?'bm':'ba'}">${a.cool.mode}</span></td><td>${a.blind.value}% <span class="b ${a.blind.mode==='manual'?'bm':'ba'}">${a.blind.mode}</span></td><td>${s.occupancy}</td><td>${s.confirmed||'-'}</td></tr>`;}}const ct=document.getElementById('ctable');if(ct){ct.innerHTML='';for(const[room,acts] of Object.entries(d.actuator_state)){for(const[act,info] of Object.entries(acts)){ct.innerHTML+=`<tr><td>${room}</td><td>${act}</td><td>${info.value}%</td><td><span class="b ${info.mode==='manual'?'bm':'ba'}">${info.mode}</span></td><td><div class="row"><input class="inp sm" type="number" id="i-${room}-${act}" value="${info.value}" min="0" max="100"><button class="btn p" onclick="setM('${room}','${act}')">Setzen</button><button class="btn d" onclick="setA('${room}','${act}')">Auto</button></div></td></tr>`;}}}const da=document.getElementById('dactuators');if(da){da.innerHTML='';for(const[room,acts] of Object.entries(d.actuator_state)){for(const[act,info] of Object.entries(acts)){da.innerHTML+=`<tr class="${info.mode==='manual'?'wr':''}"><td>${room}</td><td>${act}</td><td>${info.value}%</td><td><span class="b ${info.mode==='manual'?'bm':'ba'}">${info.mode}</span></td><td><span class="b ${info.mode==='manual'?'bm':'bok'}">${info.mode==='manual'?'Manuell':'OK'}</span></td></tr>`;}}}
}
async function setM(room,act){const v=document.getElementById(`i-${room}-${act}`)?.value;await fetch('/api/manual',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room,actuator:act,value:parseInt(v)})});toast(`${room} / ${act} auf ${v}%`);loadOverview();}
async function setA(room,act){await fetch('/api/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room,actuator:act})});toast(`${room} / ${act} auf Automatik`);loadOverview();}
async function autoAll(){await fetch('/api/auto_all',{method:'POST'});toast('Alle auf Automatik');loadOverview();}
async function loadDiag(){const r=await fetch('/api/diagnostics');const d=await r.json();const el=document.getElementById('dwarnings');if(!el)return;el.innerHTML=d.warnings.length===0?'<div class="empty">Keine Warnungen.</div>':`<table><thead><tr><th>Raum</th><th>Typ</th><th>Wert</th></tr></thead><tbody>${d.warnings.map(w=>`<tr class="wr"><td>${w.room}</td><td>${w.type}</td><td>${w.value}</td></tr>`).join('')}</tbody></table>`;loadOverview();}
async function loadSps(){const r=await fetch('/api/sps/status');const d=await r.json();document.getElementById('sps-disp').innerHTML=`<div class="row" style="margin-bottom:8px;"><span class="b ${d.connected?'bok':'bm'}">${d.connected?'Verbunden':'Getrennt'}</span><span style="font-size:12px;color:var(--ts);">${d.ams_net_id} : ${d.port}</span></div>`;document.getElementById('sps-ams').value=d.ams_net_id;document.getElementById('sps-port').value=d.port;}
async function spsReconnect(){await fetch('/api/sps/reconnect',{method:'POST'});toast('Verbindungsversuch gestartet');setTimeout(loadSps,1500);}
async function saveSps(){const ams=document.getElementById('sps-ams').value;const port=document.getElementById('sps-port').value;await fetch('/api/sps/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ams_net_id:ams,port:parseInt(port)})});toast('SPS Konfiguration gespeichert');}
async function loadConfig(){const r=await fetch('/api/state');const d=await r.json();const rr=await fetch('/api/config/rooms');const rd=await rr.json();const rooms=Object.keys(d.building_state);const sp=document.getElementById('spform');if(sp) sp.innerHTML=rooms.map(r=>`<div class="row" style="margin-bottom:10px;"><span style="width:120px;font-size:12px;">${r}</span><input class="inp sm" id="sp-${r}" type="number" step="0.5" value="21"><span style="font-size:11px;color:var(--tf);">°C</span></div>`).join('')+`<button class="btn p" onclick="saveSP()" style="margin-top:6px;">Speichern</button>`;const as=document.getElementById('asform');if(as) as.innerHTML=Object.entries(rd.rooms).map(([room,a])=>`<div style="margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--border);"><div style="font-size:12px;font-weight:400;margin-bottom:6px;">${room}</div><div class="row"><input class="inp sm" id="ai-${room}" placeholder="ID" value="${a.employee_id||''}"><input class="inp md" id="an-${room}" placeholder="Name" value="${a.name||''}"><button class="btn" onclick="saveAS('${room}')">Zuweisen</button></div></div>`).join('');const delSel=document.getElementById('del-room-sel');if(delSel){const custom=rooms.filter(r=>!['Buero','Meetingraum','Serverraum'].includes(r));delSel.innerHTML=custom.length===0?'<option value="">Keine eigenen Räume</option>':custom.map(r=>`<option value="${r}">${r}</option>`).join('');}
}
async function saveSP(){const data={};document.querySelectorAll('[id^="sp-"]').forEach(i=>{data[i.id.replace('sp-','')]=parseFloat(i.value);});await fetch('/api/config/setpoints',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});toast('Sollwerte gespeichert');}
async function saveAS(room){const id=document.getElementById(`ai-${room}`).value;const name=document.getElementById(`an-${room}`).value;await fetch('/api/config/assign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room,employee_id:id,name})});toast(`${room} zugewiesen`);}
async function addRoom(){const name=document.getElementById('new-room-name').value.trim();const sp=document.getElementById('new-room-sp').value;const orient=document.getElementById('new-room-orient').value;if(!name){toast('Bitte Raumname eingeben');return;}const r=await fetch('/api/config/rooms/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room:name,setpoint:parseFloat(sp),orientation:parseInt(orient)})});const d=await r.json();if(d.ok){toast(`Raum "${name}" angelegt`);loadConfig();}else toast(`Fehler: ${d.error}`);}
async function delRoom(){const room=document.getElementById('del-room-sel').value;if(!room){toast('Kein Raum ausgewählt');return;}const r=await fetch('/api/config/rooms/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room})});const d=await r.json();if(d.ok){toast(`Raum "${room}" gelöscht`);loadConfig();}else toast(`Fehler: ${d.error}`);}
async function loadAdaptive(){const r=await fetch('/api/adaptive');const d=await r.json();const el=document.getElementById('adcontent');if(!el)return;if(d.patterns.length===0){el.innerHTML='<div class="empty">Noch nicht genug Daten.</div>';return;}el.innerHTML=`<table><thead><tr><th>Mitarbeiter</th><th>Typ</th><th>Tag</th><th>Uhrzeit</th><th>Wahrscheinlichkeit</th><th>Messungen</th><th>Aktion</th></tr></thead><tbody>${d.patterns.map(p=>`<tr><td>${p.name} (${p.employee_id})</td><td>${p.type}</td><td>${p.day}</td><td>${String(p.hour).padStart(2,'0')}:00</td><td>${Math.round(p.probability*100)}%</td><td>${p.samples}</td><td><button class="btn d" onclick="delPat('${p.employee_id}',${p.hour})">Löschen</button></td></tr>`).join('')}</tbody></table><div class="row" style="margin-top:12px;"><input class="inp md" id="delempid" placeholder="Mitarbeiter-ID"><button class="btn d" onclick="delAll()">Alle Muster löschen</button></div>`;}
async function delPat(emp,hour){await fetch('/api/adaptive/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({employee_id:emp,key:`${emp}_${hour}`})});toast('Muster gelöscht');loadAdaptive();}
async function delAll(){const id=document.getElementById('delempid').value;if(!id){toast('Bitte ID eingeben');return;}await fetch('/api/adaptive/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({employee_id:id,all:true})});toast(`Alle Muster von ${id} gelöscht`);loadAdaptive();}
async function saveMS(){const v=parseInt(document.getElementById('msinp').value);await fetch('/api/adaptive/min_samples',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({min_samples:v})});toast(`Mindestmessungen: ${v}`);}
async function loadAttendance(){const r=await fetch('/api/attendance');const d=await r.json();const pe=document.getElementById('atpresent');const se=document.getElementById('atsummary');if(pe) pe.innerHTML=d.present.length===0?'<div class="empty">Niemand eingecheckt.</div>':d.present.map(p=>`<div style="padding:7px 0;border-bottom:1px solid var(--border);font-size:12px;"><strong>${p.name}</strong> · seit ${p.check_in}</div>`).join('');if(se) se.innerHTML=d.summary.length===0?'<div class="empty">Keine Einträge heute.</div>':d.summary.map(s=>`<div style="padding:7px 0;border-bottom:1px solid var(--border);font-size:12px;"><strong>${s.name}</strong><br><span style="color:var(--tf)">${s.check_in} → ${s.check_out}</span> · ${s.duration}</div>`).join('');}
async function loadLog(){const f=document.getElementById('lfilt')?.value||'';const r=await fetch(`/api/log?filter=${encodeURIComponent(f)}`);const d=await r.json();allLog=d.lines;const t=document.getElementById('ltype')?.value||'';const lines=t?allLog.filter(l=>l.toLowerCase().includes(t)):allLog;const el=document.getElementById('lcontent');if(el) el.innerHTML=lines.length===0?'<div class="empty">Keine Einträge.</div>':lines.map(l=>`<div class="ll">${l}</div>`).join('');}
function filterLog(){loadLog();}
async function togglePause(){const r=await fetch('/api/system/pause',{method:'POST'});const d=await r.json();const b=document.getElementById('btnpause');b.textContent=d.paused?'Simulation fortsetzen':'Simulation pausieren';b.className=d.paused?'btn p':'btn';toast(d.paused?'Simulation pausiert':'Simulation läuft');}
async function toggleEmergency(){const r=await fetch('/api/system/emergency',{method:'POST'});const d=await r.json();const b=document.getElementById('btnem');b.textContent=d.emergency?'Notfallmodus deaktivieren':'Notfallmodus aktivieren';b.className=d.emergency?'btn d p':'btn d';toast(d.emergency?'NOTFALLMODUS AKTIV':'Notfallmodus deaktiviert',3000);}
async function setTime(){const h=document.getElementById('seth').value;const m=document.getElementById('setm').value;await fetch('/api/system/settime',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hour:parseInt(h),minute:parseInt(m)})});toast(`Zeit gesetzt: ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`);}
loadOverview();
setInterval(loadOverview,3000);
</script>
</body>
</html>
"""

TABLET_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>BMS Tablet</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Segoe UI',sans-serif;background:#1a1a2e;color:#eee;height:100vh;overflow:hidden;position:relative;}

.pages-wrapper{position:relative;width:100vw;height:100vh;overflow:hidden;}
.page{
  position:absolute;width:100vw;height:100vh;
  display:flex;flex-direction:column;overflow:hidden;
  transition:transform 0.4s cubic-bezier(0.4,0,0.2,1);
}

.co2-alert{position:fixed;top:16px;right:16px;background:rgba(200,80,80,0.2);border:1px solid rgba(200,80,80,0.5);color:#ff6b6b;padding:6px 14px;border-radius:20px;font-size:12px;display:none;animation:pulse 1.5s infinite;z-index:300;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.5;}}

/* MITTE */
#page-center{align-items:center;justify-content:center;gap:20px;padding:24px;transform:translate(0,0);}
/* LINKS – kommt von links, Inhalt oben */
#page-left{padding:24px 20px;gap:12px;overflow-y:auto;transform:translate(-100vw,0);}
/* RECHTS – kommt von rechts, Inhalt oben */
#page-right{padding:24px 20px;gap:12px;overflow-y:auto;transform:translate(100vw,0);}
/* OBEN – kommt von oben, Inhalt oben */
#page-quick{padding:32px 28px;gap:24px;justify-content:flex-start;transform:translate(0,-100vh);}
/* UNTEN – kommt von unten, Inhalt unten */
#page-prefs{padding:28px;gap:18px;overflow-y:auto;justify-content:flex-end;transform:translate(0,100vh);}

.room-name{font-size:13px;text-transform:uppercase;letter-spacing:0.2em;color:rgba(255,255,255,0.4);}
.clock{font-size:64px;font-weight:200;letter-spacing:0.05em;line-height:1;}
.now-playing{font-size:11px;color:rgba(255,255,255,0.4);text-align:center;height:16px;}
.stats-row{display:flex;gap:16px;}
.stat-box{text-align:center;padding:14px 18px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:14px;min-width:85px;}
.stat-val{font-size:26px;font-weight:300;}
.stat-lbl{font-size:9px;text-transform:uppercase;letter-spacing:0.15em;color:rgba(255,255,255,0.4);margin-top:4px;}
.stat-box.warn{border-color:rgba(200,80,80,0.4);}
.stat-box.warn .stat-val{color:#ff6b6b;}
.volume-row{display:flex;align-items:center;gap:12px;width:260px;}
.volume-row label{font-size:11px;color:rgba(255,255,255,0.5);width:70px;}
.volume-row input[type=range]{flex:1;accent-color:#B8962E;}
.volume-val{font-size:11px;color:#B8962E;width:36px;text-align:right;}
.checkin-area{display:flex;flex-direction:column;align-items:center;gap:10px;}
.nfc-btn{padding:14px 32px;background:rgba(184,150,46,0.15);border:1px solid rgba(184,150,46,0.4);border-radius:50px;color:#B8962E;font-size:13px;letter-spacing:0.1em;cursor:pointer;transition:all 0.2s;}
.nfc-btn:hover{background:rgba(184,150,46,0.25);}
.checkout-btn{padding:8px 20px;background:rgba(200,80,80,0.1);border:1px solid rgba(200,80,80,0.3);border-radius:50px;color:#ff6b6b;font-size:11px;cursor:pointer;}
.confirmed-name{font-size:14px;color:rgba(255,255,255,0.7);}

.page-title{font-size:10px;text-transform:uppercase;letter-spacing:0.18em;color:rgba(255,255,255,0.3);margin-bottom:2px;}
.media-btn{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:16px;cursor:pointer;transition:all 0.2s;}
.media-btn:hover{background:rgba(184,150,46,0.15);border-color:rgba(184,150,46,0.4);}
.media-btn-title{font-size:13px;font-weight:500;margin-bottom:4px;}
.media-btn-sub{font-size:11px;color:rgba(255,255,255,0.4);}
.carousel{display:none;flex-direction:column;gap:2px;margin-top:6px;max-height:260px;overflow-y:auto;}
.carousel.show{display:flex;}
.carousel-item{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-radius:10px;cursor:pointer;transition:background 0.2s;}
.carousel-item:hover{background:rgba(255,255,255,0.06);}
.carousel-item.playing{background:rgba(184,150,46,0.12);}
.ci-name{font-size:12px;}
.ci-heart{font-size:14px;cursor:pointer;color:rgba(255,255,255,0.3);}
.ci-heart.fav{color:#ff6b6b;}

.quick-note{font-size:11px;color:rgba(255,255,255,0.3);}
.quick-group{display:flex;flex-direction:column;gap:20px;}
.quick-row{display:flex;align-items:center;gap:16px;}
.quick-row label{font-size:12px;color:rgba(255,255,255,0.6);width:90px;}
.quick-row input[type=range]{flex:1;accent-color:#B8962E;}
.quick-row .qval{font-size:13px;color:#B8962E;width:44px;text-align:right;}

.pref-group{display:flex;flex-direction:column;gap:16px;}
.pref-row{display:flex;align-items:center;gap:16px;}
.pref-row label{font-size:12px;color:rgba(255,255,255,0.5);width:90px;}
.pref-row input[type=range]{flex:1;accent-color:#B8962E;}
.pref-row .pval{font-size:13px;color:#B8962E;width:44px;text-align:right;}
.sec-label{font-size:9px;text-transform:uppercase;letter-spacing:0.15em;color:rgba(255,255,255,0.3);margin-bottom:6px;}
.scene-row{display:flex;gap:10px;flex-wrap:wrap;}
.scene-chip{padding:8px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:20px;font-size:12px;cursor:pointer;transition:all 0.2s;}
.scene-chip:hover{background:rgba(184,150,46,0.1);border-color:rgba(184,150,46,0.3);}
.scene-chip.active{background:rgba(184,150,46,0.25);border-color:rgba(184,150,46,0.6);color:#B8962E;}
.sel{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:8px 12px;color:#eee;font-size:12px;width:100%;outline:none;}
.save-btn{padding:10px 24px;background:rgba(184,150,46,0.15);border:1px solid rgba(184,150,46,0.4);border-radius:20px;color:#B8962E;font-size:12px;cursor:pointer;align-self:flex-start;}
.pref-mode-hint{font-size:11px;color:rgba(184,150,46,0.7);min-height:16px;}

.service-btn{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:14px;padding:16px;cursor:pointer;transition:all 0.2s;}
.service-btn:hover{background:rgba(184,150,46,0.1);border-color:rgba(184,150,46,0.3);}
.service-title{font-size:13px;font-weight:500;margin-bottom:4px;}
.service-sub{font-size:11px;color:rgba(255,255,255,0.4);}
.canteen-list{display:none;flex-direction:column;gap:2px;margin-top:8px;max-height:220px;overflow-y:auto;}
.canteen-list.show{display:flex;}
.cart-box{margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.08);}
.cart-item{display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;}
.cart-foot{display:flex;justify-content:space-between;align-items:center;margin-top:8px;}

.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:400;align-items:center;justify-content:center;}
.modal-overlay.show{display:flex;}
.modal{background:#16213e;border:1px solid rgba(255,255,255,0.1);border-radius:20px;padding:28px;width:360px;max-height:85vh;overflow-y:auto;}
.modal-title{font-size:16px;font-weight:300;margin-bottom:18px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.1);}
.mfield{margin-bottom:12px;}
.mfield label{display:block;font-size:10px;text-transform:uppercase;letter-spacing:0.12em;color:rgba(255,255,255,0.4);margin-bottom:5px;}
.mfield input,.mfield select{width:100%;padding:8px 12px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#eee;font-size:13px;outline:none;}
.mfield input:focus,.mfield select:focus{border-color:rgba(184,150,46,0.5);}
.mbtns{display:flex;gap:10px;margin-top:18px;}
.mbtn{flex:1;padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:transparent;color:rgba(255,255,255,0.6);cursor:pointer;font-size:12px;}
.mbtn.primary{background:rgba(184,150,46,0.2);border-color:rgba(184,150,46,0.5);color:#B8962E;}

.toast{position:fixed;bottom:30px;left:50%;transform:translateX(-50%);background:rgba(40,30,10,0.95);color:#F4EFE6;padding:8px 20px;border-radius:16px;font-size:12px;opacity:0;transition:opacity 0.3s;pointer-events:none;z-index:500;}
.toast.show{opacity:1;}
#audio-player{display:none;}
</style>
</head>
<body>
<audio id="audio-player" crossorigin="anonymous"></audio>
<div class="co2-alert" id="co2-alert">⚠ CO₂ kritisch – Fenster öffnen!</div>

<div class="pages-wrapper">

  <!-- MITTE -->
  <div class="page" id="page-center">
    <div class="room-name">Büro</div>
    <div class="clock" id="clock">--:--</div>
    <div class="now-playing" id="now-playing"></div>
    <div class="stats-row">
      <div class="stat-box"><div class="stat-val" id="val-temp">--</div><div class="stat-lbl">Temp °C</div></div>
      <div class="stat-box" id="stat-co2"><div class="stat-val" id="val-co2">--</div><div class="stat-lbl">CO₂ ppm</div></div>
      <div class="stat-box"><div class="stat-val" id="val-light">--</div><div class="stat-lbl">Licht %</div></div>
    </div>
    <div class="volume-row">
      <label>Lautstärke</label>
      <input type="range" id="volume" min="0" max="100" value="80" oninput="setVolume(this.value)">
      <span class="volume-val" id="volume-val">80%</span>
    </div>
    <div class="checkin-area">
      <div class="confirmed-name" id="confirmed-name"></div>
      <button class="nfc-btn" id="nfc-btn" onclick="doCheckin()">NFC – Anmelden</button>
      <button class="checkout-btn" id="checkout-btn" style="display:none" onclick="doCheckout()">Abmelden</button>
    </div>
  </div>

  <!-- LINKS: MEDIEN -->
  <div class="page" id="page-left">
    <div class="page-title">Medien & Szenen</div>
    <div class="media-btn" onclick="toggleInlineCarousel('radio')">
      <div class="media-btn-title">📻 Radio / Webradio</div>
      <div class="media-btn-sub" id="radio-sub">Kein Sender aktiv</div>
    </div>
    <div class="carousel" id="carousel-radio"><div id="radio-list"></div></div>
    <div class="media-btn" onclick="showToast('TV/Beamer – Hardware nicht verbunden')">
      <div class="media-btn-title">📺 TV / Beamer</div>
      <div class="media-btn-sub">Gerät auswählen</div>
    </div>
    <div class="media-btn" onclick="toggleInlineCarousel('scene')">
      <div class="media-btn-title">🎭 Szenen</div>
      <div class="media-btn-sub">Stimmung wählen</div>
    </div>
    <div class="carousel" id="carousel-scene"><div id="scene-list-carousel"></div></div>
  </div>

  <!-- RECHTS: SERVICES -->
  <div class="page" id="page-right">
    <div class="page-title">Services</div>
    <div class="service-btn" onclick="toggleCanteen()">
      <div class="service-title">🍽 Kantine</div>
      <div class="service-sub">Essen & Getränke bestellen</div>
    </div>
    <div class="canteen-list" id="canteen-list-wrap">
      <div id="canteen-items"></div>
      <div class="cart-box">
        <div class="sec-label">Warenkorb</div>
        <div id="cart-list"></div>
        <div class="cart-foot">
          <span style="font-size:13px;color:#B8962E;" id="cart-total">0.00 €</span>
          <button class="save-btn" onclick="placeOrder()">Bestellen</button>
        </div>
      </div>
    </div>
    <div class="service-btn" onclick="openMeetingModal()">
      <div class="service-title">📅 Meetingraum buchen</div>
      <div class="service-sub">Datum, Uhrzeit, Art auswählen</div>
    </div>
  </div>

  <!-- OBEN: SCHNELLEINSTELLUNGEN -->
  <div class="page" id="page-quick">
    <div class="page-title">Schnelleinstellungen</div>
    <div class="quick-note">Temporär – bis zum Abmelden</div>
    <div class="quick-group">
      <div class="quick-row"><label>Temperatur</label><input type="range" id="q-temp" min="16" max="28" step="0.5" value="21" oninput="quickUpdate('temp',this.value)"><span class="qval" id="q-temp-val">21°</span></div>
      <div class="quick-row"><label>Lüftung</label><input type="range" id="q-vent" min="0" max="100" step="10" value="0" oninput="quickUpdate('vent',this.value)"><span class="qval" id="q-vent-val">0%</span></div>
      <div class="quick-row"><label>Licht</label><input type="range" id="q-light" min="0" max="100" step="10" value="100" oninput="quickUpdate('light',this.value)"><span class="qval" id="q-light-val">100%</span></div>
      <div class="quick-row"><label>Jalousie</label><input type="range" id="q-blind" min="0" max="100" step="10" value="0" oninput="quickUpdate('blind',this.value)"><span class="qval" id="q-blind-val">0%</span></div>
    </div>
  </div>

  <!-- UNTEN: PERSÖNLICHE EINSTELLUNGEN -->
  <div class="page" id="page-prefs">
    <div class="pref-group">
      <div class="page-title">Persönliche Einstellungen</div>
      <div class="pref-mode-hint" id="pref-mode-hint">Normalbetrieb</div>
      <div class="pref-row"><label>Temperatur</label><input type="range" id="p-temp" min="16" max="28" step="0.5" value="21" oninput="document.getElementById('p-temp-val').textContent=this.value+'°'"><span class="pval" id="p-temp-val">21°</span></div>
      <div class="pref-row"><label>Lüftung</label><input type="range" id="p-vent" min="0" max="100" step="10" value="0" oninput="document.getElementById('p-vent-val').textContent=this.value+'%'"><span class="pval" id="p-vent-val">0%</span></div>
      <div class="pref-row"><label>Licht</label><input type="range" id="p-light" min="0" max="100" step="10" value="100" oninput="document.getElementById('p-light-val').textContent=this.value+'%'"><span class="pval" id="p-light-val">100%</span></div>
      <div class="pref-row"><label>Jalousie</label><input type="range" id="p-blind" min="0" max="100" step="10" value="0" oninput="document.getElementById('p-blind-val').textContent=this.value+'%'"><span class="pval" id="p-blind-val">0%</span></div>
      <div>
        <div class="sec-label">Szene anpassen</div>
        <div class="scene-row" id="scene-chips"></div>
      </div>
      <div>
        <div class="sec-label">Beim Einloggen abspielen</div>
        <select class="sel" id="p-auto-media">
          <option value="">Kein Medium</option>
          <option value="radiobob">Radio Bob – Best of Rock</option>
          <option value="wdr2">WDR 2</option>
        </select>
      </div>
      <button class="save-btn" onclick="savePreferences()">Speichern</button>
    </div>
  </div>

</div>

<!-- MEETING MODAL -->
<div class="modal-overlay" id="meeting-modal">
  <div class="modal">
    <div class="modal-title">Meetingraum buchen</div>
    <div class="mfield"><label>Titel</label><input id="m-title" placeholder="Besprechung..."></div>
    <div class="mfield"><label>Datum</label><input id="m-date" type="date"></div>
    <div class="mfield"><label>Uhrzeit</label><input id="m-time" type="time"></div>
    <div class="mfield"><label>Dauer</label>
      <select id="m-duration">
        <option value="30">30 Minuten</option><option value="60" selected>1 Stunde</option>
        <option value="90">90 Minuten</option><option value="120">2 Stunden</option>
      </select>
    </div>
    <div class="mfield"><label>Art</label>
      <select id="m-type">
        <option value="normal">Normal</option><option value="presentation">Präsentation</option>
        <option value="private">Ungestört</option>
      </select>
    </div>
    <div class="mfield"><label>Sichtbarkeit</label>
      <select id="m-visibility"><option value="public">Öffentlich</option><option value="private">Privat</option></select>
    </div>
    <div class="mbtns">
      <button class="mbtn" onclick="closeMeetingModal()">Abbrechen</button>
      <button class="mbtn primary" onclick="bookMeeting()">Buchen</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const ROOM='Buero';
let currentEmployee=null,currentProfile=null,cart={},playingStation=null,currentPage='center',activeInline=null,activeSceneId=null;

const PAGE_POS={
  center:'translate(0,0)',
  left:  'translate(-100vw,0)',
  right: 'translate(100vw,0)',
  quick: 'translate(0,-100vh)',
  prefs: 'translate(0,100vh)',
};

function goTo(target){
  Object.keys(PAGE_POS).forEach(id=>{
    document.getElementById('page-'+id).style.transform=PAGE_POS[id];
  });
  document.getElementById('page-'+target).style.transform='translate(0,0)';
  currentPage=target;
}

let startX=0,startY=0,isDragging=false;

function handleSwipe(dx,dy){
  if(Math.abs(dx)<50&&Math.abs(dy)<50) return;
  if(currentPage!=='center'){goTo('center');return;}
  if(Math.abs(dx)>Math.abs(dy)){
    if(dx>0) goTo('left');
    else     goTo('right');
  } else {
    if(dy>0) goTo('quick');
    else     goTo('prefs');
  }
}

document.addEventListener('touchstart',e=>{startX=e.touches[0].clientX;startY=e.touches[0].clientY;},{passive:true});
document.addEventListener('touchend',e=>{handleSwipe(e.changedTouches[0].clientX-startX,e.changedTouches[0].clientY-startY);},{passive:true});
document.addEventListener('mousedown',e=>{startX=e.clientX;startY=e.clientY;isDragging=true;});
document.addEventListener('mouseup',e=>{if(!isDragging)return;isDragging=false;handleSwipe(e.clientX-startX,e.clientY-startY);});
document.addEventListener('mouseleave',()=>{isDragging=false;});

function showToast(msg,dur=2500){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),dur);}

async function loadState(){
  const r=await fetch(`/api/tablet/state/${ROOM}`);
  const d=await r.json();
  document.getElementById('clock').textContent=String(d.hour).padStart(2,'0')+':'+String(d.minute).padStart(2,'0');
  document.getElementById('val-temp').textContent=d.temp+'°';
  document.getElementById('val-co2').textContent=d.co2;
  document.getElementById('val-light').textContent=d.light+'%';
  const co2Warn=document.getElementById('co2-alert');
  const co2Box=document.getElementById('stat-co2');
  if(d.co2>1400){co2Warn.style.display='block';co2Box.classList.add('warn');}
  else{co2Warn.style.display='none';co2Box.classList.remove('warn');}
  if(d.confirmed){
    document.getElementById('confirmed-name').textContent='Angemeldet: '+d.confirmed.name;
    document.getElementById('nfc-btn').style.display='none';
    document.getElementById('checkout-btn').style.display='block';
  } else {
    document.getElementById('confirmed-name').textContent='';
    document.getElementById('nfc-btn').style.display='block';
    document.getElementById('checkout-btn').style.display='none';
  }
  if(!currentEmployee&&d.actuators){
    const a=d.actuators;
    document.getElementById('q-vent').value=a.vent.value;document.getElementById('q-vent-val').textContent=a.vent.value+'%';
    document.getElementById('q-blind').value=a.blind.value;document.getElementById('q-blind-val').textContent=a.blind.value+'%';
    document.getElementById('q-light').value=d.light;document.getElementById('q-light-val').textContent=d.light+'%';
    document.getElementById('q-temp').value=d.temp;document.getElementById('q-temp-val').textContent=d.temp+'°';
  }
}

async function doCheckin(){
  const r=await fetch(`/api/tablet/checkin/${ROOM}`,{method:'POST'});
  const d=await r.json();
  if(!d.ok){showToast(d.error||'Fehler');return;}
  currentProfile=d.profile;currentEmployee=currentProfile.employee_id;
  applyProfile(currentProfile);
  showToast('Willkommen!');
  loadState();loadScenes();
}

async function doCheckout(){
  await fetch(`/api/tablet/checkout/${ROOM}`,{method:'POST'});
  stopRadio();currentEmployee=null;currentProfile=null;activeSceneId=null;
  showToast('Abgemeldet');loadState();
}

function applyProfile(p){
  // Schieberegler auf Normalbetriebs-Werte
  setPrefsSliders(p.temp, p.vent, p.light, p.blind);
  if(p.auto_media_id) document.getElementById('p-auto-media').value=p.auto_media_id;
  document.getElementById('q-temp').value=p.temp;document.getElementById('q-temp-val').textContent=p.temp+'°';
  document.getElementById('pref-mode-hint').textContent='Normalbetrieb';
  activeSceneId=null;
  // Auto-Media: kurze Verzögerung damit Browser bereit ist
  if(p.auto_media&&p.auto_media_id){
    setTimeout(()=>playStationById(p.auto_media_id), 800);
  }
}

function setPrefsSliders(temp,vent,light,blind){
  document.getElementById('p-temp').value=temp;document.getElementById('p-temp-val').textContent=temp+'°';
  document.getElementById('p-vent').value=vent;document.getElementById('p-vent-val').textContent=vent+'%';
  document.getElementById('p-light').value=light;document.getElementById('p-light-val').textContent=light+'%';
  document.getElementById('p-blind').value=blind;document.getElementById('p-blind-val').textContent=blind+'%';
}

function setVolume(val){
  document.getElementById('volume-val').textContent=val+'%';
  document.getElementById('audio-player').volume=val/100;
}

async function quickUpdate(key,value){
  document.getElementById(`q-${key}-val`).textContent=key==='temp'?value+'°':value+'%';
  const body={};
  if(key==='temp'){body['heat']=parseFloat(value)>21?70:0;}else{body[key]=parseInt(value);}
  await fetch(`/api/tablet/quick/${ROOM}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
}

async function loadRadio(){
  const empId=currentEmployee||'default';
  const r=await fetch(`/api/tablet/radio/${empId}`);const d=await r.json();
  document.getElementById('radio-list').innerHTML=d.stations.map(s=>`
    <div class="carousel-item ${playingStation===s.id?'playing':''}" onclick="playStation('${s.id}','${s.url}','${s.name}')">
      <span class="ci-name">${s.name}</span>
      <span class="ci-heart ${s.favorite?'fav':''}" onclick="event.stopPropagation();toggleFav('${s.id}',this)">♥</span>
    </div>`).join('');
}

// Sender nach ID suchen und abspielen (für Auto-Play nach Login)
async function playStationById(stationId){
  const empId=currentEmployee||'default';
  const r=await fetch(`/api/tablet/radio/${empId}`);
  const d=await r.json();
  const station=d.stations.find(s=>s.id===stationId);
  if(station) playStation(station.id, station.url, station.name);
}

function playStation(id,url,name){
  const audio=document.getElementById('audio-player');
  if(playingStation===id){
    audio.pause();playingStation=null;
    document.getElementById('now-playing').textContent='';
    document.getElementById('radio-sub').textContent='Kein Sender aktiv';
  } else {
    audio.src=url;
    audio.volume=document.getElementById('volume').value/100;
    const playPromise=audio.play();
    if(playPromise!==undefined){
      playPromise.catch(()=>{
        // Zweiter Versuch nach kurzer Pause
        setTimeout(()=>{
          audio.play().catch(()=>showToast('Stream nicht erreichbar'));
        },1000);
      });
    }
    playingStation=id;
    document.getElementById('now-playing').textContent='▶ '+name;
    document.getElementById('radio-sub').textContent=name;
  }
  loadRadio();
}

function stopRadio(){
  const audio=document.getElementById('audio-player');
  audio.pause();playingStation=null;
  document.getElementById('now-playing').textContent='';
  document.getElementById('radio-sub').textContent='Kein Sender aktiv';
}

async function toggleFav(stationId,el){
  if(!currentEmployee){showToast('Bitte zuerst anmelden');return;}
  el.classList.toggle('fav');
  await fetch(`/api/tablet/radio/${currentEmployee}/fav`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({station_id:stationId})});
}

async function loadScenes(){
  const empId=currentEmployee||'default';
  const r=await fetch(`/api/tablet/scenes/${empId}`);const d=await r.json();
  // Szenen-Chips in persönlichen Einstellungen
  document.getElementById('scene-chips').innerHTML=d.scenes.map(s=>`
    <div class="scene-chip ${activeSceneId===s.id?'active':''}" id="chip-${s.id}" onclick="selectSceneForEdit('${s.id}')">${s.name}</div>`).join('');
  // Szenen-Karussell in Medien-Page
  document.getElementById('scene-list-carousel').innerHTML=d.scenes.map(s=>`
    <div class="carousel-item" onclick="activateScene('${s.id}')">
      <span class="ci-name">${s.name}</span>
      <span style="font-size:10px;color:rgba(255,255,255,0.3);">Licht ${s.light}% · Jalousie ${s.blind}%</span>
    </div>`).join('');
}

// Szene im Medien-Karussell aktivieren (wendet sie auf den Raum an)
async function activateScene(sceneId){
  if(!currentEmployee){showToast('Bitte zuerst anmelden');return;}
  await fetch(`/api/tablet/scenes/${currentEmployee}/activate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_id:sceneId,room:ROOM})});
  showToast('Szene aktiviert');
}

// Szene in persönlichen Einstellungen auswählen zum Bearbeiten
async function selectSceneForEdit(sceneId){
  if(!currentEmployee){showToast('Bitte zuerst anmelden');return;}
  const empId=currentEmployee;
  const r=await fetch(`/api/tablet/scenes/${empId}`);const d=await r.json();
  const scene=d.scenes.find(s=>s.id===sceneId);
  if(!scene) return;
  if(activeSceneId===sceneId){
    // Zweites Tippen: Szene deselektieren, zurück zu Normalbetrieb
    activeSceneId=null;
    setPrefsSliders(currentProfile.temp,currentProfile.vent,currentProfile.light,currentProfile.blind);
    document.getElementById('pref-mode-hint').textContent='Normalbetrieb';
  } else {
    activeSceneId=sceneId;
    setPrefsSliders(scene.temp||scene.light,scene.vent||0,scene.light,scene.blind);
    document.getElementById('pref-mode-hint').textContent='Szene: '+scene.name;
  }
  loadScenes();
}

function toggleInlineCarousel(type){
  if(activeInline===type){document.getElementById('carousel-'+type).classList.remove('show');activeInline=null;return;}
  if(activeInline) document.getElementById('carousel-'+activeInline).classList.remove('show');
  activeInline=type;
  document.getElementById('carousel-'+type).classList.add('show');
  if(type==='radio') loadRadio();
  if(type==='scene') loadScenes();
}

async function toggleCanteen(){
  const el=document.getElementById('canteen-list-wrap');
  el.classList.toggle('show');
  if(el.classList.contains('show')) loadCanteen();
}

async function loadCanteen(){
  const r=await fetch('/api/tablet/canteen');const d=await r.json();
  document.getElementById('canteen-items').innerHTML=d.menu.map(item=>`
    <div class="carousel-item" onclick="addToCart('${item.id}','${item.name}',${item.price})">
      <span class="ci-name">${item.name}</span>
      <span style="font-size:11px;color:#B8962E;">${item.price.toFixed(2)} €</span>
    </div>`).join('');
  renderCart();
}

function addToCart(id,name,price){if(!cart[id]) cart[id]={id,name,price,qty:0};cart[id].qty++;renderCart();}

function renderCart(){
  const items=Object.values(cart).filter(i=>i.qty>0);
  const total=items.reduce((s,i)=>s+i.price*i.qty,0);
  document.getElementById('cart-list').innerHTML=items.map(i=>`<div class="cart-item"><span>${i.name} x${i.qty}</span><span style="color:#B8962E;">${(i.price*i.qty).toFixed(2)}€</span></div>`).join('')||'<span style="font-size:12px;color:rgba(255,255,255,0.3);">Leer</span>';
  document.getElementById('cart-total').textContent=total.toFixed(2)+' €';
}

async function placeOrder(){
  if(!currentEmployee){showToast('Bitte zuerst anmelden');return;}
  const items=Object.values(cart).filter(i=>i.qty>0);
  if(!items.length){showToast('Warenkorb ist leer');return;}
  await fetch('/api/tablet/canteen/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({employee_id:currentEmployee,name:currentProfile?.name||currentEmployee,items})});
  cart={};renderCart();showToast('Bestellung aufgegeben!');
}

function openMeetingModal(){document.getElementById('m-date').value=new Date().toISOString().split('T')[0];document.getElementById('meeting-modal').classList.add('show');}
function closeMeetingModal(){document.getElementById('meeting-modal').classList.remove('show');}

async function bookMeeting(){
  if(!currentEmployee){showToast('Bitte zuerst anmelden');return;}
  const data={title:document.getElementById('m-title').value||'Meeting',date:document.getElementById('m-date').value,time:document.getElementById('m-time').value,duration:parseInt(document.getElementById('m-duration').value),type:document.getElementById('m-type').value,visibility:document.getElementById('m-visibility').value,room:'Meetingraum',booked_by:currentEmployee};
  const r=await fetch('/api/tablet/meetings/book',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const d=await r.json();
  if(d.ok){showToast('Meetingraum gebucht!');closeMeetingModal();if(data.type==='presentation') activateScene('presentation');}
}

async function savePreferences(){
  if(!currentEmployee){showToast('Bitte zuerst anmelden');return;}
  const temp=parseFloat(document.getElementById('p-temp').value);
  const vent=parseInt(document.getElementById('p-vent').value);
  const light=parseInt(document.getElementById('p-light').value);
  const blind=parseInt(document.getElementById('p-blind').value);
  const autoMedia=document.getElementById('p-auto-media').value;

  if(activeSceneId){
    // Szene speichern
    const empId=currentEmployee;
    const r=await fetch(`/api/tablet/scenes/${empId}`);const d=await r.json();
    const scene=d.scenes.find(s=>s.id===activeSceneId);
    if(scene){
      const updated={...scene, temp, vent, light, blind};
      await fetch(`/api/tablet/scenes/${empId}/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(updated)});
      showToast(`Szene "${scene.name}" gespeichert`);
    }
  } else {
    // Normalbetrieb speichern
    const profile={...currentProfile, temp, vent, light, blind,
      auto_media: autoMedia!=='',
      auto_media_id: autoMedia||null};
    await fetch(`/api/tablet/profile/${currentEmployee}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(profile)});
    currentProfile=profile;
    showToast('Einstellungen gespeichert');
  }
}

loadState();
loadScenes();
setInterval(loadState,5000);
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/tablet')
def tablet():
    return render_template_string(TABLET_HTML)

def start(building_state, actuator_state):
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    init(building_state, actuator_state)
    t = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    t.start()
    print(">> Browser-Interface: http://localhost:5000")
    print(">> Tablet-Interface:  http://localhost:5000/tablet")