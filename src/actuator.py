class Actuator:
    def __init__(self, name, value=0, min_value=0, max_value=100):
        self.name = name
        self.value = value
        self.min_value = min_value
        self.max_value = max_value
        self.mode = "auto"
        self.manual_value = None

    def set_manual(self, value):
        value = max(self.min_value, min(self.max_value, value))
        self.value = value
        self.mode = "manual"
        self.manual_value = value

    def set_auto(self):
        self.mode = "auto"
        self.manual_value = None

    def update_auto(self, target):
        if self.mode == "auto":
            self.value = max(self.min_value, min(self.max_value, target))

    def get_value(self):
        return self.value