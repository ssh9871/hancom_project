"""Create a standalone blank HWPX without reading a template document."""

from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

from lxml import etree as E
from PIL import Image

from .package import NS, Package, q


def create_blank():
    head = E.Element(q("hh:head"), nsmap=NS, version="1.2", secCnt="1")
    E.SubElement(head,q("hh:beginNum"),page="1",footnote="1",endnote="1",pic="1",tbl="1",equation="1")
    refs = E.SubElement(head,q("hh:refList"))
    faces = E.SubElement(refs,q("hh:fontfaces"),itemCnt="7")
    languages = ("HANGUL","LATIN","HANJA","JAPANESE","OTHER","SYMBOL","USER")
    for lang in languages:
        face = E.SubElement(faces,q("hh:fontface"),lang=lang,fontCnt="1")
        E.SubElement(face,q("hh:font"),id="0",face="Malgun Gothic",type="TTF",isEmbedded="0")
    borders = E.SubElement(refs,q("hh:borderFills"),itemCnt="1")
    b = E.SubElement(borders,q("hh:borderFill"),id="1",threeD="0",shadow="0",centerLine="NONE",breakCellSeparateLine="0")
    for tag in ("slash","backSlash"):
        E.SubElement(b,q("hh:"+tag),type="NONE",Crooked="0",isCounter="0")
    for side in ("leftBorder","rightBorder","topBorder","bottomBorder","diagonal"):
        E.SubElement(b,q("hh:"+side),type="NONE",width="0.1 mm",color="#000000")
    chars = E.SubElement(refs,q("hh:charProperties"),itemCnt="1")
    char = E.SubElement(chars,q("hh:charPr"),id="0",height="1000",textColor="#000000",shadeColor="none",
                        useFontSpace="0",useKerning="0",symMark="NONE",borderFillIDRef="1")
    for tag,value in (("fontRef","0"),("ratio","100"),("spacing","0"),("relSz","100"),("offset","0")):
        E.SubElement(char,q("hh:"+tag),**{lang.lower():value for lang in languages})
    E.SubElement(char,q("hh:underline"),type="NONE",shape="SOLID",color="#000000")
    E.SubElement(char,q("hh:strikeout"),shape="NONE",color="#000000")
    E.SubElement(char,q("hh:outline"),type="NONE")
    E.SubElement(char,q("hh:shadow"),type="NONE",color="#B2B2B2",offsetX="10",offsetY="10")
    tabs = E.SubElement(refs,q("hh:tabProperties"),itemCnt="1")
    E.SubElement(tabs,q("hh:tabPr"),id="0",autoTabLeft="0",autoTabRight="0")
    paras = E.SubElement(refs,q("hh:paraProperties"),itemCnt="1")
    para = E.SubElement(paras,q("hh:paraPr"),id="0",tabPrIDRef="0",condense="0",fontLineHeight="0",
                        snapToGrid="1",suppressLineNumbers="0",checked="0")
    E.SubElement(para,q("hh:align"),horizontal="LEFT",vertical="BASELINE")
    E.SubElement(para,q("hh:heading"),type="NONE",idRef="0",level="0")
    E.SubElement(para,q("hh:breakSetting"),breakLatinWord="KEEP_WORD",breakNonLatinWord="KEEP_WORD",
                 widowOrphan="0",keepWithNext="0",keepLines="0",pageBreakBefore="0",lineWrap="BREAK")
    E.SubElement(para,q("hh:autoSpacing"),eAsianEng="0",eAsianNum="0")
    margin = E.SubElement(para,q("hh:margin"))
    for tag in ("intent","left","right","prev","next"):
        E.SubElement(margin,q("hc:"+tag),value="0",unit="HWPUNIT")
    E.SubElement(para,q("hh:lineSpacing"),type="PERCENT",value="160",unit="HWPUNIT")
    E.SubElement(para,q("hh:border"),borderFillIDRef="1",offsetLeft="0",offsetRight="0",offsetTop="0",offsetBottom="0",connect="0",ignoreMargin="0")
    styles = E.SubElement(refs,q("hh:styles"),itemCnt="1")
    E.SubElement(styles,q("hh:style"),id="0",type="PARA",name="Normal",engName="Normal",paraPrIDRef="0",charPrIDRef="0",nextStyleIDRef="0",langID="1042",lockForm="0")
    section = E.Element(q("hs:sec"),nsmap=NS)
    p = E.SubElement(section,q("hp:p"),id="0",paraPrIDRef="0",styleIDRef="0",pageBreak="0",columnBreak="0",merged="0")
    run = E.SubElement(p,q("hp:run"),charPrIDRef="0")
    sec = E.SubElement(run,q("hp:secPr"),id="",textDirection="HORIZONTAL",spaceColumns="1134",tabStop="8000",
                       tabStopVal="4000",tabStopUnit="HWPUNIT",outlineShapeIDRef="0",memoShapeIDRef="0",textVerticalWidthHead="0",masterPageCnt="0")
    E.SubElement(sec,q("hp:grid"),lineGrid="0",charGrid="0",wonggojiFormat="0")
    E.SubElement(sec,q("hp:startNum"),pageStartsOn="BOTH",page="0",pic="0",tbl="0",equation="0")
    E.SubElement(sec,q("hp:visibility"),hideFirstHeader="0",hideFirstFooter="0",hideFirstMasterPage="0",border="SHOW_ALL",fill="SHOW_ALL",hideFirstPageNum="0",hideFirstEmptyLine="0",showLineNumber="0")
    E.SubElement(sec,q("hp:lineNumberShape"),restartType="0",countBy="0",distance="0",startNumber="0")
    page = E.SubElement(sec,q("hp:pagePr"),landscape="WIDELY",width="59528",height="84186",gutterType="LEFT_ONLY")
    E.SubElement(page,q("hp:margin"),header="4252",footer="4252",gutter="0",left="8504",right="8504",top="5668",bottom="4252")
    for tag,place in (("footNotePr","EACH_COLUMN"),("endNotePr","END_OF_DOCUMENT")):
        note = E.SubElement(sec,q("hp:"+tag))
        E.SubElement(note,q("hp:autoNumFormat"),type="DIGIT",userChar="",prefixChar="",suffixChar=")",supscript="0")
        E.SubElement(note,q("hp:noteLine"),length="-1",type="SOLID",width="0.12 mm",color="#000000")
        E.SubElement(note,q("hp:noteSpacing"),betweenNotes="283",belowLine="567",aboveLine="850")
        E.SubElement(note,q("hp:numbering"),type="CONTINUOUS",newNum="1")
        E.SubElement(note,q("hp:placement"),place=place,beneathText="0")
    for kind in ("BOTH","EVEN","ODD"):
        border = E.SubElement(sec,q("hp:pageBorderFill"),type=kind,borderFillIDRef="1",textBorder="PAPER",headerInside="0",footerInside="0",fillArea="PAPER")
        E.SubElement(border,q("hp:offset"),left="1417",right="1417",top="1417",bottom="1417")
    E.SubElement(E.SubElement(run,q("hp:ctrl")),q("hp:colPr"),id="",type="NEWSPAPER",layout="LEFT",colCount="1",sameSz="1",sameGap="0")
    E.SubElement(E.SubElement(p,q("hp:run"),charPrIDRef="0"),q("hp:t"))
    content = E.Element(q("opf:package"),nsmap=NS,version="",id="")
    E.SubElement(content,q("opf:metadata"))
    manifest = E.SubElement(content,q("opf:manifest"))
    for ident,href in (("header","Contents/header.xml"),("section0","Contents/section0.xml"),("settings","settings.xml")):
        E.SubElement(manifest,q("opf:item"),id=ident,href=href,**{"media-type":"application/xml"})
    spine = E.SubElement(content,q("opf:spine"))
    for ident in ("header","section0"):
        E.SubElement(spine,q("opf:itemref"),idref=ident,linear="yes")
    def payload(root):
        return E.tostring(root,encoding="UTF-8",xml_declaration=True)
    png = BytesIO()
    Image.new("RGB",(1,1),"white").save(png,format="PNG")
    parts = {
        "mimetype":b"application/hwp+zip",
        "version.xml":b'<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="0" buildNumber="1" os="1" xmlVersion="1.5" application="hwpx-cli" appVersion="0.1.0"/>',
        "Contents/header.xml":payload(head),"Contents/section0.xml":payload(section),"Contents/content.hpf":payload(content),
        "settings.xml":b'<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"/>',
        "META-INF/container.xml":b'<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container"><ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/></ocf:rootfiles></ocf:container>',
        "META-INF/container.rdf":b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>',
        "META-INF/manifest.xml":b'<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>',
        "Preview/PrvText.txt":b"", "Preview/PrvImage.png":png.getvalue(),
    }
    result = BytesIO()
    with ZipFile(result,"w") as z:
        for name,data in parts.items():
            z.writestr(name,data,compress_type=ZIP_STORED if name == "mimetype" else ZIP_DEFLATED)
    Package(result.getvalue()).validate()
    return result.getvalue()
