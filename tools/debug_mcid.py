import sys
from pathlib import Path
import pikepdf

def inspect_node(node, depth=0, max_depth=4):
    if depth > max_depth:
        return
    indent = "  " * depth
    print(f"{indent}Type: {type(node)}, Repr: {repr(node)}")
    
    if isinstance(node, pikepdf.Dictionary):
        if "/K" in node:
            kids = node.get("/K")
            if isinstance(kids, pikepdf.Array):
                for k in kids:
                    inspect_node(k, depth + 1, max_depth)
            else:
                inspect_node(kids, depth + 1, max_depth)
    elif isinstance(node, pikepdf.Array):
        for k in node:
            inspect_node(k, depth + 1, max_depth)

def main():
    if len(sys.argv) < 2:
        print("Bitte PDF-Pfad angeben.")
        sys.exit(1)
        
    pdf_path = Path(sys.argv[1])
    print(f"Untersuche {pdf_path.name}...")
    
    with pikepdf.open(pdf_path) as pdf:
        if "/StructTreeRoot" in pdf.Root:
            inspect_node(pdf.Root.StructTreeRoot)
        else:
            print("Kein StructTreeRoot vorhanden.")

if __name__ == "__main__":
    main()
