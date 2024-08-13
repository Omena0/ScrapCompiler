import json

TEMPLATE = {
    "bodies": [
        {
            "childs": [

            ]
        }
    ],
    "version": 4
}

ID = 0

def generate_gate(connections:list, mode:int, x:int, y:int, z:int):
    global ID
    ID += 1
    return {
            "color": "19E753",
            "controller": {
                "active": False,
                "controllers": connections,
                "id": ID,
                "joints": None,
                "mode": mode
            },
            "pos": { "x": x, "y": z, "z": y },
            "shapeId": "9f0f56e8-2c31-4d83-996c-d00a9b296c3f",
            "xaxis": 1,
            "zaxis": -2
        }

class Schematic:
    def __init__(self,width,depth,height):
        self.width = width
        self.depth = depth
        self.height = height
        self.data = None
        self.schem = TEMPLATE
    
    def compile(self,func):
        self.data = {}
        for y in range(self.height):
            for z in range(self.depth):
                for x in range(self.width):
                    self.data[x,y,z] = func(x,y,z)
        return self

    def add_block(self, x, y, z, block):
        self.data[x,y,z] = block

    def save(self,name):
        for (x,y,z), block in self.data.items():
            self.schem['bodies'][0]['childs'].append(block)

        with open(name,'w') as f:
            json.dump(self.schem,f)

__all__ = 'Schematic', 'generate_gate'