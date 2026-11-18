"""Loopback, read-only snapshot transport for the pinned rhwp WASM renderer."""

import argparse
from getpass import getpass
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit
import webbrowser

from hwpx_cli.crypto import decrypt, is_encrypted
from hwpx_cli.package import HwpxError, Package
from hwpx_cli.storage import read_file

WEB = Path(__file__).parent / "web"


class Snapshot:
    def __init__(self,path,password=None):
        self.path,self.password = Path(path),password
        self.version,self.data,self.error = None,None,None
        self.fingerprint = None
        self.lock = threading.Lock()

    def refresh(self):
        with self.lock:
            try:
                stat = self.path.stat()
                fingerprint = (stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size)
                if fingerprint != self.fingerprint:
                    data = read_file(self.path)
                    Package(decrypt(data,self.password)).validate()
                    self.version = sha256(data).hexdigest()
                    self.data = data
                    self.fingerprint = fingerprint
                self.error = None
            except (OSError,ValueError) as exc:
                self.error = str(exc)
            return {"version":self.version,"error":self.error,"encrypted":self.password is not None}


def make_server(path,port=0,password=None):
    snapshot = Snapshot(path,password)
    snapshot.refresh()
    if snapshot.data is None:
        raise HwpxError(snapshot.error or "Cannot read document")
    token = secrets.token_urlsafe(32)
    prefix = "/"+token+"/"
    assets = {"":"index.html","viewer.js":"viewer.js","viewer.css":"viewer.css",
              "rhwp/rhwp.js":"rhwp/rhwp.js","rhwp/rhwp_bg.wasm":"rhwp/rhwp_bg.wasm"}
    for font in ("NotoSansKR-Regular.woff2","NotoSansKR-Bold.woff2","NotoSerifKR-Regular.woff2"):
        assets["fonts/"+font] = "fonts/"+font
    mimes = {".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",
             ".css":"text/css; charset=utf-8",".wasm":"application/wasm",".woff2":"font/woff2"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def respond(self,status,data,mime="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type",mime)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Cross-Origin-Resource-Policy","same-origin")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; font-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):
                pass

        def checked_route(self):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                self.respond(403,b'{}')
                return None
            origin = self.headers.get("Origin")
            if origin and origin != "http://"+host:
                self.respond(403,b'{}')
                return None
            path = urlsplit(self.path).path
            if not path.startswith(prefix):
                self.respond(404,b'{}')
                return None
            return path[len(prefix):]

        def do_GET(self):
            route = self.checked_route()
            if route is None:
                return
            if route == "api/state":
                self.respond(200,json.dumps(snapshot.refresh()).encode())
            elif route.startswith("api/document/"):
                version = route[len("api/document/"):]
                with snapshot.lock:
                    if version == snapshot.version:
                        self.respond(200,snapshot.data,"application/hwp+zip")
                    else:
                        self.respond(409,b'{"error":"Document changed; retry"}')
            elif route in assets:
                asset = WEB/assets[route]
                if asset.is_file():
                    self.respond(200,asset.read_bytes(),mimes.get(asset.suffix,"application/octet-stream"))
                else:
                    self.respond(503,b'{"error":"rhwp renderer assets are not built; see README"}')
            else:
                self.respond(404,b'{}')

        def do_POST(self):
            route = self.checked_route()
            if route is None:
                return
            if self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
                self.respond(403,b'{}')
            elif route == "api/credentials" and self.headers.get("Content-Length","0") == "0":
                self.respond(200,json.dumps({"password":snapshot.password}).encode())
            else:
                self.respond(405,b'{}')

    server = ThreadingHTTPServer(("127.0.0.1",port),Handler)
    server.daemon_threads = True
    return server,snapshot,f"http://127.0.0.1:{server.server_port}{prefix}"


def serve(path,port=0,open_browser=False):
    if not (WEB/"rhwp/rhwp_bg.wasm").is_file():
        raise HwpxError("rhwp WASM is not built. Run viewer/build_renderer.ps1.")
    password = getpass("HWPX password: ") if is_encrypted(read_file(path)) else None
    server,snapshot,url = make_server(path,port,password)
    print(json.dumps({"viewer":url,"file":str(Path(path).absolute())}),flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        snapshot.password = None
        snapshot.data = None
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Run the standalone read-only rhwp viewer")
    parser.add_argument("file", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    if args.file.suffix.lower() != ".hwpx":
        parser.error("Only .hwpx input is supported")
    try:
        serve(args.file, args.port, args.open)
    except (OSError, ValueError) as exc:
        parser.exit(2, json.dumps({"error": str(exc)}) + "\n")


if __name__ == "__main__":
    main()
