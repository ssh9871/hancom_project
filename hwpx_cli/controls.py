"""Direct XML controls and shared style management."""

from copy import deepcopy

from lxml import etree as E

from .editing import color, mm, new_paragraph, positive, require, t_text, write_text
from .package import HEADER, NS, HwpxError, local_name, q, text_of


def append_control(pkg,target,node):
    name,p = pkg.target(target,"hp:p")
    run = E.SubElement(p,q("hp:run"),charPrIDRef="0")
    ctrl = E.SubElement(run,q("hp:ctrl"))
    ctrl.append(node)
    E.SubElement(run,q("hp:t"))
    pkg.mark(name)
    return name,node


def sublist(pkg,node,text,template=None):
    sub = E.SubElement(node,q("hp:subList"),id="",textDirection="HORIZONTAL",lineWrap="BREAK",vertAlign="TOP",
                       linkListIDRef="0",linkListNextIDRef="0",textWidth="0",textHeight="0",hasTextRef="0",hasNumRef="0")
    sub.append(new_paragraph(pkg,template,text))
    return sub


def control_create(pkg,target,kind,text="",name="",properties=None):
    properties = properties or {}
    _,p = pkg.target(target,"hp:p")
    if kind in ("header","footer"):
        require(set(properties) <= {"apply"},"Unknown header/footer property")
        apply = properties.get("apply","BOTH")
        require(apply in ("BOTH","ODD","EVEN"),"Invalid applyPageType")
        node = E.Element(q("hp:"+kind),id=pkg.new_id("hp:"+kind),applyPageType=apply)
        sublist(pkg,node,text,p)
    elif kind in ("footNote","endNote"):
        require(set(properties) <= {"number","suffix"},"Unknown note property")
        number = int(properties.get("number",1+sum(1 for n in pkg.sections for _ in pkg.tree(n).iter(q("hp:"+kind)))))
        require(number > 0,"Note number must be positive")
        node = E.Element(q("hp:"+kind),number=str(number),suffixChar=str(properties.get("suffix",41)),instId=pkg.new_id("hp:"+kind,"instId"))
        sublist(pkg,node,text,p)
    elif kind == "bookmark":
        require(bool(name),"Bookmark name is required")
        require(not any(n.get("name") == name for s in pkg.sections for n in pkg.tree(s).iter(q("hp:bookmark"))),"Duplicate bookmark name")
        node = E.Element(q("hp:bookmark"),name=name)
    elif kind == "field":
        require(bool(name),"Field name is required")
        field_type = properties.get("type","CLICK_HERE")
        require(field_type in {"CLICK_HERE","DATE","DOC_DATE","PATH","BOOKMARK","MAILMERGE","CROSSREF","FORMULA","SUMMERY","USER_INFO","HYPERLINK"},"Unsupported field type")
        ident = pkg.new_id("hp:fieldBegin")
        begin = E.Element(q("hp:fieldBegin"),id=ident,type=field_type,name=name,editable="1",dirty="0",fieldid=ident)
        params = E.SubElement(begin,q("hp:parameters"),cnt="2",name="")
        E.SubElement(params,q("hp:integerParam"),name="Prop").text = "0"
        E.SubElement(params,q("hp:stringParam"),name="Command").text = str(properties.get("command",""))
        section,node = append_control(pkg,target,begin)
        run = begin.getparent().getparent()
        t = run.find(q("hp:t"))
        write_text(t,text)
        E.SubElement(E.SubElement(run,q("hp:ctrl")),q("hp:fieldEnd"),beginIDRef=ident,fieldid=ident)
        return {"target":pkg.address(section,begin)}
    elif kind == "equation":
        require(set(properties) <= {"size","color","width","height"},"Unknown equation property")
        node = E.Element(q("hp:equation"),id=pkg.new_id("hp:equation"),zOrder="0",numberingType="EQUATION",
                         textWrap="SQUARE",textFlow="BOTH_SIDES",lock="0",dropcapstyle="None",version="Equation Version 60",
                         baseLine="85",textColor=color(properties.get("color","#000000")),baseUnit=str(round(positive(properties.get("size",10),"equation size")*100)),lineMode="CHAR",font="HYhwpEQ")
        E.SubElement(node,q("hp:script")).text = text
        E.SubElement(node,q("hp:sz"),width=str(mm(properties.get("width",30))),widthRelTo="ABSOLUTE",height=str(mm(properties.get("height",10))),heightRelTo="ABSOLUTE")
        E.SubElement(node,q("hp:pos"),treatAsChar="1",affectLSpacing="0",flowWithText="1",allowOverlap="0",holdAnchorAndSO="0",vertRelTo="PARA",horzRelTo="PARA",vertAlign="TOP",horzAlign="LEFT",vertOffset="0",horzOffset="0")
        E.SubElement(node,q("hp:outMargin"),left="0",right="0",top="0",bottom="0")
        # Equations, like pictures/tables, are direct run children rather than ctrl children.
        section,p = pkg.target(target,"hp:p")
        E.SubElement(p,q("hp:run"),charPrIDRef="0").append(node)
        pkg.mark(section)
        return {"target":pkg.address(section,node)}
    else:
        raise HwpxError(f"Control creation not implemented: {kind}")
    section,node = append_control(pkg,target,node)
    return {"target":pkg.address(section,node)}


def control_edit(pkg,target,action,text=None,name=None,properties=None):
    section,node = pkg.target(target)
    kind = local_name(node)
    allowed = {"header","footer","footNote","endNote","bookmark","fieldBegin","equation"}
    require(kind in allowed,"Unsupported control type")
    if action == "delete":
        if kind == "fieldBegin":
            ident = node.get("id")
            ends = [n for s in pkg.sections for n in pkg.tree(s).iter(q("hp:fieldEnd")) if n.get("beginIDRef") == ident]
            require(len(ends) == 1,"Field end is missing or ambiguous")
            for end in ends:
                end.getparent().remove(end)
        node.getparent().remove(node)
    elif action == "rename":
        require(kind in ("bookmark","fieldBegin") and bool(name),"Rename requires a bookmark/field and a name")
        require(not any(n is not node and n.get("name") == name for s in pkg.sections for n in pkg.tree(s).iter(node.tag)),"Duplicate name")
        node.set("name",name)
    elif action == "set":
        if kind == "equation":
            if text is not None:
                node.find(q("hp:script")).text = text
            for key,value in (properties or {}).items():
                require(key in ("size","color","baseline","font"),"Unknown equation property")
                attr = {"size":"baseUnit","color":"textColor","baseline":"baseLine","font":"font"}[key]
                node.set(attr,str(round(positive(value,"equation size")*100)) if key == "size" else color(value) if key == "color" else str(value))
        elif kind == "fieldBegin":
            run = node.getparent().getparent()
            ident = node.get("id")
            require(node.getparent().tag == q("hp:ctrl") and run.tag == q("hp:run"),"Unsupported field layout")
            children = list(run)
            start = children.index(node.getparent())
            end = next((i for i,c in enumerate(children) if i > start and any(e.get("beginIDRef") == ident for e in c.iter(q("hp:fieldEnd")))),None)
            require(end is not None,"Field value update currently requires same-run begin/end")
            require(all(c.tag == q("hp:t") for c in children[start+1:end]),"Nested field/control value update requires richer span handling")
            for c in children[start+1:end]:
                run.remove(c)
            t = E.Element(q("hp:t"))
            write_text(t,text or "")
            run.insert(start+1,t)
        else:
            raise HwpxError("Edit nested paragraphs using their inspect target addresses")
    else:
        raise HwpxError("Unknown control action")
    pkg.mark(section)
    return 1


def styles(pkg,action,ident=None,name=None,target=None,replacement=None,properties=None):
    root = pkg.tree(HEADER).find(".//"+q("hh:styles"))
    require(root is not None,"Missing styles")
    if action == "list":
        return [dict(n.attrib) for n in root]
    node = next((n for n in root if n.get("id") == str(ident)),None)
    if action == "create":
        require(bool(name) and not any(n.get("name") == name for n in root),"Empty or duplicate style name")
        require(node is not None,"Base style ID is required")
        node = deepcopy(node)
        node.set("id",str(max(int(n.get("id")) for n in root)+1))
        node.set("name",name)
        node.set("engName",name)
        root.append(node)
    else:
        require(node is not None,"Unknown style ID")
        if action == "rename":
            require(bool(name) and not any(n is not node and n.get("name") == name for n in root),"Empty or duplicate style name")
            node.set("name",name)
        elif action == "apply":
            section,p = pkg.target(target,"hp:p")
            p.set("styleIDRef",str(ident))
            p.set("paraPrIDRef",node.get("paraPrIDRef"))
            for r in p.findall(q("hp:run")):
                r.set("charPrIDRef",node.get("charPrIDRef"))
            pkg.mark(section)
        elif action == "update":
            allowed = {"charPrIDRef":"charPr","paraPrIDRef":"paraPr","nextStyleIDRef":"style"}
            require(bool(properties) and set(properties) <= set(allowed),"Style update requires valid reference properties")
            for attr,value in properties.items():
                require(any(n.get("id") == str(value) for n in pkg.tree(HEADER).iter(q("hh:"+allowed[attr]))),"Unknown style reference")
                node.set(attr,str(value))
        elif action == "delete":
            alternative = next((n for n in root if n.get("id") == str(replacement)),None)
            require(alternative is not None and alternative is not node,"Specify a different replacement style")
            for n in root:
                if n.get("nextStyleIDRef") == str(ident):
                    n.set("nextStyleIDRef",str(replacement))
            for section in pkg.sections:
                for p in pkg.tree(section).iter(q("hp:p")):
                    if p.get("styleIDRef") == str(ident):
                        p.set("styleIDRef",str(replacement))
                        pkg.mark(section)
            root.remove(node)
        else:
            raise HwpxError("Unknown style action")
    root.set("itemCnt",str(len(root)))
    pkg.mark(HEADER)
    return dict(node.attrib)
