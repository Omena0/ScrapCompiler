from .parser import parse
import json

if __name__ == "__main__":
    import sys, time
    if len(sys.argv) == 1:
        print('Usage: py parser.py <file>')
        exit(-1)

    with open(sys.argv[1]) as f:
        source = f.read()

    start = time.perf_counter()
    ast = parse(source)
    print(f'Took: {(time.perf_counter()-start)*1000} ms.')

    with open('ast.json','w') as f:
        f.write(json.dumps(ast,indent=2))