import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hwpx_cli.creation import create_blank
from hwpx_cli.editing import replace_range
from hwpx_cli.package import Package
from viewer.server import make_server


class ViewerTests(unittest.TestCase):
    def test_viewer_transport_refresh_and_access_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"work.hwpx"; path.write_bytes(create_blank())
            server,snapshot,url = make_server(path)
            worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            try:
                initial = json.load(urlopen(url+"api/state"))
                self.assertEqual(urlopen(url+"api/document/"+initial["version"]).read(),path.read_bytes())
                p = Package(path.read_bytes()); replace_range(p,"Contents/section0.xml#0",0,0,"changed")
                path.write_bytes(p.bytes())
                updated = json.load(urlopen(url+"api/state"))
                self.assertNotEqual(initial["version"],updated["version"])
                path.write_bytes(b"incomplete")
                failed = json.load(urlopen(url+"api/state"))
                self.assertEqual(failed["version"],updated["version"])
                self.assertTrue(failed["error"])
                for request in (url+"../README.md",Request(url+"api/state",headers={"Host":"evil.example"}),Request(url+"api/state",headers={"Origin":"http://evil.example"})):
                    with self.assertRaises(HTTPError):urlopen(request)
            finally:
                server.shutdown(); server.server_close(); worker.join()
