"""Bounded arithmetic AST interpreter; no eval, attributes, or Python calls."""

import ast
import math
import re

from .editing import replace_range, require
from .package import HwpxError, q, text_of
from .tables import grid

CELL = r"(?:[A-Z]+|\?)(?:[1-9][0-9]*|\?)"


def evaluate(pkg,target,formula,row=0,column=0,write=False):
    name,table = pkg.target(target,"hp:tbl")
    rows,cols,specs,_ = grid(table)
    require(0 <= row < rows and 0 <= column < cols,"Result cell out of bounds")
    require(isinstance(formula,str) and 0 < len(formula) <= 4096,"Invalid formula length")
    source = formula.strip().removeprefix("=").upper()
    require(bool(re.fullmatch(r"[A-Z0-9?.+*/(),:\s-]+",source)),"Invalid formula character")
    aliases = {}
    def reference(match):
        key = "CELL_"+str(len(aliases))
        aliases[key] = match.group()
        return key
    source = re.sub(rf"(?<![A-Z0-9]){CELL}(?![A-Z0-9])",reference,source)
    source = re.sub(r"(CELL_\d+)\s*:\s*(CELL_\d+)",r"RANGE(\1,\2)",source)
    try:
        tree = ast.parse(source,mode="eval")
    except (SyntaxError,RecursionError) as exc:
        raise HwpxError("Invalid formula syntax") from exc
    require(sum(1 for _ in ast.walk(tree)) <= 512,"Formula complexity limit exceeded")
    anchors = {(r,c):cell for r,c,rs,cs,cell in specs}

    def coords(node):
        require(isinstance(node,ast.Name) and node.id in aliases,"Expected cell reference")
        match = re.fullmatch(r"([A-Z]+|\?)([0-9]+|\?)",aliases[node.id])
        col,r = match.groups()
        c = column if col == "?" else sum((ord(ch)-64)*26**i for i,ch in enumerate(reversed(col)))-1
        r = row if r == "?" else int(r)-1
        require(0 <= r < rows and 0 <= c < cols,"Cell reference outside table")
        return r,c

    def number(r,c):
        cell = anchors.get((r,c))
        if cell is None:
            return None
        p = cell.find(".//"+q("hp:p"))
        value = re.sub(r"[\s,]","",text_of(p)) if p is not None else ""
        try:
            value = float(value)
        except ValueError:
            return None
        require(math.isfinite(value),"Non-finite cell number")
        return value

    def collect(node):
        if isinstance(node,ast.Name) and node.id in aliases:
            value = number(*coords(node))
            return [] if value is None else [value]
        if isinstance(node,ast.Name) and node.id in ("LEFT","RIGHT","ABOVE","BELOW"):
            points = ([(row,c) for c in range(column)] if node.id == "LEFT" else
                      [(row,c) for c in range(column+1,cols)] if node.id == "RIGHT" else
                      [(r,column) for r in range(row)] if node.id == "ABOVE" else
                      [(r,column) for r in range(row+1,rows)])
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id == "RANGE":
            require(len(node.args) == 2 and not node.keywords,"Range requires two references")
            r0,c0 = coords(node.args[0]); r1,c1 = coords(node.args[1])
            points = [(r,c) for r in range(min(r0,r1),max(r0,r1)+1) for c in range(min(c0,c1),max(c0,c1)+1)]
        else:
            return [scalar(node)]
        return [v for r,c in points if (v := number(r,c)) is not None]

    def scalar(node,depth=0):
        require(depth < 64,"Formula nesting limit exceeded")
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            return float(node.value)
        if isinstance(node,ast.Name) and node.id in aliases:
            return number(*coords(node)) or 0
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            return (-1 if isinstance(node.op,ast.USub) else 1)*scalar(node.operand,depth+1)
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b = scalar(node.left,depth+1),scalar(node.right,depth+1)
            if isinstance(node.op,ast.Add): return a+b
            if isinstance(node.op,ast.Sub): return a-b
            if isinstance(node.op,ast.Mult): return a*b
            require(b != 0,"Division by zero")
            return a/b
        require(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords,"Unsupported expression")
        fn,args = node.func.id,node.args
        if fn == "IF":
            require(len(args) == 3,"IF requires three arguments")
            return scalar(args[1] if scalar(args[0],depth+1) != 0 else args[2],depth+1)
        aggregate = {"SUM","PRODUCT","COUNT","AVG","AVERAGE","MIN","MAX"}
        if fn in aggregate:
            values = [v for arg in args for v in collect(arg)]
            if fn == "SUM": return sum(values)
            if fn == "PRODUCT": return math.prod(values)
            if fn == "COUNT": return len(values)
            if fn in ("AVG","AVERAGE"): return sum(values)/len(values) if values else 0
            return (min(values) if fn == "MIN" else max(values)) if values else 0
        if fn == "MOD":
            require(len(args) == 2,"MOD requires two arguments")
            return math.fmod(scalar(args[0],depth+1),scalar(args[1],depth+1))
        functions = {"ABS":abs,"SQRT":math.sqrt,"EXP":math.exp,"LOG":math.log,"SIN":math.sin,"COS":math.cos,"TAN":math.tan,
                     "ASIN":math.asin,"ACOS":math.acos,"ATAN":math.atan,"RADIAN":math.radians,"SIGN":lambda x:(x>0)-(x<0),
                     "INT":math.trunc,"CEILING":math.ceil,"FLOOR":math.floor,"ROUND":lambda x:math.copysign(math.floor(abs(x)+0.5),x),"TRUNC":math.trunc}
        require(fn in functions and len(args) == 1,"Unknown function or wrong argument count")
        return functions[fn](scalar(args[0],depth+1))

    try:
        result = scalar(tree.body)
        require(math.isfinite(result),"Non-finite formula result")
    except (ValueError,OverflowError,ZeroDivisionError,RecursionError) as exc:
        raise HwpxError(f"Formula evaluation failed: {exc}") from exc
    if write:
        require((row,column) in anchors,"Result must target a merged cell anchor")
        p = anchors[row,column].find(".//"+q("hp:p"))
        value = str(int(result)) if result == int(result) and abs(result) < 1e15 else str(result)
        replace_range(pkg,pkg.address(name,p),0,len(text_of(p)),value)
    return {"result":result,"formula":formula,"written":write}
