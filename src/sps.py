from logger import log

_connected = False
_plc       = None
_reconnect_attempts = 0
MAX_RECONNECT_ATTEMPTS = 3

try:
    import pyads
    _pyads_available = True
except Exception:
    _pyads_available = False

AMS_NET_ID = "192.168.1.5.1.1"
ADS_PORT   = 851

def connect():
    global _plc, _connected, _reconnect_attempts
    if not _pyads_available:
        print(">> pyads nicht gefunden – Simulationsmodus aktiv.")
        return
    try:
        _plc = pyads.Connection(AMS_NET_ID, ADS_PORT)
        _plc.open()
        _connected          = True
        _reconnect_attempts = 0
        log("SPS", detail="Verbindung hergestellt")
        print(">> SPS verbunden.")
    except Exception as e:
        _connected = False
        log("SPS", detail=f"Verbindung fehlgeschlagen: {e}")
        print(">> SPS nicht erreichbar – Simulationsmodus aktiv.")

def disconnect():
    global _plc, _connected
    if _plc and _connected:
        _plc.close()
        _connected = False
        log("SPS", detail="Verbindung getrennt")

def reconnect_if_needed():
    global _reconnect_attempts
    if _connected or not _pyads_available:
        return
    if _reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
        return
    _reconnect_attempts += 1
    log("SPS", detail=f"Reconnect-Versuch {_reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS}")
    connect()

def write(variable, value):
    if not _connected:
        return
    try:
        _plc.write_by_name(variable, value)
    except Exception as e:
        log("SPS Schreibfehler", detail=f"{variable} = {value} | {e}")
        _handle_connection_error()

def read(variable, plc_type=None):
    if not _connected:
        return None
    try:
        t = plc_type if plc_type else pyads.PLCTYPE_REAL
        return _plc.read_by_name(variable, t)
    except Exception as e:
        log("SPS Lesefehler", detail=f"{variable} | {e}")
        _handle_connection_error()
        return None

def _handle_connection_error():
    global _connected, _reconnect_attempts
    _connected          = False
    _reconnect_attempts = 0
    log("SPS", detail="Verbindung verloren – Simulationsmodus aktiv")
    print(">> SPS Verbindung verloren – weiter im Simulationsmodus.")

def is_connected():
    return _connected

def push_actuators(actuator_state):
    if not _connected:
        return
    for room, acts in actuator_state.items():
        for act_name, act_obj in acts.items():
            write(f"GVL.{room}_{act_name}", float(act_obj.get_value()))

def pull_sensors(building_state):
    if not _connected:
        return building_state
    for room in building_state:
        co2  = read(f"GVL.{room}_co2")
        temp = read(f"GVL.{room}_temp")
        occ  = read(f"GVL.{room}_occupancy")
        if co2  is not None: building_state[room]["co2"]  = co2
        if temp is not None: building_state[room]["temp"] = temp
        if occ  is not None: building_state[room]["occupancy"] = int(occ)
    return building_state