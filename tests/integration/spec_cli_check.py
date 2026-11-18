"""Run the public CLI against a disposable copy of the campaign specification."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

from lxml import etree

fixtures = Path("tests/fixtures")
source = fixtures / "가상기관_요구사항명세서_B_환경캠페인.hwpx"
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
work = out / "work.hwpx"
report = out / "commands.md"
report.write_text("# 명세서 CLI 실행 기록\n", encoding="utf-8")
step = 0
results = {}
exercised = set()


def log(message):
    with report.open("a", encoding="utf-8") as file:
        file.write(message + "\n")


def cli(*args, expected=0, passwords=()):
    args = list(map(str, args))
    command = ["python", "-m", "hwpx_cli", *args]
    # Redirect disposable test passwords to the standard getpass fallback on Windows.
    launcher = [sys.executable, "-m", "hwpx_cli"]
    if passwords and sys.platform == "win32":
        launcher = [sys.executable, "-c",
                    "import sys,runpy; sys.__stdin__=None; runpy.run_module('hwpx_cli',run_name='__main__',alter_sys=True)"]
    process = subprocess.run(launcher + args, capture_output=True, text=True, encoding="utf-8",
                             input="\n".join(passwords) + "\n" if passwords else None, timeout=30)
    log("\n```powershell\n" + " ".join(command[:3] + [
        "'" + arg.replace("'", "''") + "'" for arg in args]) + "\n```")
    if passwords:
        log("암호 프롬프트에 입력할 테스트 값 " + " → ".join(passwords))
    lines = (process.stdout + process.stderr).splitlines()
    data = json.loads(process.stdout) if process.stdout else None
    if args[0] == "inspect" and data:
        summary = {"sections": data["sections"], "elements": len(data["elements"]), "version": data["version"]}
    else:
        summary = data if data is not None else "\n".join(lines)
    log(f"\n종료 코드 {process.returncode}\n\n```text\n" +
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n```")
    assert process.returncode == expected, f"{args}: {lines}"
    return data


def op(operation, **kwargs):
    global step
    step += 1
    batch = out / f"op-{step:02}.json"
    batch.write_text(json.dumps([{"op": operation, **kwargs}], ensure_ascii=False, indent=2), encoding="utf-8")
    log("\n입력 JSON\n\n```json\n" + batch.read_text(encoding="utf-8") + "\n```")
    result = cli("apply", work, "--batch", batch, "--in-place")["operations"][0]
    exercised.add(operation)
    return result


def find(text, file=work, **kwargs):
    return cli("find", file, "--text", text, **kwargs)["matches"]


def node(target):
    name, indexes = target.split("#", 1)
    with ZipFile(work) as archive:
        element = etree.fromstring(archive.read(name))
    for index in indexes.split("/"):
        element = element[int(index)]
    return element


def case(name, check):
    log("\n## " + name)
    try:
        results[name] = check()
    except (AssertionError, KeyError, IndexError, TypeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        results[name] = "실패 " + str(error)
    print(name, results[name], flush=True)
    log("\n**검증 결과** " + results[name])


original = source.read_bytes()
operations = set(cli("operations")["operations"])
cli("validate", source)
initial = cli("inspect", source)
cli("copy", source, "--output", work)
cli("create", "--template", source, "--output", out / "template.hwpx")
cli("create", "--output", out / "blank.hwpx")
cli("validate", out / "blank.hwpx")
assert work.read_bytes() == original == (out / "template.hwpx").read_bytes()
log("\n복사본과 템플릿 생성 파일의 원본 SHA-256 일치 " + hashlib.sha256(original).hexdigest())


def text_check():
    title = find("40초")[0]["target"]
    cli("text", "replace", work, "--target", title, "--text", "40초", "--with", "45초", "--in-place")
    assert find("45초")[0]["target"] == title
    cell = find("20명")[0]["target"]
    op("text.replace", target=cell, text="20명", **{"with": "24명"})
    assert find("24명")[0]["target"] == cell
    cli("text", "insert", work, "--target", cell, "--start", 0, "--text", "검토 ", "--in-place")
    assert find("검토 ")[0]["target"] == cell
    cli("text", "delete", work, "--target", cell, "--start", 0, "--end", 3, "--in-place")
    assert not find("검토 ")
    return "통과. 제목 45초, 원본 표 셀 24명, 삽입 후 삭제 확인."


case("검색과 텍스트 편집", text_check)
op("paragraph.insert-after", target="Contents/section0.xml#1", text="QA 기준 문단")
anchor = find("QA 기준 문단")[0]["target"]


def paragraph_check():
    op("paragraph.insert-before", target=anchor, text="QA 임시 문단")
    temp = find("QA 임시 문단")[0]["target"]
    op("paragraph.split", target=temp, offset=3)
    assert find("임시 문단")[0]["target"] != temp
    op("paragraph.merge-next", target=temp)
    assert find("QA 임시 문단")[0]["target"] == temp
    op("paragraph.delete", target=temp)
    assert not find("QA 임시 문단")
    op("text.range", target=anchor, start=0, end=2, value="CLI")
    op("format.text", target=anchor, start=0, end=3, properties={"bold": True, "size": 16, "color": "#123456"})
    assert find("CLI 기준 문단")
    assert len({run.get("charPrIDRef") for run in node(anchor) if run.tag.endswith("}run")}) >= 2
    op("format.paragraph", target=anchor, properties={"align": "CENTER", "line-spacing": 160})
    op("format.numbering", target=anchor, kind="bullet", character="•")
    op("section.set", index=0, properties={"left": 18, "right": 18})
    return "통과. 문단 분리·병합·삭제 및 범위 편집 확인. 서식·글머리표·구역 변경 저장 성공."


case("문단·서식·구역", paragraph_check)


def table_check():
    table = op("table.create", target=anchor, rows=2, cols=3, values=[["10", "20", "0"], ["4", "5", "6"]])["target"]
    assert op("table.calculate", target=table, formula="SUM(A1:B1)", row=0, column=2, write=True)["result"] == 30
    assert any(hit["target"].startswith(table + "/") for hit in find("30"))
    op("table.insert-row", target=table, index=2)
    op("table.insert-column", target=table, index=3)
    assert (node(table).get("rowCnt"), node(table).get("colCnt")) == ("3", "4")
    op("table.delete-row", target=table, index=2)
    op("table.delete-column", target=table, index=3)
    op("table.merge", target=table, row=0, column=0, end_row=0, end_column=1)
    assert any(span.get("colSpan") == "2" for span in node(table).iter("{*}cellSpan"))
    op("table.split-cell", target=table, row=0, column=0)
    assert all(span.get("colSpan") == "1" for span in node(table).iter("{*}cellSpan"))
    op("table.transpose", target=table)
    assert (node(table).get("rowCnt"), node(table).get("colCnt")) == ("3", "2")
    other = op("table.split-table", target=table, index=1)["target"]
    assert node(other).get("rowCnt") == "2"
    op("table.merge-table", target=table, other=other)
    assert node(table).get("rowCnt") == "3"
    op("table.resize", target=table, width=120, height=30)
    op("table.border", target=table, properties={"type": "SOLID", "width": 0.2, "color": "#123456"})
    op("table.delete", target=table)
    assert sum(e["kind"] == "tbl" for e in cli("inspect", work)["elements"]) == 2
    return "통과. 계산값 30, 2×3 → 3×4 → 2×3 → 3×2, 병합·분할·합치기 및 삭제 후 기존 표 2개 확인."


case("표 구조와 계산", table_check)


def drawing_check():
    pic = op("image.insert", target=anchor, path=(fixtures / "무궁화.webp").as_posix(), properties={"width": 25, "height": 20})["target"]
    ref = node(pic).find("{*}img").get("binaryItemIDRef")
    op("image.replace", target=pic, path=(fixtures / "한라산.webp").as_posix())
    assert node(pic).find("{*}img").get("binaryItemIDRef") != ref
    op("image.set", target=pic, properties={"rotation": 15, "brightness": 10, "width": 30})
    assert float(node(pic).find("{*}rotationInfo").get("angle")) == 15
    op("image.delete", target=pic)
    shape = op("shape.create", target=anchor, text="QA 도형", width=30, height=15)["target"]
    op("shape.set", target=shape, properties={"fill": "#ABCDEF", "stroke": "#123456", "z": 5})
    assert node(shape).get("zOrder") == "5"
    op("shape.delete", target=shape)
    assert not find("QA 도형")
    return "통과. 그림 리소스 교체, 15도 회전, 도형 zOrder 5와 삭제 확인."


case("그림과 도형", drawing_check)


def controls_check():
    for kind in ("header", "footer", "footNote", "endNote"):
        target = op("control.create", target=anchor, kind=kind, text="QA " + kind)["target"]
        assert find("QA " + kind)[0]["target"].startswith(target + "/")
        op("control.delete", target=target)
        assert not find("QA " + kind)
    for kind in ("bookmark", "field", "equation"):
        target = op("control.create", target=anchor, kind=kind, name="QA_" + kind, text="x")["target"]
        if kind != "equation":
            op("control.rename", target=target, name="QA_" + kind + "_new")
            assert node(target).get("name").endswith("_new")
        if kind != "bookmark":
            op("control.set", target=target, text="QA필드값" if kind == "field" else "x+y")
            if kind == "field":
                assert find("QA필드값")
            else:
                assert node(target).find("{*}script").text == "x+y"
        op("control.delete", target=target)
    return "통과. 머리말·꼬리말·각주·미주·책갈피·필드·수식의 구조와 해당 수정값 확인."


case("제어 요소", controls_check)


def style_copy_check():
    base = op("style.list")[0]["id"]
    style = op("style.create", ident=base, name="QA Style")["id"]
    op("style.rename", ident=style, name="QA Renamed Style")
    op("style.update", ident=style, properties={"nextStyleIDRef": style})
    op("style.apply", ident=style, target=anchor)
    assert node(anchor).get("styleIDRef") == style
    op("style.delete", ident=style, replacement=base)
    assert node(anchor).get("styleIDRef") == base
    pasted = op("clipboard.html", target=anchor, markup="<p><b>QA HTML</b><br>둘째 줄</p>")["targets"][0]
    op("clipboard.copy", target=pasted, destination=pasted)
    assert len(find("QA HTML")) == 2
    return "통과. 스타일 적용·대체 삭제 확인. HTML 삽입 및 같은 문서 내 복제 결과 2건."


case("스타일과 붙여넣기", style_copy_check)


def history_check():
    before = work.read_bytes()
    cli("text", "replace", work, "--target", "Contents/section0.xml#0", "--text", "45초", "--with", "50초", "--in-place")
    after = work.read_bytes()
    cli("history", work, "undo")
    assert work.read_bytes() == before
    cli("history", work, "redo")
    assert work.read_bytes() == after
    cli("history", work, "restore", "--revision", "1")
    assert work.read_bytes() == original
    latest = cli("history", work, "list")["revisions"][-1]["id"]
    cli("history", work, "restore", "--revision", latest)
    assert work.read_bytes() == after
    cli("history", work, "prune", "--revision", latest)
    assert len(cli("history", work, "list")["revisions"]) == 1
    return "통과. Undo·Redo·복원 바이트 일치, 정리 후 최신 리비전만 보관."


case("히스토리", history_check)


def negative_check():
    before = work.read_bytes()
    cli("text", "insert", work, "--target", anchor, "--start", 0, "--text", "실패 예정",
        "--expect-version", "stale", "--in-place", expected=2)
    batch = out / "reject-batch.json"
    batch.write_text(json.dumps([{"op": "text.range", "target": anchor, "start": 0, "end": 0, "value": "rollback"},
                                 {"op": "nonexistent"}]), encoding="utf-8")
    log("\n실패 배치 입력\n\n```json\n" + batch.read_text(encoding="utf-8") + "\n```")
    cli("apply", work, "--batch", batch, "--in-place", expected=2)
    assert work.read_bytes() == before
    return "통과. 두 실패 모두 종료 코드 2이며 파일 바이트 불변."


case("오래된 버전과 실패 배치", negative_check)


def password_check():
    old, new = "spec-test-one", "spec-test-two"
    encrypted, changed, clear = [out / name for name in ("protected.hwpx", "changed.hwpx", "clear.hwpx")]
    cli("password", "set", work, "--output", encrypted, passwords=(old, old))
    cli("validate", encrypted, passwords=("wrong-test-password",), expected=2)
    cli("validate", encrypted, passwords=(old,))
    target = find("50초", encrypted, passwords=(old,))[0]["target"]
    cli("text", "replace", encrypted, "--target", target, "--text", "50초", "--with", "55초", "--in-place", passwords=(old,))
    cli("history", encrypted, "undo", passwords=(old,))
    assert find("50초", encrypted, passwords=(old,))
    cli("history", encrypted, "redo", passwords=(old,))
    assert find("55초", encrypted, passwords=(old,))
    cli("password", "change", encrypted, "--output", changed, passwords=(old, new, new))
    cli("validate", changed, passwords=(old,), expected=2)
    cli("password", "remove", changed, "--output", clear, passwords=(new,))
    assert find("55초", clear)
    return "통과. 암호 설정·오답 거부·편집·Undo/Redo·암호 변경과 해제 확인."


case("암호 문서", password_check)
cli("validate", work)
assert source.read_bytes() == original
with ZipFile(source) as before, ZipFile(work) as after:
    changed = [name for name in before.namelist() if before.read(name) != after.read(name)]
    assert "Scripts/headerScripts.js" not in changed
    assert not any(name.startswith("BinData/") for name in changed)
    log("\n원본은 바이트 동일. 편집본에서 내용이 바뀐 기존 ZIP 항목 " + ", ".join(changed))
log("\n## 결과 집계\n")
log(f"CLI 등록 JSON 연산 {len(operations)}개 중 {len(exercised)}개 실행 성공.")
if operations - exercised:
    log("실행 성공을 확인하지 못한 연산 " + ", ".join(sorted(operations - exercised)))
for name, result in results.items():
    log(f"- {name} — {result}")
sys.exit(operations != exercised or any(result.startswith("실패") for result in results.values()))
