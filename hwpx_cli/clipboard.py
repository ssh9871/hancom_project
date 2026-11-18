"""Safe document-local copies and a deliberately explicit HTML subset."""

from copy import deepcopy

from lxml import etree as E, html

from .editing import new_paragraph, require, write_text
from .package import MAX_ENTRY, NS, HwpxError, local_name, q


def copy_node(pkg,target,destination):
    source_name,node = pkg.target(target)
    dest_name,dest = pkg.target(destination,"hp:p")
    require(node.tag in {q("hp:p"),q("hp:tbl"),q("hp:pic"),q("hp:equation"),q("hp:rect"),q("hp:line")},"Unsupported copy source")
    require(not node.xpath(".//hp:secPr | .//hp:fieldBegin | .//hp:fieldEnd | .//hp:bookmark",namespaces=NS),
            "Copying section properties/fields/bookmarks requires explicit reference remapping")
    clone = deepcopy(node)
    for child in clone.iter():
        if child.get("id","").isdecimal() and E.QName(child).namespace == NS["hp"]:
            ident = pkg.new_id("hp:"+local_name(child))
            child.set("id",ident)
            if "instid" in child.attrib:
                child.set("instid",ident)
    if clone.tag == q("hp:p"):
        dest.addnext(clone)
    else:
        E.SubElement(dest,q("hp:run"),charPrIDRef="0").append(clone)
    pkg.mark(dest_name)
    return {"target":pkg.address(dest_name,clone)}


def paste_html(pkg,target,markup):
    require(isinstance(markup,str) and len(markup.encode("utf-8")) <= MAX_ENTRY,"HTML input exceeds limit")
    try:
        root = html.fragment_fromstring(markup,create_parent="div",parser=html.HTMLParser(no_network=True))
    except E.ParserError as exc:
        raise HwpxError("Invalid HTML") from exc
    allowed = {"div","p","br","span","b","strong","i","em","u"}
    require(all(n.tag in allowed for n in root.iter()),"HTML currently supports text paragraphs only; unsupported elements refused")
    require(all(not n.attrib for n in root.iter()),"HTML attributes/styles/URLs are not yet supported")
    name,p = pkg.target(target,"hp:p")
    def segments(node,style=None):
        style = dict(style or {})
        if node.tag in ("b","strong"):style["bold"] = True
        if node.tag in ("i","em"):style["italic"] = True
        if node.tag == "u":style["underline"] = True
        if node.tag == "br":yield "\n",style
        if node.text:yield node.text,style
        for child in node:
            yield from segments(child,style)
            if child.tail:yield child.tail,style
    from .editing import char_definition
    blocks = [segments(root)]
    if all(c.tag in ("p", "div") for c in root):
        blocks = []
        if (root.text or "").strip():
            blocks.append([(root.text, {})])
        for child in root:
            blocks.append(segments(child))
            if (child.tail or "").strip():
                blocks.append([(child.tail, {})])
    results = []
    anchor = p
    for block in blocks:
        new = new_paragraph(pkg,p)
        for child in list(new):new.remove(child)
        for text,props in block:
            style = char_definition(pkg,"0",props) if props else "0"
            write_text(E.SubElement(E.SubElement(new,q("hp:run"),charPrIDRef=style),q("hp:t")),text)
        if not len(new):E.SubElement(E.SubElement(new,q("hp:run"),charPrIDRef="0"),q("hp:t"))
        anchor.addnext(new);anchor=new
        results.append(new)
    pkg.mark(name)
    return {"targets":[pkg.address(name,n) for n in results]}
