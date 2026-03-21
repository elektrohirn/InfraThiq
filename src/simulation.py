import random
import math

room_orientation = {
    "Buero": 180,
    "Meetingraum": 270,
    "Serverraum": 0,
}

people = []

class Person:
    def __init__(self, person_id):
        self.person_id = person_id
        self.location  = "draussen"

    def update(self, hour):
        if self.location == "draussen":
            if 7 <= hour < 9 and random.random() < 0.3:
                self.location = "Buero"
            elif 9 <= hour < 10 and random.random() < 0.5:
                self.location = "Buero"
        elif 9 <= hour < 17:
            roll = random.random()
            if roll < 0.05:
                self.location = "Meetingraum"
            elif roll < 0.08:
                self.location = "Serverraum"
            elif roll < 0.12:
                self.location = "Buero"
        elif hour >= 17:
            if random.random() < 0.2:
                self.location = "draussen"
        if hour >= 19 or hour < 7:
            self.location = "draussen"

def init_people(count=15):
    global people
    people = [Person(i) for i in range(count)]

def simulate_occupancy(building_state, hour, minute):
    global people
    if not people:
        init_people(15)
    for person in people:
        person.update(hour)
    server_count = sum(1 for p in people if p.location == "Serverraum")
    if server_count > 2:
        extras = [p for p in people if p.location == "Serverraum"][2:]
        for p in extras:
            p.location = "Buero"
    for room in building_state:
        building_state[room]["occupancy"] = sum(1 for p in people if p.location == room)

def simulate_sun_position(hour, minute):
    total_minutes = (hour - 6) * 60 + minute
    total_minutes = max(0, min(720, total_minutes))
    return 90 + (total_minutes / 720) * 180

def simulate_environment(building_state, actuator_state, outside_light, sun_position, cloud_cover, hour, minute):
    simulate_occupancy(building_state, hour, minute)
    sun_position = simulate_sun_position(hour, minute)

    cloud_cover += random.uniform(-0.03, 0.03)
    cloud_cover  = max(0, min(1, cloud_cover))

    if 6 <= hour < 18:
        base_light       = math.sin((hour - 6) / 12 * math.pi) * 100 + random.uniform(-5, 5)
        diffuse_light    = max(0, min(100, base_light * (0.3 + 0.7 * cloud_cover)))
        direct_radiation = max(0, min(100, base_light * (1 - cloud_cover)))
    else:
        diffuse_light    = 0
        direct_radiation = 0

    outside_light = max(diffuse_light, direct_radiation)

    for room in building_state:
        people_count = building_state[room]["occupancy"]

        co2  = building_state[room]["co2"]
        co2 += people_count * 40
        co2 -= actuator_state[room]["vent"].get_value() * 5
        co2  = max(400, min(3000, co2))
        building_state[room]["co2"] = co2

        temp  = building_state[room]["temp"]
        temp += actuator_state[room]["heat"].get_value() * 0.02
        temp -= actuator_state[room]["cool"].get_value() * 0.02

        if room == "Serverraum":
            temp += 0.08

        orientation = room_orientation[room]
        diff = abs((sun_position - orientation + 180) % 360 - 180)
        if diff < 60:
            blind_value = actuator_state[room]["blind"].get_value()
            temp += direct_radiation * 0.002 * (1 - blind_value / 100)

        temp = max(14, min(35, temp))
        building_state[room]["temp"] = temp

        blind_value = actuator_state[room]["blind"].get_value()
        building_state[room]["light_sensor"] = diffuse_light * (1 - blind_value / 100)

    return building_state, outside_light, sun_position, cloud_cover, direct_radiation