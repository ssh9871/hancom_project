"""Rectangle creation and conservative edits to supported drawing properties."""

from lxml import etree as E

from .controls import sublist
from .editing import color, mm, require
from .images import picture_new
from .package import HwpxError, q


def shape_create(pkg,target,width=40,height=20,text="",fill="#FFFFFF",stroke="#000000"):
    name,p = pkg.target(target,"hp:p")
    node = picture_new(pkg)
    node.tag = q("hp:rect")
    ident = pkg.new_id("hp:rect")
    node.set("id",ident);node.set("instid",ident);node.set("ratio","0")
    w,h = mm(width),mm(height)
    for child in list(node):
        if child.tag in {q("hp:imgRect"),q("hp:imgClip"),q("hp:imgDim"),q("hp:inMargin"),q("hc:img"),q("hp:effects")}:
            node.remove(child)
    for tag in ("orgSz","curSz","sz"):
        node.find(q("hp:"+tag)).attrib.update({"width":str(w),"height":str(h)})
    index = node.index(node.find(q("hp:sz")))
    line = E.Element(q("hp:lineShape"),color=color(stroke),width="75",style="SOLID",endCap="FLAT",headStyle="NORMAL",tailStyle="NORMAL",headfill="0",tailfill="0",headSz="SMALL_SMALL",tailSz="SMALL_SMALL",outlineStyle="NORMAL",alpha="0")
    node.insert(index,line);index+=1
    brush = E.Element(q("hc:fillBrush"))
    E.SubElement(brush,q("hc:winBrush"),faceColor=color(fill),hatchColor="#000000",alpha="0")
    node.insert(index,brush);index+=1
    shadow = E.Element(q("hp:shadow"),type="NONE",color="#B2B2B2",offsetX="0",offsetY="0",alpha="0")
    node.insert(index,shadow);index+=1
    if text:
        draw = E.Element(q("hp:drawText"),lastWidth=str(w),name="",editable="0")
        sublist(pkg,draw,text,p)
        E.SubElement(draw,q("hp:textMargin"),left="0",right="0",top="0",bottom="0")
        node.insert(index,draw);index+=1
    for i,(x,y) in enumerate(((0,0),(w,0),(w,h),(0,h))):
        node.insert(index,E.Element(q("hc:pt"+str(i)),x=str(x),y=str(y)));index+=1
    E.SubElement(p,q("hp:run"),charPrIDRef="0").append(node)
    pkg.mark(name)
    return {"target":pkg.address(name,node)}


def shape_edit(pkg,target,action,properties=None):
    name,node = pkg.target(target)
    require(node.tag in {q("hp:rect"),q("hp:line"),q("hp:ellipse"),q("hp:polygon"),q("hp:container")},"Expected drawing shape")
    if action == "delete":node.getparent().remove(node)
    elif action == "set":
        props = properties or {}
        require(set(props) <= {"x","y","z","fill","stroke","inline","locked"},"Unsupported drawing property")
        for key,attr in (("z","zOrder"),("locked","lock")):
            if key in props:
                if key == "locked":require(isinstance(props[key],bool),"locked must be boolean")
                else:require(int(props[key]) >= 0,"z must be nonnegative")
                node.set(attr,str(int(props[key])))
        pos = node.find(q("hp:pos"))
        for key,attr in (("x","horzOffset"),("y","vertOffset")):
            if key in props:
                require(pos is not None,"Drawing has no position element")
                pos.set(attr,str(round(float(props[key])*7200/25.4)))
        if "inline" in props:
            require(pos is not None and isinstance(props["inline"],bool),"inline needs a boolean and a position")
            pos.set("treatAsChar","1" if props["inline"] else "0")
        if "fill" in props:
            brush = node.find(".//"+q("hc:winBrush"));require(brush is not None,"Only solid existing fills can be changed")
            brush.set("faceColor",color(props["fill"]))
        if "stroke" in props:
            line = node.find(q("hp:lineShape"));require(line is not None,"Missing lineShape")
            line.set("color",color(props["stroke"]))
    else:raise HwpxError("Drawing action is not implemented")
    pkg.mark(name)
    return 1
