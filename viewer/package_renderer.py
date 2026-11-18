"""Package the pinned rhwp WASM and licensed fonts, recording artifact hashes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

VIEWER = Path(__file__).resolve().parent
COMMIT = "1a76570e833917d15817415a53c09ad61ab3203f"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source",type=Path,default=VIEWER.parent/"vendor/rhwp")
    p.add_argument("--optimized",action="store_true",help="Only after the optimized build succeeds")
    args = p.parse_args()
    source = args.source.resolve()
    sha = subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"],text=True).strip()
    if sha != COMMIT:raise SystemExit("Unexpected rhwp source commit")
    destination = VIEWER/"web/rhwp"
    destination.mkdir(parents=True,exist_ok=True)
    hashes = {}
    for name in ("rhwp.js","rhwp_bg.wasm","rhwp.d.ts"):
        data = (source/"pkg"/name).read_bytes()
        if name.endswith(".wasm") and not data.startswith(b"\0asm"):raise SystemExit("Invalid WASM build")
        shutil.copyfile(source/"pkg"/name,destination/name)
        hashes[name] = sha256(data).hexdigest()
    for name in ("LICENSE","THIRD_PARTY_LICENSES.md"):
        shutil.copyfile(source/name,destination/name)
    fonts = VIEWER/"web/fonts"
    fonts.mkdir(exist_ok=True)
    for name in ("NotoSansKR-Regular.woff2","NotoSansKR-Bold.woff2","NotoSerifKR-Regular.woff2","SourceHanSerifK-OFL.txt"):
        shutil.copyfile(source/"assets/fonts"/name,fonts/name)
    report = {"source":"https://github.com/edwardkim/rhwp","commit":COMMIT,
              "optimized":args.optimized,"sha256":hashes,
              "fonts":"Noto Sans/Serif KR; SIL OFL 1.1, Adobe/Google; see fonts/SourceHanSerifK-OFL.txt"}
    (destination/"provenance.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":main()
