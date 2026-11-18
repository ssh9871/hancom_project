from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from hwpx_cli.creation import create_blank
from hwpx_cli.editing import replace_range, replace_all, format_text
from hwpx_cli.images import picture_edit
from hwpx_cli.package import Package, HwpxError, q, text_of, xml
from hwpx_cli.storage import save, history
from hwpx_cli.tables import create_table, table_edit, grid

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "test.hwpx"
CAMPAIGN = next(FIXTURE.parent.glob("*환경캠페인.hwpx"))
CAMPAIGN_TABLE = "Contents/section0.xml#1/0/3/4/0/0/6/0/0"


class EditorTests(unittest.TestCase):
    def test_manifest_script_in_spine_is_preserved(self):
        original = Package(CAMPAIGN.read_bytes())
        self.assertEqual(original.sections, ["Contents/section0.xml"])
        script = "Scripts/headerScripts.js"
        replace_all(original, "20명", "24명")
        saved = Package(original.bytes())
        self.assertEqual(saved.parts[script], original.parts[script])

    def test_campaign_table_border_and_width_preserve_other_geometry(self):
        p = Package(CAMPAIGN.read_bytes())
        table = p.target(CAMPAIGN_TABLE)[1]
        _, _, cells, _ = grid(table)
        original = deepcopy(table)
        size = table.find(q("hp:sz"))
        height = size.get("height")
        table_edit(p, CAMPAIGN_TABLE, "border", properties={"type": "DASH", "width": 0.4, "color": "#B52222"})
        self.assertEqual(dict(size.attrib), dict(original.find(q("hp:sz")).attrib))
        before_cells = list(original.iter(q("hp:tc")))
        fills = p.tree("Contents/header.xml").find(".//" + q("hh:borderFills"))
        for before, (_, _, _, _, after) in zip(before_cells, cells):
            self.assertEqual(dict(after.find(q("hp:cellSz")).attrib), dict(before.find(q("hp:cellSz")).attrib))
            definition = fills.find(f"*[@id='{after.get('borderFillIDRef')}']")
            self.assertEqual(definition.find(q("hh:topBorder")).get("color"), "#B52222")
        table_edit(p, CAMPAIGN_TABLE, "resize", width=150)
        self.assertEqual(size.get("width"), "42520")
        self.assertEqual(size.get("height"), height)
        for before, (_, _, _, _, after) in zip(before_cells, cells):
            self.assertEqual(after.find(q("hp:cellSz")).get("height"), before.find(q("hp:cellSz")).get("height"))
        Package(p.bytes()).validate()
        with self.assertRaises(HwpxError):
            table_edit(p, CAMPAIGN_TABLE, "resize", width=0.001)
        with self.assertRaises(HwpxError):
            create_table(p, "Contents/section0.xml#0", 1, 3, width=0.001)

    def test_campaign_picture_brightness_and_width_preserve_other_geometry(self):
        p = Package(CAMPAIGN.read_bytes())
        target = CAMPAIGN_TABLE + "/5/2/0/0/0/0"
        picture = p.target(target)[1]
        before = deepcopy(picture)
        picture_edit(p, target, "set", {"brightness": 15})
        from lxml import etree as E
        for tag in ("sz", "curSz", "rotationInfo", "renderingInfo", "imgClip", "pos"):
            self.assertEqual(E.tostring(picture.find(q("hp:" + tag)), method="c14n", exclusive=True),
                             E.tostring(before.find(q("hp:" + tag)), method="c14n", exclusive=True))
        picture_edit(p, target, "set", {"width": 10})
        self.assertEqual(picture.find(q("hp:sz")).get("width"), "2835")
        for tag in ("sz", "curSz"):
            self.assertEqual(picture.find(q("hp:" + tag)).get("height"), before.find(q("hp:" + tag)).get("height"))
        self.assertEqual(picture.find(q("hc:img")).get("binaryItemIDRef"), "image9")
        Package(p.bytes()).validate()

    def test_inserted_tracks_keep_neighbor_border(self):
        p = self.blank()
        target = create_table(p, "Contents/section0.xml#0", 2, 2)["target"]
        table_edit(p, target, "border", properties={"type": "SOLID", "color": "#B52222"})
        for operation in ("insert-row", "insert-column"):
            table_edit(p, target, operation, index=2)
        _, _, cells, _ = grid(p.target(target)[1])
        self.assertEqual(len({cell.get("borderFillIDRef") for _, _, _, _, cell in cells}), 1)
        with self.assertRaises(HwpxError):
            table_edit(p, target, "insert-row", index=0, size=0.001)

    def blank(self,text=""):
        p = Package(create_blank())
        if text:
            replace_range(p,"Contents/section0.xml#0",0,0,text)
        return p

    def test_noop_exact_bytes(self):
        data = FIXTURE.read_bytes()
        self.assertEqual(Package(data).bytes(),data)

    def test_template_free_document(self):
        p = self.blank()
        self.assertEqual(p.validate(),{"valid":True,"sections":1})
        self.assertEqual(text_of(p.tree(p.sections[0])[0]),"")

    def test_range_across_runs_and_emoji_preservation(self):
        p = self.blank("A😀B\nC")
        node = p.tree(p.sections[0])[0]
        from lxml import etree as E
        r = E.SubElement(node,q("hp:run"),charPrIDRef="0")
        E.SubElement(r,q("hp:t")).text = "tail"
        replace_range(p,"Contents/section0.xml#0",1,7,"새\n값")
        after = Package(p.bytes())
        self.assertEqual(text_of(after.tree(after.sections[0])[0]),"A새\n값il")

    def test_unrelated_parts_preserved(self):
        p = Package(FIXTURE.read_bytes())
        old = dict(p.parts)
        replace_all(p,"남산","한라산")
        saved = Package(p.bytes())
        for name in old:
            if name not in p.dirty:
                self.assertEqual(old[name],saved.parts[name],name)
        self.assertIn("한라산",str(saved.inspect()))

    def test_shared_style_cloned(self):
        p = self.blank("abcdef")
        old = deepcopy(p.tree("Contents/header.xml"))
        format_text(p,"Contents/section0.xml#0",{"size":30,"bold":True,"color":"#0000ff"},1,3)
        after = Package(p.bytes())
        paragraph = after.tree(after.sections[0])[0]
        runs = [r for r in paragraph.findall(q("hp:run")) if r.find(q("hp:t")) is not None]
        self.assertEqual([text_of_run(r) for r in runs],["a","bc","def"])
        self.assertEqual(runs[0].get("charPrIDRef"),"0")
        self.assertNotEqual(runs[1].get("charPrIDRef"),"0")
        from lxml import etree as E
        self.assertEqual(E.tostring(old.find(".//"+q("hh:charPr"))),
                         E.tostring(after.tree("Contents/header.xml").find(".//"+q("hh:charPr"))))

    def test_grid_merge_insert_delete_transpose_split(self):
        p = self.blank()
        result = create_table(p,"Contents/section0.xml#0",2,3,[["a","b","c"],["d","e","f"]])
        target = result["target"]
        table_edit(p,target,"merge",row=0,column=0,end_row=1,end_column=1)
        table_edit(p,target,"insert-row",index=1)
        t = p.target(target)[1]
        self.assertEqual(grid(t)[0:2],(3,3))
        self.assertEqual(grid(t)[3][1,0][2],3)
        table_edit(p,target,"delete-column",index=2)
        table_edit(p,target,"transpose")
        self.assertEqual(grid(t)[0:2],(2,3))
        table_edit(p,target,"split-cell",row=0,column=0)
        self.assertEqual(len(grid(t)[2]),6)
        saved = Package(p.bytes())
        ids = [n.get("id") for n in saved.tree(saved.sections[0]).iter(q("hp:p"))]
        self.assertEqual(len(ids),len(set(ids)))
        with self.assertRaises(HwpxError):
            table_edit(p,target,"border",properties={"type":"INVALID"})
        with self.assertRaises(HwpxError):
            table_edit(p,target,"border",properties={"width":-1})

    def test_image_replacement_keeps_shared_resource(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"a.png"
            Image.new("RGB",(20,30),"red").save(path)
            p = self.blank()
            a = picture_edit(p,"Contents/section0.xml#0","insert",{"width":50},path)
            self.assertEqual(p.target(a["target"])[1].find(q("hp:sz")).get("height"), "2250")
            before = dict(p.parts)
            Image.new("RGB",(10,10),"blue").save(path)
            picture_edit(p,a["target"],"replace",path=path)
            after = Package(p.bytes())
            self.assertEqual(before["BinData/image1.png"],after.parts["BinData/image1.png"])
            self.assertIn("BinData/image2.png",after.parts)

    def test_atomic_save_history_branch_and_external_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"work.hwpx"
            first = create_blank()
            save(path,first)
            p = Package(first)
            replace_range(p,"Contents/section0.xml#0",0,0,"one")
            second = p.bytes()
            save(path,second,expected=p.version)
            history(path,"undo")
            self.assertEqual(path.read_bytes(),first)
            history(path,"redo")
            self.assertEqual(path.read_bytes(),second)
            history(path,"undo")
            p = Package(first)
            replace_range(p,"Contents/section0.xml#0",0,0,"two")
            save(path,p.bytes(),expected=p.version)
            with self.assertRaises(HwpxError):
                history(path,"redo")
            path.write_bytes(first)
            with self.assertRaises(HwpxError):
                history(path,"undo")

    def test_unsafe_input_and_invalid_edits_do_not_save(self):
        with self.assertRaises(HwpxError):
            xml(b'<!DOCTYPE x [<!ENTITY a "secret">]><x>&a;</x>')
        with self.assertRaises(HwpxError):
            Package(b"not zip")
        p = self.blank("abc")
        with self.assertRaises(HwpxError):
            replace_range(p,"Contents/section0.xml#0",0,99,"x")
        with self.assertRaises(HwpxError):
            p.target("Contents/section0.xml#-1")
        source = BytesIO(create_blank())
        with ZipFile(source,"a") as z:
            z.writestr("../escape.xml",b"<x/>")
        with self.assertRaises(HwpxError):
            Package(source.getvalue())


def text_of_run(run):
    p = deepcopy(run)
    from lxml import etree as E
    parent = E.Element(q("hp:p"))
    parent.append(p)
    return text_of(parent)


if __name__ == "__main__":
    unittest.main()
