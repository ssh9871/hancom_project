"""Table edits operate on a validated logical grid, including merged cells."""

from copy import deepcopy

from lxml import etree as E

from .editing import mm, new_paragraph, require, clone_definition, color
from .package import HEADER, HwpxError, NS, q


def cell_new(pkg, template=None, text=""):
    cell = E.Element(q("hp:tc"), name="", header="0", hasMargin="1", protect="0", editable="0", dirty="0", borderFillIDRef="1")
    sub = E.SubElement(cell, q("hp:subList"), id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign="CENTER",
                       linkListIDRef="0", linkListNextIDRef="0", textWidth="0", textHeight="0", hasTextRef="0", hasNumRef="0")
    sub.append(new_paragraph(pkg, template, text))
    E.SubElement(cell, q("hp:cellAddr"), colAddr="0", rowAddr="0")
    E.SubElement(cell, q("hp:cellSpan"), colSpan="1", rowSpan="1")
    E.SubElement(cell, q("hp:cellSz"), width="1", height="1")
    E.SubElement(cell, q("hp:cellMargin"), left="283", right="283", top="141", bottom="141")
    return cell


def grid(table):
    rows, cols = int(table.get("rowCnt", "0")), int(table.get("colCnt", "0"))
    require(0 < rows <= 1000 and 0 < cols <= 1000 and rows * cols <= 100000, "Invalid or excessive table dimensions")
    specs, occupied = [], {}
    for tr in table.findall(q("hp:tr")):
        for cell in tr.findall(q("hp:tc")):
            addr, span = cell.find(q("hp:cellAddr")), cell.find(q("hp:cellSpan"))
            require(addr is not None and span is not None, "Missing cell address/span")
            r, c = int(addr.get("rowAddr")), int(addr.get("colAddr"))
            rs, cs = int(span.get("rowSpan")), int(span.get("colSpan"))
            require(r >= 0 and c >= 0 and rs > 0 and cs > 0 and r+rs <= rows and c+cs <= cols, "Cell span out of bounds")
            spec = [r, c, rs, cs, cell]
            specs.append(spec)
            for y in range(r, r+rs):
                for x in range(c, c+cs):
                    require((y, x) not in occupied, "Overlapping table cells")
                    occupied[y, x] = spec
    require(len(occupied) == rows*cols, "Table grid has holes")
    return rows, cols, specs, occupied


def dimensions(table, rows, cols, specs):
    widths, heights = [None]*cols, [None]*rows
    for r, c, rs, cs, cell in specs:
        size = cell.find(q("hp:cellSz"))
        require(size is not None, "Missing cell size")
        if cs == 1:
            widths[c] = int(size.get("width"))
        if rs == 1:
            heights[r] = int(size.get("height"))
    # shortcut: merged-only tracks use equal shares; explicit track resizing can replace them.
    size = table.find(q("hp:sz"))
    for tracks, total in ((widths, int(size.get("width"))), (heights, int(size.get("height")))):
        known = sum(t for t in tracks if t is not None)
        missing = sum(t is None for t in tracks)
        if missing:
            remainder = total-known
            require(remainder >= missing, "Cannot infer positive track dimensions")
            for i, t in enumerate(tracks):
                if t is None:
                    value = remainder//missing
                    tracks[i] = value
                    remainder -= value
                    missing -= 1
        require(all(t > 0 for t in tracks), "Table track size must be positive")
    return widths, heights


def rebuild(table, specs, widths, heights):
    table.set("rowCnt", str(len(heights)))
    table.set("colCnt", str(len(widths)))
    table.find(q("hp:sz")).attrib.update({"width": str(sum(widths)), "height": str(sum(heights))})
    old_rows = table.findall(q("hp:tr"))
    index = table.index(old_rows[0]) if old_rows else len(table)
    for row in old_rows:
        table.remove(row)
    rows = []
    for _ in heights:
        row = E.Element(q("hp:tr"))
        table.insert(index, row)
        index += 1
        rows.append(row)
    for r, c, rs, cs, cell in sorted(specs, key=lambda x: (x[0], x[1])):
        cell.find(q("hp:cellAddr")).attrib.update({"rowAddr": str(r), "colAddr": str(c)})
        cell.find(q("hp:cellSpan")).attrib.update({"rowSpan": str(rs), "colSpan": str(cs)})
        cell.find(q("hp:cellSz")).attrib.update({"width": str(sum(widths[c:c+cs])), "height": str(sum(heights[r:r+rs]))})
        rows[r].append(cell)
    grid(table)


def create_table(pkg, target, rows, cols, values=None, width=160, row_height=10):
    name, p = pkg.target(target, "hp:p")
    require(0 < rows <= 1000 and 0 < cols <= 1000 and rows*cols <= 100000, "Table dimensions out of range")
    if values is not None:
        require(len(values) == rows and all(len(row) == cols for row in values), "Values must match table dimensions")
    width, height = mm(width), mm(row_height)
    require(width >= cols and height > 0, "Table dimensions must allow positive cell sizes")
    table = E.Element(q("hp:tbl"), id=pkg.new_id("hp:tbl"), zOrder="0", numberingType="TABLE", textWrap="SQUARE",
                      textFlow="BOTH_SIDES", lock="0", dropcapstyle="None", pageBreak="CELL", repeatHeader="0",
                      rowCnt=str(rows), colCnt=str(cols), cellSpacing="0", borderFillIDRef="1", noAdjust="0")
    E.SubElement(table, q("hp:sz"), width=str(width), widthRelTo="ABSOLUTE", height=str(height*rows), heightRelTo="ABSOLUTE", protect="0")
    E.SubElement(table, q("hp:pos"), treatAsChar="1", affectLSpacing="1", flowWithText="1", allowOverlap="0",
                 holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="PARA", vertAlign="TOP", horzAlign="LEFT", vertOffset="0", horzOffset="0")
    E.SubElement(table, q("hp:outMargin"), left="0", right="0", top="0", bottom="0")
    E.SubElement(table, q("hp:inMargin"), left="283", right="283", top="141", bottom="141")
    widths = [width//cols + (i < width % cols) for i in range(cols)]
    specs = [[r,c,1,1,cell_new(pkg,p,str(values[r][c]) if values is not None else "")]
             for r in range(rows) for c in range(cols)]
    rebuild(table, specs, widths, [height]*rows)
    run = E.SubElement(p, q("hp:run"), charPrIDRef="0")
    run.append(table)
    E.SubElement(run, q("hp:t"))
    pkg.mark(name)
    return {"target": pkg.address(name, table), "rows": rows, "columns": cols}


def table_edit(pkg, target, op, **args):
    name, table = pkg.target(target, "hp:tbl")
    rows, cols, specs, occupied = grid(table)
    if op == "border":
        props = args["properties"]
        require(set(props) <= {"color", "width", "type"}, "Unknown border property")
        line_type = props.get("type","SOLID")
        require(line_type in {"NONE","SOLID","DASH","DOT","DASH_DOT","DASH_DOT_DOT","LONG_DASH","CIRCLE","DOUBLE_SLIM","SLIM_THICK","THICK_SLIM","SLIM_THICK_SLIM","WAVE","DOUBLE_WAVE"},"Invalid border line type")
        if "width" in props:
            require(0 < float(props["width"]) <= 5,"Border width must be greater than zero and at most 5 mm")
        borders = {}
        for _, _, _, _, cell in specs:
            ref = cell.get("borderFillIDRef")
            if ref in borders:
                cell.set("borderFillIDRef", borders[ref])
                continue
            border = clone_definition(pkg, "borderFills", ref)
            for side in ("leftBorder","rightBorder","topBorder","bottomBorder"):
                child = border.find(q("hh:"+side))
                require(child is not None, "Missing border edge")
                child.set("type",line_type)
                if "color" in props:
                    child.set("color",color(props["color"]))
                if "width" in props:
                    child.set("width",f"{float(props['width']):g} mm")
            cell.set("borderFillIDRef",border.get("id"))
            borders[ref] = border.get("id")
        pkg.mark(name)
        return 1
    if op == "resize":
        for axis, count, start, span in (("width", cols, 1, 3), ("height", rows, 0, 2)):
            if args.get(axis) is None:
                continue
            total = mm(args[axis])
            require(total >= count, "Table dimensions must allow positive cell sizes")
            tracks = [total//count + (i < total % count) for i in range(count)]
            table.find(q("hp:sz")).set(axis, str(total))
            for spec in specs:
                cell_length = sum(tracks[spec[start]:spec[start]+spec[span]])
                spec[4].find(q("hp:cellSz")).set(axis, str(cell_length))
        pkg.mark(name)
        return 1
    widths, heights = dimensions(table, rows, cols, specs)
    if op == "delete":
        table.getparent().remove(table)
        pkg.mark(name)
        return 1
    elif op in ("insert-row", "insert-column", "delete-row", "delete-column"):
        axis = 0 if op.endswith("row") else 1
        index = int(args["index"])
        tracks = heights if axis == 0 else widths
        count = len(tracks)
        inserting = op.startswith("insert")
        require(0 <= index <= count if inserting else 0 <= index < count, "Track index out of range")
        require(inserting or count > 1, "Cannot delete the last track")
        if inserting:
            size = mm(args.get("size", 10 if axis == 0 else 30))
            require(size > 0, "Table track size must be positive")
            tracks.insert(index, size)
            for s in specs:
                if s[axis] >= index:
                    s[axis] += 1
                elif s[axis]+s[axis+2] > index:
                    s[axis+2] += 1
            newrows, newcols = len(heights), len(widths)
            filled = {(r,c) for y,x,rs,cs,_ in specs for r in range(y,y+rs) for c in range(x,x+cs)}
            template = table.find(".//"+q("hp:p"))
            neighbor = max(0, index - 1)
            for r in range(newrows):
                for c in range(newcols):
                    if (r,c) not in filled:
                        source = occupied[(neighbor,c) if axis == 0 else (r,neighbor)][4]
                        cell = cell_new(pkg, template)
                        cell.set("borderFillIDRef", source.get("borderFillIDRef"))
                        specs.append([r,c,1,1,cell])
        else:
            removed = []
            for s in specs:
                if s[axis] <= index < s[axis]+s[axis+2]:
                    if s[axis+2] == 1:
                        removed.append(s)
                    else:
                        s[axis+2] -= 1
                elif s[axis] > index:
                    s[axis] -= 1
            for s in removed:
                specs.remove(s)
            tracks.pop(index)
    elif op == "merge":
        r0,c0,r1,c1 = (int(args[k]) for k in ("row", "column", "end_row", "end_column"))
        require(0 <= r0 <= r1 < rows and 0 <= c0 <= c1 < cols, "Invalid merge rectangle")
        chosen = [s for s in specs if not (s[0]+s[2] <= r0 or s[0] > r1 or s[1]+s[3] <= c0 or s[1] > c1)]
        require(all(r0 <= r and c0 <= c and r+rs <= r1+1 and c+cs <= c1+1 for r,c,rs,cs,_ in chosen),
                "Merge rectangle cuts an existing merged cell")
        anchor = occupied[r0,c0]
        sub = anchor[4].find(q("hp:subList"))
        for s in sorted(chosen, key=lambda x:(x[0],x[1])):
            if s is not anchor:
                for p in list(s[4].find(q("hp:subList"))):
                    sub.append(p)
                specs.remove(s)
        anchor[2], anchor[3] = r1-r0+1, c1-c0+1
    elif op == "split-cell":
        r,c = int(args["row"]), int(args["column"])
        require((r,c) in occupied, "Cell out of bounds")
        s = occupied[r,c]
        y,x,rs,cs,cell = s
        subdivisions = (int(args.get("rows",1)),int(args.get("columns",1)))
        if subdivisions != (1,1):
            nr,nc = subdivisions
            require(rs == cs == 1,"Explicit subdivisions currently require an unmerged cell")
            require(1 <= nr <= 100 and 1 <= nc <= 100 and nr*nc > 1,"Invalid subdivision counts")
            require(heights[y] >= nr and widths[x] >= nc,"Subdivisions would create zero-sized tracks")
            h,w = heights[y],widths[x]
            heights[y:y+1] = [h//nr+(i<h%nr) for i in range(nr)]
            widths[x:x+1] = [w//nc+(i<w%nc) for i in range(nc)]
            for other in specs:
                if other is s:continue
                for axis,at,count in ((0,y,nr),(1,x,nc)):
                    if other[axis] > at:other[axis] += count-1
                    elif other[axis] <= at < other[axis]+other[axis+2]:other[axis+2] += count-1
            for a in range(nr):
                for b in range(nc):
                    if a or b:
                        fresh = cell_new(pkg,cell.find(".//"+q("hp:p")))
                        fresh.set("borderFillIDRef",cell.get("borderFillIDRef"))
                        specs.append([y+a,x+b,1,1,fresh])
            rebuild(table,specs,widths,heights)
            pkg.mark(name)
            return 1
        require(rs > 1 or cs > 1, "Cell is unmerged; specify rows/columns to subdivide it")
        s[2], s[3] = 1,1
        for a in range(y,y+rs):
            for b in range(x,x+cs):
                if (a,b) != (y,x):
                    fresh = cell_new(pkg, cell.find(".//"+q("hp:p")))
                    fresh.set("borderFillIDRef", cell.get("borderFillIDRef"))
                    specs.append([a,b,1,1,fresh])
    elif op == "transpose":
        for s in specs:
            s[0],s[1],s[2],s[3] = s[1],s[0],s[3],s[2]
        widths,heights = heights,widths
    elif op == "split-table":
        index = int(args["index"])
        require(0 < index < rows,"Split row must be inside the table")
        require(not any(r < index < r+rs for r,c,rs,cs,cell in specs),"Split crosses a merged cell; split the cell first")
        second = deepcopy(table)
        second.set("id",pkg.new_id("hp:tbl"))
        before = [s for s in specs if s[0] < index]
        after = [[r-index,c,rs,cs,cell] for r,c,rs,cs,cell in specs if r >= index]
        rebuild(second,after,widths,heights[index:])
        rebuild(table,before,widths,heights[:index])
        table.addnext(second)
        pkg.mark(name)
        return {"target":pkg.address(name,second)}
    elif op == "merge-table":
        other_name,other = pkg.target(args["other"],"hp:tbl")
        require(other_name == name and other is not table,"Tables must be distinct and in the same section")
        require(other not in table.iter() and table not in other.iter(),"Cannot merge ancestor/descendant tables")
        r2,c2,s2,_ = grid(other)
        w2,h2 = dimensions(other,r2,c2,s2)
        require(cols == c2 and widths == w2,"Tables must have identical column tracks")
        specs += [[r+rows,c,rs,cs,cell] for r,c,rs,cs,cell in s2]
        heights += h2
        other.getparent().remove(other)
    else:
        raise HwpxError(f"Table operation not implemented: {op}")
    rebuild(table,specs,widths,heights)
    pkg.mark(name)
    return 1
