from schemlib import *

SIZE = 25*25*25

def shaderfunc(x,y,z):
    conn = []

    ID = x + y*25*25 + z * 25 + 1

    conn.append({"id": ID%SIZE})
    
    if not conn: conn = None

    mode = 1
    return generate_gate(conn, mode, x, y, z)

schem = Schematic(25,25,25)

schem.compile(shaderfunc).save('a.json')
