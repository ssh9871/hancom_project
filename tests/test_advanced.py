from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hwpx_cli.calculation import evaluate
from hwpx_cli.controls import control_create, control_edit, styles
from hwpx_cli.clipboard import copy_node,paste_html
from hwpx_cli.shapes import shape_create,shape_edit
from hwpx_cli.numbering import apply_numbering
from hwpx_cli.creation import create_blank
from hwpx_cli.crypto import encrypt,decrypt,is_encrypted
from hwpx_cli.editing import replace_range
from hwpx_cli.package import Package,HwpxError,q,text_of
from hwpx_cli.storage import save,history
from hwpx_cli.tables import create_table,table_edit,grid


class AdvancedTests(unittest.TestCase):
    def test_subdivide_cell_preserves_neighbors_and_numbering(self):
        p = Package(create_blank());root="Contents/section0.xml#0"
        table = create_table(p,root,2,2,[["a","b"],["c","d"]])["target"]
        table_edit(p,table,"split-cell",row=0,column=0,rows=2,columns=3)
        rows,cols,specs,occupied=grid(p.target(table)[1])
        self.assertEqual((rows,cols),(3,4))
        self.assertEqual(occupied[0,3][2],2)
        self.assertEqual(occupied[2,0][3],3)
        first=apply_numbering(p,root,kind="bullet")
        second=apply_numbering(p,root,kind="number",start=5)
        self.assertEqual(first["id"],"1")
        self.assertEqual(second["id"],"1")
        Package(p.bytes()).validate()

    def test_clipboard_html_and_drawing(self):
        p = Package(create_blank());root="Contents/section0.xml#0"
        paste_html(p,root,"<p>Hello <b>world</b><br>한글</p><p>Second</p>")
        address = next(e["target"] for e in p.inspect()["elements"] if e.get("text","").startswith("Hello"))
        copy_node(p,address,root)
        rect = shape_create(p,root,text="Box",fill="#112233")
        shape_edit(p,rect["target"],"set",{"x":10,"y":20,"z":2,"fill":"#223344"})
        saved = Package(p.bytes())
        self.assertEqual(sum(e.get("text","").startswith("Hello") for e in saved.inspect()["elements"]),2)
        with self.assertRaises(HwpxError):paste_html(p,root,'<script>alert(1)</script>')
        with self.assertRaises(HwpxError):paste_html(p,root,'<img src="file:///secret">')

    def test_encryption_roundtrip_wrong_password_and_history(self):
        plain = create_blank()
        cipher = encrypt(plain,"test-only-password")
        self.assertTrue(is_encrypted(cipher))
        before,after = Package(plain),Package(decrypt(cipher,"test-only-password"))
        for n in before.parts:
            if n != "META-INF/manifest.xml":
                self.assertEqual(before.parts[n],after.parts[n])
        with self.assertRaises(HwpxError):
            decrypt(cipher,"wrong")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"secret.hwpx"
            save(path,cipher,password="test-only-password")
            replace_range(after,"Contents/section0.xml#0",0,0,"secret text")
            new = encrypt(after.bytes(),"test-only-password")
            save(path,new,expected=__import__('hashlib').sha256(cipher).hexdigest(),password="test-only-password")
            history(path,"undo",password="test-only-password")
            self.assertEqual(path.read_bytes(),cipher)
            history(path,"redo",password="test-only-password")
            self.assertEqual(path.read_bytes(),new)

    def test_controls_and_styles_preserve_nested_text(self):
        p = Package(create_blank())
        root = "Contents/section0.xml#0"
        for kind in ("header","footer","footNote","endNote"):
            a = control_create(p,root,kind,"Nested")
            self.assertIn("Nested","".join(p.target(a["target"])[1].itertext()))
        a = control_create(p,root,"field","First",name="customer")
        control_edit(p,a["target"],"set",text="Second")
        self.assertIn("Second",text_of(p.tree(p.sections[0])[0]))
        b = control_create(p,root,"bookmark",name="anchor")
        control_edit(p,b["target"],"rename",name="renamed")
        control_create(p,root,"equation","a over b")
        style = styles(p,"create",ident=0,name="Heading")
        styles(p,"apply",ident=style["id"],target=root)
        saved = Package(p.bytes())
        self.assertEqual(len([e for e in saved.inspect()["elements"] if e["kind"] == "p"]),5)

    def test_formulas_ranges_directions_and_invalid_input(self):
        p = Package(create_blank())
        target = create_table(p,"Contents/section0.xml#0",2,3,[["1,000","2",""],["3","4",""]])["target"]
        self.assertEqual(evaluate(p,target,"=SUM(A1:B2)")["result"],1009)
        self.assertEqual(evaluate(p,target,"SUM(LEFT)",row=0,column=2)["result"],1002)
        self.assertEqual(evaluate(p,target,"IF(1,ROUND(-2.5),1/0)")["result"],-3)
        evaluate(p,target,"SUM(A1:B2)",row=1,column=2,write=True)
        self.assertEqual(text_of(grid(p.target(target)[1])[3][1,2][4].find(".//"+q("hp:p"))),"1009")
        for value in ("1/0","__import__('os')","A1.__class__","2**999999","SUM(A1:B2) GARBAGE"):
            with self.assertRaises(HwpxError,msg=value):
                evaluate(p,target,value)

    def test_split_and_merge_tables(self):
        p = Package(create_blank())
        target = create_table(p,"Contents/section0.xml#0",3,2,[["1","2"],["3","4"],["5","6"]])["target"]
        second = table_edit(p,target,"split-table",index=1)["target"]
        self.assertEqual(grid(p.target(target)[1])[:2],(1,2))
        table_edit(p,target,"merge-table",other=second)
        self.assertEqual(grid(p.target(target)[1])[:2],(3,2))
        Package(p.bytes()).validate()

    def test_failed_branch_commit_preserves_redo(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"work.hwpx"
            first = create_blank(); save(path,first)
            p = Package(first); replace_range(p,"Contents/section0.xml#0",0,0,"second")
            second = p.bytes(); save(path,second,expected=p.version)
            history(path,"undo")
            p = Package(first); replace_range(p,"Contents/section0.xml#0",0,0,"failed branch")
            with patch("hwpx_cli.storage.atomic_write",side_effect=OSError("disk full")):
                with self.assertRaises(OSError): save(path,p.bytes(),expected=p.version)
            history(path,"redo")
            self.assertEqual(path.read_bytes(),second)


if __name__ == "__main__":unittest.main()
