class Building:

    def __init__(self, id_building, name):
        self.id_building = id_building
        self.name = name
        # self.id_thingsboard = id_thingsboard
        self.spaces = []

    def add_space(self, space):
        self.spaces.append(space)

    def toString(self):
        return "name " + self.name + " id " + self.id_building + "spaces " + self.spaces
