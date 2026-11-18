from lxml import etree as E

from .editing import clone_definition,require
from .package import HEADER,q


def apply_numbering(pkg,target,kind="number",ident=None,level=0,start=1,character="•",pattern=None):
    name,p = pkg.target(target,"hp:p")
    require(kind in ("number","bullet","none"),"Numbering kind must be number/bullet/none")
    require(0 <= level < 7 and start > 0,"Invalid numbering level/start")
    head = pkg.tree(HEADER)
    if kind != "none":
        collection,tag = ("numberings","numbering") if kind == "number" else ("bullets","bullet")
        root = head.find(".//"+q("hh:"+collection))
        if root is None:
            root = E.Element(q("hh:"+collection),itemCnt="0")
            refs = head.find(q("hh:refList"))
            # Both collections precede paraProperties in the header schema.
            next_collection = refs.find(q("hh:bullets")) if kind == "number" else None
            if next_collection is None:next_collection = refs.find(q("hh:paraProperties"))
            refs.insert(refs.index(next_collection),root)
        if ident is None:
            ident = str(max((int(n.get("id")) for n in root),default=0)+1)
            if kind == "number":
                node = E.SubElement(root,q("hh:numbering"),id=ident,start=str(start))
                for i in range(1,8):
                    child = E.SubElement(node,q("hh:paraHead"),start=str(start),level=str(i),align="LEFT",useInstWidth="1",autoIndent="1",
                                         widthAdjust="0",textOffsetType="PERCENT",textOffset="50",numFormat="DIGIT",charPrIDRef="0",checkable="0")
                    child.text = pattern if pattern is not None else f"^{i}."
            else:
                require(isinstance(character,str) and len(character) == 1,"Bullet must be one Unicode character")
                node = E.SubElement(root,q("hh:bullet"),id=ident,char=character,useImage="0")
                E.SubElement(node,q("hh:paraHead"),level="0",align="LEFT",useInstWidth="1",autoIndent="1",widthAdjust="0",
                             textOffsetType="PERCENT",textOffset="50",numFormat="DIGIT",charPrIDRef="0",checkable="0")
            root.set("itemCnt",str(len(root)))
        else:
            require(any(n.get("id") == str(ident) for n in root),"Unknown numbering/bullet ID")
    definition = clone_definition(pkg,"paraProperties",p.get("paraPrIDRef"))
    heading = definition.find(q("hh:heading"))
    require(heading is not None,"Missing paragraph heading")
    heading.attrib.update({"type":{"number":"NUMBER","bullet":"BULLET","none":"NONE"}[kind],"idRef":str(ident or 0),"level":str(level)})
    p.set("paraPrIDRef",definition.get("id"))
    pkg.mark(name);pkg.mark(HEADER)
    return {"id":ident,"kind":kind}
