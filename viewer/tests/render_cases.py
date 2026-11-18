"""Build disposable HWPX scenarios and serve them for browser integration tests."""
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from PIL import Image
from hwpx_cli.controls import control_create
from hwpx_cli.creation import create_blank
from hwpx_cli.crypto import encrypt
from hwpx_cli.editing import format_text,paragraph_edit,replace_range
from hwpx_cli.images import picture_edit
from hwpx_cli.package import Package
from hwpx_cli.shapes import shape_create
from hwpx_cli.tables import create_table
from viewer.server import make_server

folder = Path(sys.argv[1]);folder.mkdir(parents=True,exist_ok=True)
root = "Contents/section0.xml#0"
cases = []
p = Package(create_blank())
replace_range(p,root,0,0,"표·그림·수식·도형 표시")
paragraph_edit(p,"insert-after",root,text="")
table_target = "Contents/section0.xml#1"
table = create_table(p,table_target,2,3,[["항목","수량","금액"],["검증", "2","1000"]])
paragraph_edit(p,"insert-after",table_target,text="")
image_target = "Contents/section0.xml#2"
img = folder/"image.png";Image.new("RGB",(80,50),(42,111,188)).save(img)
picture_edit(p,image_target,"insert",{"width":30,"height":20},img)
paragraph_edit(p,"insert-after",image_target,text="")
equation_target = "Contents/section0.xml#3"
control_create(p,equation_target,"equation","a over b")
paragraph_edit(p,"insert-after",equation_target,text="")
shape_target = "Contents/section0.xml#4"
shape_create(p,shape_target,width=35,height=15,text="도형",fill="#B8D9EE")
paragraph_edit(p,"insert-after",shape_target,text="이 문단은 표와 그림 아래에 있습니다.")
cases.append(("objects",p.bytes(),None))
p = Package(create_blank())
replace_range(p,root,0,0,"암호 문서 읽기 테스트")
cases.append(("encrypted",encrypt(p.bytes(),"test-only-password"),"test-only-password"))
p = Package(create_blank())
replace_range(p,root,0,0,"페이지 재조판 확인\n"*200)
format_text(p,root,{"size":20})
cases.append(("pagination",p.bytes(),None))
source = ROOT/"tests/fixtures/test.hwpx"
cases.append(("research",source.read_bytes(),None))
servers = [];result=[]
for name,data,password in cases:
    file = folder/(name+".hwpx");file.write_bytes(data)
    server,snapshot,url = make_server(file,password=password)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    servers.append(server)
    result.append({"name":name,"url":url,"file":str(file),"version":Package(data,raw_only=True).version})
print(json.dumps(result),flush=True)
try:
    while True:time.sleep(1)
except KeyboardInterrupt:pass
finally:
    for server in servers:server.shutdown();server.server_close()
