room_orientation = {
    "Buero": 180,
    "Meetingraum": 270,
    "Serverraum": 0,
}

temp_setpoints = {
    "Buero": 21,
    "Meetingraum": 21,
    "Serverraum": 19,
}

def get_mode(hour):
    if 8 <= hour < 18:
        return "comfort"
    return "night"

def apply_control(building_state, actuator_state, outside_light, sun_position, cloud_cover, hour, direct_radiation):
    mode = get_mode(hour)

    for room in building_state:
        co2          = building_state[room]["co2"]
        temp         = building_state[room]["temp"]
        occ          = building_state[room]["occupancy"]
        light_sensor = building_state[room]["light_sensor"]
        setpoint     = temp_setpoints[room]
        if mode == "night":
            setpoint -= 2

        orientation = room_orientation[room]
        diff = abs((sun_position - orientation + 180) % 360 - 180)
        if diff < 60 and direct_radiation > 15:
            actuator_state[room]["blind"].update_auto(80)
        elif diff < 60 and direct_radiation > 10:
            actuator_state[room]["blind"].update_auto(40)
        else:
            actuator_state[room]["blind"].update_auto(0)

        if co2 >= 1400:
            vent = 100
        elif co2 >= 1000:
            vent = 60
        elif co2 >= 800:
            vent = 30
        else:
            vent = 0
        if mode == "night" and co2 < 1400:
            vent = min(vent, 30)
        actuator_state[room]["vent"].update_auto(vent)

        if temp < setpoint - 0.5:
            actuator_state[room]["heat"].update_auto(70)
        else:
            actuator_state[room]["heat"].update_auto(0)

        if temp > setpoint + 1.5:
            actuator_state[room]["cool"].update_auto(100)
        elif temp > setpoint + 0.5:
            actuator_state[room]["cool"].update_auto(70)
        else:
            actuator_state[room]["cool"].update_auto(0)

        if occ > 0 and light_sensor < 40:
            building_state[room]["light"] = 100
        else:
            building_state[room]["light"] = 0

    return actuator_state