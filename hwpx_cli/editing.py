"""Edits only XML; no renderer or document serializer is called."""

from copy import deepcopy
import re

from lxml import etree as E

from .package import HEADER, NS, HwpxError, local_name, q, text_of


def require(condition, message):
    if not condition:
        raise HwpxError(message)


def positive(value, label="size"):
    value = float(value)
    require(0 < value <= 1000000, f"Invalid {label}")
    return value


def mm(value):
    return round(positive(value) * 7200 / 25.4)


def color(value):
    require(bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", value)), "Color must be #RRGGBB")
    return value.upper()


def write_text(t, value):
    require(all(local_name(c) in ("lineBreak", "tab") for c in t),
            "Text contains an unsupported inline element; edit refused")
    for c in list(t):
        t.remove(c)
    parts = re.split(r"([\n\t])", value)
    t.text = parts[0]
    for index in range(1, len(parts), 2):
        c = E.SubElement(t, q("hp:lineBreak" if parts[index] == "\n" else "hp:tab"))
        if parts[index] == "\t":
            c.attrib.update({"width": "0", "leader": "0", "type": "1"})
        c.tail = parts[index + 1]


def t_text(t):
    require(all(local_name(c) in ("lineBreak", "tab") for c in t),
            "Unsupported inline element in selected paragraph")
    return (t.text or "") + "".join(("\n" if local_name(c) == "lineBreak" else "\t")
                                    + (c.tail or "") for c in t)


def text_nodes(p):
    return [t for r in p.findall(q("hp:run")) for t in r.findall(q("hp:t"))]


def replace_range(pkg, target, start, end, value):
    name, p = pkg.target(target, "hp:p")
    nodes = text_nodes(p)
    content = [t_text(t) for t in nodes]
    total = sum(map(len, content))
    require(0 <= start <= end <= total, "Text range out of bounds")
    if start == end and not value:
        return 0
    # Bookmark/field anchor movement needs explicit span handling, not flattened text.
    require(not p.xpath(".//hp:fieldBegin | .//hp:fieldEnd | .//hp:bookmark", namespaces=NS),
            "Range edits in paragraphs with fields/bookmarks are not yet supported")
    position = 0
    for run in p.findall(q("hp:run")):
        for child in run:
            if child.tag == q("hp:t"):
                position += len(t_text(child))
            elif local_name(child) in ("pic","tbl","equation","rect","line","ellipse","container"):
                require(not start < position < end,"Range crosses an inline object; use explicit object editing")
    if not nodes:
        r = p.find(q("hp:run"))
        if r is None:
            r = E.SubElement(p, q("hp:run"), charPrIDRef="0")
        nodes = [E.SubElement(r, q("hp:t"))]
        content = [""]
    same_length = len(value) == end - start
    cursor = 0
    inserted = False
    changed = False
    for node, old in zip(nodes, content):
        right = cursor + len(old)
        new = old
        if same_length and cursor < end and right > start:
            left = max(cursor, start)
            stop = min(right, end)
            new = old[:left - cursor] + value[left - start:stop - start] + old[stop - cursor:]
        elif not same_length:
            if not inserted and cursor <= start <= right:
                left_cut = start - cursor
                after_cut = max(left_cut, min(len(old), end - cursor))
                new = old[:left_cut] + value + old[after_cut:]
                inserted = True
            elif cursor < end and right > start:
                new = old[:max(0, start - cursor)] + old[min(len(old), end - cursor):]
        if new != old:
            write_text(node, new)
            changed = True
        cursor = right
    if changed:
        pkg.mark(name)
    return 1


def text_matches(pkg, text, target=None):
    require(bool(text), "Search text cannot be empty")
    pattern = re.compile(re.escape(text))
    for name, paragraph, _ in pkg.elements("p"):
        if paragraph.tag != q("hp:p"):
            continue
        value = text_of(paragraph)
        if not pattern.search(value):
            continue
        address = pkg.address(name, paragraph)
        if target is None or address == target:
            for match in pattern.finditer(value):
                yield address, match.start(), match.end()


def replace_all(pkg, old, new, target=None, all_matches=False):
    hits = list(text_matches(pkg, old, target))
    require(bool(hits), "No matching text")
    require(len(hits) == 1 or all_matches, f"Found {len(hits)} matches; specify --all or a narrower target")
    # Addresses stay valid: range edits never add/remove paragraph-level nodes before commit.
    for address, start, end in reversed(hits):
        replace_range(pkg, address, start, end, new)
    return len(hits)


def new_paragraph(pkg, template=None, text=""):
    attrs = dict(template.attrib) if template is not None else {
        "paraPrIDRef": "0", "styleIDRef": "0", "pageBreak": "0", "columnBreak": "0", "merged": "0"}
    attrs["id"] = pkg.new_id("hp:p")
    attrs.update({"pageBreak":"0","columnBreak":"0","merged":"0"})
    p = E.Element(q("hp:p"), attrs)
    style = "0"
    if template is not None:
        r = template.find(q("hp:run"))
        if r is not None:
            style = r.get("charPrIDRef", "0")
    t = E.SubElement(E.SubElement(p, q("hp:run"), charPrIDRef=style), q("hp:t"))
    write_text(t, text)
    return p


def paragraph_edit(pkg, op, target, text="", offset=0):
    name, p = pkg.target(target, "hp:p")
    parent = p.getparent()
    require(parent is not None, "Paragraph has no container")
    if op in ("insert-before", "insert-after"):
        node = new_paragraph(pkg, p, text)
        parent.insert(parent.index(p) + (op == "insert-after"), node)
    elif op == "delete":
        require(not p.xpath(".//hp:secPr | .//hp:ctrl | .//hp:tbl | .//hp:pic", namespaces=NS),
                "Deleting a paragraph containing controls requires explicit control handling")
        require(len(parent.findall(q("hp:p"))) > 1, "Cannot remove the last paragraph of a container")
        parent.remove(p)
    elif op in ("split", "merge-next"):
        require(all(all(c.tag == q("hp:t") for c in r) for r in p.findall(q("hp:run"))),
                "Split/merge currently requires a text-only paragraph")
        if op == "split":
            require(0 <= offset <= len(text_of(p)), "Split offset out of bounds")
            node = E.Element(q("hp:p"), dict(p.attrib))
            node.set("id", pkg.new_id("hp:p"))
            node.attrib.update({"pageBreak":"0","columnBreak":"0","merged":"0"})
            cursor = 0
            for r in list(p.findall(q("hp:run"))):
                value = "".join(t_text(t) for t in r)
                end = cursor + len(value)
                if cursor >= offset:
                    p.remove(r)
                    node.append(r)
                elif end > offset:
                    suffix = deepcopy(r)
                    for c in list(r):
                        r.remove(c)
                    for c in list(suffix):
                        suffix.remove(c)
                    write_text(E.SubElement(r, q("hp:t")), value[:offset-cursor])
                    write_text(E.SubElement(suffix, q("hp:t")), value[offset-cursor:])
                    node.append(suffix)
                cursor = end
            if not node.findall(q("hp:run")):
                E.SubElement(E.SubElement(node, q("hp:run"), charPrIDRef="0"), q("hp:t"))
            if not p.findall(q("hp:run")):
                E.SubElement(E.SubElement(p,q("hp:run"),charPrIDRef="0"),q("hp:t"))
            parent.insert(parent.index(p)+1, node)
        else:
            node = p.getnext()
            require(node is not None and node.tag == q("hp:p"), "No next paragraph")
            require(not node.xpath(".//hp:secPr | .//hp:ctrl | .//hp:fieldBegin | .//hp:fieldEnd", namespaces=NS),
                    "Next paragraph contains structural controls")
            for r in list(node.findall(q("hp:run"))):
                node.remove(r)
                p.append(r)
            parent.remove(node)
    else:
        raise HwpxError(f"Unknown paragraph operation: {op}")
    pkg.mark(name)
    return 1


def clone_definition(pkg, collection, ident):
    root = pkg.tree(HEADER).find(".//" + q("hh:" + collection))
    require(root is not None, f"Missing {collection}")
    old = next((c for c in root if c.get("id") == str(ident)), None)
    require(old is not None, f"Unknown {collection} ID {ident}")
    node = deepcopy(old)
    node.set("id", str(max((int(c.get("id")) for c in root), default=-1) + 1))
    root.append(node)
    root.set("itemCnt", str(len(root)))
    pkg.mark(HEADER)
    return node


def char_definition(pkg, old_id, properties):
    allowed = {"font", "size", "color", "bold", "italic", "underline"}
    require(set(properties) <= allowed, f"Unknown character properties: {set(properties) - allowed}")
    node = clone_definition(pkg, "charProperties", old_id)
    if "size" in properties:
        node.set("height", str(round(positive(properties["size"], "font size") * 100)))
    if "color" in properties:
        node.set("textColor", color(properties["color"]))
    for tag in ("bold", "italic"):
        if tag in properties:
            require(isinstance(properties[tag], bool), f"{tag} must be boolean")
            child = node.find(q("hh:" + tag))
            if child is not None:
                node.remove(child)
            if properties[tag]:
                underline = node.find(q("hh:underline"))
                node.insert(node.index(underline) if underline is not None else len(node), E.Element(q("hh:"+tag)))
    if "underline" in properties:
        require(isinstance(properties["underline"], bool), "underline must be boolean")
        u = node.find(q("hh:underline"))
        require(u is not None, "Missing underline definition")
        u.set("type", "BOTTOM" if properties["underline"] else "NONE")
    if "font" in properties:
        font_name = properties["font"]
        require(isinstance(font_name, str) and bool(font_name.strip()), "Font name is empty")
        fonts = pkg.tree(HEADER).find(".//" + q("hh:fontfaces"))
        require(fonts is not None, "No fontfaces")
        ref = node.find(q("hh:fontRef"))
        for face in fonts:
            font = next((f for f in face if f.get("face") == font_name), None)
            if font is None:
                font = E.SubElement(face, q("hh:font"), id=str(max((int(f.get("id")) for f in face), default=-1)+1),
                                    face=font_name, type="TTF", isEmbedded="0")
                face.set("fontCnt", str(len(face)))
            ref.set(face.get("lang").lower(), font.get("id"))
    return node.get("id")


def format_text(pkg, target, properties, start=0, end=None):
    name, p = pkg.target(target, "hp:p")
    end = len(text_of(p)) if end is None else end
    require(0 <= start < end <= len(text_of(p)), "Invalid nonempty format range")
    cursor, count, styles = 0, 0, {}
    for run in list(p.findall(q("hp:run"))):
        value = "".join(t_text(t) for t in run.findall(q("hp:t")))
        right = cursor + len(value)
        left, stop = max(start, cursor), min(end, right)
        if left < stop:
            require(all(c.tag == q("hp:t") for c in run), "Formatting mixed control/text runs is not yet supported")
            old = run.get("charPrIDRef")
            if old not in styles:
                styles[old] = char_definition(pkg, old, properties)
            index = p.index(run)
            for a, b, style in ((cursor, left, old), (left, stop, styles[old]), (stop, right, old)):
                if a < b:
                    clone = E.Element(run.tag, dict(run.attrib))
                    clone.set("charPrIDRef", style)
                    write_text(E.SubElement(clone, q("hp:t")), value[a-cursor:b-cursor])
                    p.insert(index, clone)
                    index += 1
            p.remove(run)
            count += 1
        cursor = right
    pkg.mark(name)
    return count


def format_paragraph(pkg, target, properties):
    name, p = pkg.target(target, "hp:p")
    allowed = {"align", "left", "right", "indent", "before", "after", "line-spacing", "page-break", "column-break"}
    require(set(properties) <= allowed, "Unknown paragraph property")
    node = clone_definition(pkg, "paraProperties", p.get("paraPrIDRef"))
    if "align" in properties:
        value = str(properties["align"]).upper()
        require(value in {"LEFT", "RIGHT", "CENTER", "JUSTIFY", "DISTRIBUTE", "DISTRIBUTE_SPACE"}, "Invalid alignment")
        node.find(q("hh:align")).set("horizontal", value)
    margins = {"left": "left", "right": "right", "indent": "intent", "before": "prev", "after": "next"}
    for key, tag in margins.items():
        if key in properties:
            children = node.findall(".//" + q("hc:" + tag))
            require(bool(children), f"Missing paragraph {tag} margin")
            for child in children:
                value = round(float(properties[key]) * 7200 / 25.4)
                if any(a.tag == q("hp:case") and "HwpUnitChar" in a.get(q("hp:required-namespace"),"") for a in child.iterancestors()):
                    value //= 2
                child.set("value",str(value))
    if "line-spacing" in properties:
        children = node.findall(".//" + q("hh:lineSpacing"))
        require(bool(children), "Missing line spacing")
        for child in children:
            child.attrib.update({"type": "PERCENT", "value": str(round(positive(properties["line-spacing"]))), "unit": "HWPUNIT"})
    for key, attr in (("page-break", "pageBreak"), ("column-break", "columnBreak")):
        if key in properties:
            require(isinstance(properties[key], bool), f"{key} must be boolean")
            p.set(attr, "1" if properties[key] else "0")
    p.set("paraPrIDRef", node.get("id"))
    pkg.mark(name)
    return 1


def section_edit(pkg, index, properties):
    require(0 <= index < len(pkg.sections), "Section index out of bounds")
    name = pkg.sections[index]
    sec = pkg.tree(name).find(".//" + q("hp:secPr"))
    require(sec is not None, "Missing section properties")
    page = sec.find(q("hp:pagePr"))
    margin = page.find(q("hp:margin"))
    allowed = {"width", "height", "landscape", "left", "right", "top", "bottom", "header", "footer", "gutter", "columns", "column-gap"}
    require(set(properties) <= allowed, "Unknown section property")
    for key in ("width", "height"):
        if key in properties:
            page.set(key, str(mm(properties[key])))
    if "landscape" in properties:
        require(isinstance(properties["landscape"], bool), "landscape must be boolean")
        page.set("landscape", "NARROWLY" if properties["landscape"] else "WIDELY")
    for key in ("left", "right", "top", "bottom", "header", "footer", "gutter"):
        if key in properties:
            value = float(properties[key])
            require(0 <= value <= 1000000, "Invalid margin")
            margin.set(key, str(round(value*7200/25.4)))
    require(int(page.get("width")) > int(margin.get("left", 0)) + int(margin.get("right", 0)), "Margins exceed page width")
    require(int(page.get("height")) > int(margin.get("top", 0)) + int(margin.get("bottom", 0)), "Margins exceed page height")
    if "columns" in properties or "column-gap" in properties:
        col = pkg.tree(name).find(".//" + q("hp:colPr"))
        require(col is not None, "No column definition")
        if "columns" in properties:
            count = int(properties["columns"])
            require(1 <= count <= 20, "Column count must be 1..20")
            col.set("colCount", str(count))
            col.set("sameSz", "1")
            for c in list(col):
                require(local_name(c) != "colSz", "Unequal columns require explicit width handling")
        if "column-gap" in properties:
            col.set("sameGap", str(round(float(properties["column-gap"])*7200/25.4)))
    pkg.mark(name)
    return 1
