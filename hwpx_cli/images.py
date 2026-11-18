from copy import deepcopy
from io import BytesIO
from pathlib import Path
import math

from lxml import etree as E
from PIL import Image, UnidentifiedImageError

from .editing import mm, require
from .package import CONTENT, MAX_ENTRY, NS, HwpxError, q


def image_resource(pkg, path):
    with Path(path).open("rb") as f:
        data = f.read(MAX_ENTRY+1)
    require(len(data) <= MAX_ENTRY,"Image exceeds entry limit")
    try:
        with Image.open(BytesIO(data)) as image:
            width,height = image.size
            fmt = image.format
            require(width > 0 and height > 0 and width*height <= 100000000,"Image dimensions exceed limits")
            image.verify()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
        raise HwpxError("Invalid image") from exc
    formats = {"PNG":("png","image/png"),"JPEG":("jpg","image/jpeg"),"WEBP":("webp","image/webp"),"GIF":("gif","image/gif"),"BMP":("bmp","image/bmp"),"TIFF":("tif","image/tiff")}
    require(fmt in formats,"Unsupported image format")
    extension,mime = formats[fmt]
    i = 1
    while f"image{i}" in pkg.items or f"BinData/image{i}.{extension}" in pkg.parts:
        i += 1
    ident,href = f"image{i}",f"BinData/image{i}.{extension}"
    pkg.parts[href] = data
    pkg.items[ident] = href
    manifest = pkg.tree(CONTENT).find(q("opf:manifest"))
    E.SubElement(manifest,q("opf:item"),id=ident,href=href,isEmbeded="1",**{"media-type":mime})
    pkg.mark(CONTENT)
    return ident,width,height


def picture_new(pkg):
    ident = pkg.new_id("hp:pic")
    p = E.Element(q("hp:pic"),id=ident,zOrder="0",numberingType="PICTURE",textWrap="SQUARE",textFlow="BOTH_SIDES",
                  lock="0",dropcapstyle="None",href="",groupLevel="0",instid=ident,reverse="0")
    E.SubElement(p,q("hp:offset"),x="0",y="0")
    for tag in ("orgSz","curSz"):
        E.SubElement(p,q("hp:"+tag),width="1",height="1")
    E.SubElement(p,q("hp:flip"),horizontal="0",vertical="0")
    E.SubElement(p,q("hp:rotationInfo"),angle="0",centerX="0",centerY="0",rotateimage="1")
    info = E.SubElement(p,q("hp:renderingInfo"))
    for tag in ("transMatrix","scaMatrix","rotMatrix"):
        E.SubElement(info,q("hc:"+tag),e1="1",e2="0",e3="0",e4="0",e5="1",e6="0")
    rect = E.SubElement(p,q("hp:imgRect"))
    for i in range(4):
        E.SubElement(rect,q("hc:pt"+str(i)),x="0",y="0")
    for tag in ("imgClip","inMargin"):
        E.SubElement(p,q("hp:"+tag),left="0",right="0",top="0",bottom="0")
    E.SubElement(p,q("hp:imgDim"),dimwidth="1",dimheight="1")
    E.SubElement(p,q("hc:img"),binaryItemIDRef="",bright="0",contrast="0",effect="REAL_PIC",alpha="0")
    E.SubElement(p,q("hp:effects"))
    E.SubElement(p,q("hp:sz"),width="1",widthRelTo="ABSOLUTE",height="1",heightRelTo="ABSOLUTE",protect="0")
    E.SubElement(p,q("hp:pos"),treatAsChar="1",affectLSpacing="1",flowWithText="1",allowOverlap="0",holdAnchorAndSO="0",
                 vertRelTo="PARA",horzRelTo="PARA",vertAlign="TOP",horzAlign="LEFT",vertOffset="0",horzOffset="0")
    E.SubElement(p,q("hp:outMargin"),left="0",right="0",top="0",bottom="0")
    E.SubElement(p,q("hp:shapeComment"))
    return p


def picture_edit(pkg,target,op,properties=None,path=None):
    require(op in ("insert","replace","set","delete"),"Unknown picture operation")
    name,node = pkg.target(target,"hp:p" if op == "insert" else "hp:pic")
    properties = properties or {}
    allowed = {"width","height","rotation","inline","x","y","brightness","contrast","crop-left","crop-right","crop-top","crop-bottom"}
    require(set(properties) <= allowed,"Unknown picture property")
    if op == "delete":
        node.getparent().remove(node)
        pkg.mark(name)
        return 1
    if op == "insert":
        picture = picture_new(pkg)
        run = E.SubElement(node,q("hp:run"),charPrIDRef="0")
        run.append(picture)
        E.SubElement(run,q("hp:t"))
    else:
        picture = node
    if op in ("insert","replace"):
        require(path is not None,"Image file is required")
        ident,w,h = image_resource(pkg,path)
        picture.find(q("hc:img")).set("binaryItemIDRef",ident)
        ow,oh = w*75,h*75
        picture.find(q("hp:orgSz")).attrib.update({"width":str(ow),"height":str(oh)})
        picture.find(q("hp:imgDim")).attrib.update({"dimwidth":str(w),"dimheight":str(h)})
        for point,(x,y) in zip(picture.find(q("hp:imgRect")),((0,0),(ow,0),(ow,oh),(0,oh))):
            point.attrib.update({"x":str(x),"y":str(y)})
        # imgClip uses imgDim's source coordinate plane, not orgSz's HWP units.
        picture.find(q("hp:imgClip")).attrib.update({"left":"0","top":"0","right":str(w),"bottom":str(h)})
        picture.find(q("hp:shapeComment")).text = Path(path).name
        if op == "insert":
            properties = {"width":w*25.4/96,"height":h*25.4/96,**properties}
    rotation = picture.find(q("hp:rotationInfo"))
    if op in ("insert","replace") or properties.keys() & {"width","height"}:
        original = picture.find(q("hp:orgSz"))
        size = picture.find(q("hp:sz"))
        current = picture.find(q("hp:curSz"))
        scale = picture.find("hp:renderingInfo/hc:scaMatrix",NS)
        for axis, coefficient in (("width","e1"),("height","e5")):
            if op == "set" and axis not in properties:
                continue
            length = mm(properties[axis]) if axis in properties else int(size.get(axis))
            original_length = int(original.get(axis))
            require(length > 0 and original_length > 0,"Invalid picture dimensions")
            size.set(axis,str(length))
            current.set(axis,str(length))
            scale.set(coefficient,str(length/original_length))
        if op in ("insert","replace"):
            rotation.attrib.update({"centerX":str(int(original.get("width"))//2),"centerY":str(int(original.get("height"))//2)})
    if "rotation" in properties:
        angle = float(properties["rotation"])
        require(math.isfinite(angle),"Invalid rotation")
        rotation.set("angle",str(angle%360))
        rad = math.radians(angle)
        matrix = picture.find(".//"+q("hc:rotMatrix"))
        matrix.attrib.update({"e1":str(math.cos(rad)),"e2":str(-math.sin(rad)),"e4":str(math.sin(rad)),"e5":str(math.cos(rad))})
    pos = picture.find(q("hp:pos"))
    if "inline" in properties:
        require(isinstance(properties["inline"],bool),"inline must be boolean")
        pos.set("treatAsChar","1" if properties["inline"] else "0")
    for key,attr in (("x","horzOffset"),("y","vertOffset")):
        if key in properties:
            pos.set(attr,str(round(float(properties[key])*7200/25.4)))
    for key,attr in (("brightness","bright"),("contrast","contrast")):
        if key in properties:
            value = int(properties[key])
            require(-100 <= value <= 100,"Brightness/contrast must be -100..100")
            picture.find(q("hc:img")).set(attr,str(value))
    for key in ("left","right","top","bottom"):
        if "crop-"+key in properties:
            value = int(properties["crop-"+key])
            require(value >= 0,"Crop coordinates must be nonnegative imgDim source coordinates")
            picture.find(q("hp:imgClip")).set(key,str(value))
    clip = picture.find(q("hp:imgClip"))
    dim = picture.find(q("hp:imgDim"))
    if op in ("insert","replace") or any(k.startswith("crop-") for k in properties):
        require(0 <= int(clip.get("left")) < int(clip.get("right")) <= int(dim.get("dimwidth"))
                and 0 <= int(clip.get("top")) < int(clip.get("bottom")) <= int(dim.get("dimheight")),"Crop rectangle exceeds imgDim source bounds")
    pkg.mark(name)
    return {"target":pkg.address(name,picture)}
