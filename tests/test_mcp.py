from datetime import timedelta
from importlib.util import find_spec
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from hwpx_cli.crypto import encrypt
from hwpx_cli.package import Package, q
from hwpx_cli.storage import digest, history


@unittest.skipUnless(find_spec("mcp"), 'Install ".[mcp]" to test MCP')
class McpTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_over_stdio(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = Path(__file__).parent / "fixtures"
            shutil.copyfile(next(fixtures.glob("*.webp")), root / "image.webp")
            server = StdioServerParameters(
                command=sys.executable,
                args=["-m", "hwpx_cli", "mcp", "--workspace", str(root)],
                cwd=Path(__file__).resolve().parents[1],
            )
            async with stdio_client(server) as (reader, writer):
                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=15)) as client:
                    await client.initialize()
                    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                    self.assertTrue(tools["hwpx_inspect"].annotations.readOnlyHint)

                    async def call(tool, **arguments):
                        result = await client.call_tool(f"hwpx_{tool}", arguments)
                        self.assertFalse(result.isError, result.content)
                        return result.structuredContent

                    catalog = await call("operations")
                    self.assertIn("table.create", catalog["operations"])
                    self.assertIn("row_height", catalog["contracts"])
                    family = await call("operations", family="table")
                    self.assertIn("row_height", family["contracts"])
                    self.assertNotIn("text.range", family["contracts"])
                    path = "작업본.hwpx"
                    created = await call("create", output=path)
                    doc = await call("inspect", path=path, limit=1)
                    self.assertEqual(created["version"], doc["version"])
                    target = doc["elements"][0]["target"]
                    long_text = "초안" + "가" * 200
                    insert = {"op": "text.range", "target": target, "start": 0, "end": 0, "value": long_text}
                    image = {"op": "image.insert", "target": target, "path": "image.webp"}
                    source = root / path
                    self.assertEqual(digest(source.read_bytes()), doc["version"])

                    apply = {"path": path, "expected_version": doc["version"], "in_place": True}
                    for invalid in ({"op": "unknown"}, {**image, "path": "../image.webp"}):
                        failed = await client.call_tool("hwpx_apply", {**apply, "operations": [insert, invalid]})
                        self.assertTrue(failed.isError, failed.content)
                        self.assertEqual(digest(source.read_bytes()), doc["version"])

                    saved = await call("apply", **apply, operations=[insert, image])
                    self.assertEqual(digest(source.read_bytes()), saved["version"])
                    self.assertTrue((root / f"{path}.bak").is_file())
                    self.assertEqual(len(history(root / path)["revisions"]), 2)
                    stale = await client.call_tool("hwpx_apply", {**apply, "operations": [insert]})
                    self.assertTrue(stale.isError)
                    self.assertIn("Stale document version", stale.content[0].text)
                    self.assertEqual((await call("inspect", path=path, limit=1))["next_offset"], 1)
                    compact = (await call("inspect", path=path, kind="p"))["elements"][0]
                    self.assertEqual(compact["text"], long_text[:160])
                    self.assertTrue(compact["text_truncated"])
                    self.assertNotIn("attributes", compact)
                    full = await call("inspect", path=path, target=target, detail="full")
                    self.assertEqual(full["total"], 1)
                    self.assertIn("attributes", full["elements"][0])
                    self.assertEqual(full["elements"][0]["text"], long_text)
                    match = await call("find", path=path, text="초안")
                    self.assertEqual(match["matches"], [{"target": target, "start": 0, "end": 2, "text": "초안"}])

                    output = "최종본.hwpx"
                    await call("apply", path=path, output=output, expected_version=match["version"],
                               operations=[{**insert, "end": 2, "value": "최종안"}])
                    self.assertTrue((await call("validate", path=output))["valid"])
                    self.assertEqual((await call("find", path=output, text="최종안"))["total"], 1)
                    self.assertEqual((await call("find", path=path, text="초안"))["version"], saved["version"])

                    campaign = next(fixtures.glob("*환경캠페인.hwpx")).read_bytes()
                    (root / "campaign.hwpx").write_bytes(campaign)
                    edit = {"path": "campaign.hwpx", "output": "campaign-edited.hwpx"}
                    replacement = {"text": "20명", "replacement": "24명"}
                    failed = await client.call_tool("hwpx_replace", {**edit, "replacements": [
                        replacement, {"text": "없는 문구", "replacement": ""},
                    ]})
                    self.assertTrue(failed.isError, failed.content)
                    self.assertFalse((root / edit["output"]).exists())

                    result = await call("replace", **edit, replacements=[
                        {"text": "40초", "replacement": "50초"}, replacement,
                    ])
                    self.assertEqual(result["counts"], [4, 1])
                    self.assertTrue(result["valid"])
                    self.assertEqual((root / edit["path"]).read_bytes(), campaign)
                    edited = Package((root / edit["output"]).read_bytes())
                    address = (await call("find", path=edit["output"], text="24명"))["matches"][0]["target"]
                    original_paragraph = Package(campaign).target(address)[1]
                    edited_paragraph = edited.target(address)[1]
                    self.assertEqual(
                        [(run.get("charPrIDRef"), [node.text for node in run.findall(q("hp:t"))])
                         for run in edited_paragraph.findall(q("hp:run"))],
                        [(run.get("charPrIDRef"), [node.text.replace("20", "24") if node.text else node.text
                                                   for node in run.findall(q("hp:t"))])
                         for run in original_paragraph.findall(q("hp:run"))],
                    )

                    (root / "locked.hwpx").write_bytes(encrypt(source.read_bytes(), "test"))
                    protected = await client.call_tool("hwpx_inspect", {"path": "locked.hwpx"})
                    self.assertTrue(protected.isError)
                    self.assertIn("password-protected", protected.content[0].text)
