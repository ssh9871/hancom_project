"""Command line boundary; every mutation uses the same validated commit path."""

import argparse
from getpass import getpass
import json
from pathlib import Path
import sys

from . import editing
from .creation import create_blank
from .controls import control_create, control_edit, styles
from .calculation import evaluate
from .clipboard import copy_node, paste_html
from .shapes import shape_create, shape_edit
from .numbering import apply_numbering
from .crypto import decrypt, encrypt, is_encrypted
from .images import picture_edit
from .package import HwpxError, Package
from .storage import digest, history, read_file, save
from .tables import create_table, table_edit


def json_object(value):
    try:
        result = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if not isinstance(result, dict):
        raise argparse.ArgumentTypeError("Expected a JSON object")
    return result


def parser():
    p = argparse.ArgumentParser(prog="hwpx", description="ZIP/XML HWPX editor")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("operations",help="List implemented JSON operation names")
    c = sub.add_parser("mcp", help="Serve HWPX editing tools over MCP stdio")
    c.add_argument("--workspace", type=Path, default=Path.cwd(), help="Root for document and image paths")
    c = sub.add_parser("create", help="Create a blank document without a template")
    c.add_argument("--output", required=True)
    c.add_argument("--template", help="Optionally copy an existing HWPX instead")
    for op in ("inspect", "validate", "find", "copy", "apply", "history"):
        c = sub.add_parser(op)
        c.add_argument("file", type=Path)
        c.add_argument("--json", action="store_true", help="JSON is also the default output format")
        if op == "find":
            c.add_argument("--text", required=True)
        if op in ("copy", "apply"):
            group = c.add_mutually_exclusive_group(required=True)
            group.add_argument("--output", type=Path)
            if op == "apply":
                group.add_argument("--in-place", action="store_true")
        if op == "apply":
            group = c.add_mutually_exclusive_group(required=True)
            group.add_argument("--operation", type=json_object, help="One operation as a JSON object")
            group.add_argument("--batch", type=Path, help="UTF-8 JSON array; all operations commit atomically")
            c.add_argument("--expect-version", help="Reject stale addresses/results")
        if op == "history":
            c.add_argument("action", choices=("list", "undo", "redo", "restore", "prune"))
            c.add_argument("--revision", type=int)
    text = sub.add_parser("text")
    ts = text.add_subparsers(dest="text_op", required=True)
    for op in ("replace", "insert", "delete"):
        c = ts.add_parser(op)
        c.add_argument("file", type=Path)
        c.add_argument("--target")
        if op == "replace":
            c.add_argument("--text", required=True)
            c.add_argument("--with", dest="replacement", required=True)
            c.add_argument("--all", action="store_true")
        else:
            c.add_argument("--start", type=int, required=True)
            if op == "insert":
                c.add_argument("--text", required=True)
            else:
                c.add_argument("--end", type=int, required=True)
        c.add_argument("--expect-version")
        c.add_argument("--json", action="store_true")
        g = c.add_mutually_exclusive_group(required=True)
        g.add_argument("--output", type=Path)
        g.add_argument("--in-place", action="store_true")
    c = sub.add_parser("password",help="Set/change/remove HWPX password; output must be a new file")
    c.add_argument("action",choices=("set","change","remove"))
    c.add_argument("file",type=Path)
    c.add_argument("--output",type=Path,required=True)
    return p


def apply_operation(pkg, operation):
    if not isinstance(operation, dict) or not isinstance(operation.get("op"), str):
        raise HwpxError("Operation must be an object with an op string")
    o = dict(operation)
    op = o.pop("op")
    if op == "text.replace":
        return editing.replace_all(pkg, o.pop("text"), o.pop("with"), **o)
    if op == "text.range":
        return editing.replace_range(pkg, **o)
    if op.startswith("paragraph."):
        return editing.paragraph_edit(pkg, op.split(".",1)[1], **o)
    if op == "format.text":
        return editing.format_text(pkg, **o)
    if op == "format.paragraph":
        return editing.format_paragraph(pkg, **o)
    if op == "format.numbering":
        return apply_numbering(pkg,**o)
    if op == "section.set":
        return editing.section_edit(pkg, **o)
    if op == "table.create":
        return create_table(pkg, **o)
    if op == "table.calculate":
        return evaluate(pkg,**o)
    if op.startswith("table."):
        target = o.pop("target")
        return table_edit(pkg, target, op.split(".",1)[1], **o)
    if op.startswith("image."):
        return picture_edit(pkg, op=op.split(".",1)[1], **o)
    if op == "control.create":
        return control_create(pkg,**o)
    if op.startswith("control."):
        return control_edit(pkg,action=op.split(".",1)[1],**o)
    if op.startswith("style."):
        return styles(pkg,action=op.split(".",1)[1],**o)
    if op == "clipboard.copy":
        return copy_node(pkg,**o)
    if op == "clipboard.html":
        return paste_html(pkg,**o)
    if op == "shape.create":
        return shape_create(pkg,**o)
    if op.startswith("shape."):
        return shape_edit(pkg,action=op.split(".",1)[1],**o)
    raise HwpxError(f"Operation is not implemented: {op}")


def operation_catalog():
    return {"operations":[
        "text.replace","text.range","paragraph.insert-before","paragraph.insert-after","paragraph.delete","paragraph.split","paragraph.merge-next",
        "format.text","format.paragraph","format.numbering","section.set",
        "table.create","table.delete","table.insert-row","table.insert-column","table.delete-row","table.delete-column",
        "table.merge","table.split-cell","table.transpose","table.split-table","table.merge-table","table.resize","table.border","table.calculate",
        "image.insert","image.replace","image.set","image.delete","control.create","control.set","control.rename","control.delete",
        "style.list","style.create","style.rename","style.update","style.apply","style.delete","clipboard.copy","clipboard.html",
        "shape.create","shape.set","shape.delete"],"details":"README.md and hwpx_cli/operations.md"}


def find_text(pkg, text):
    matches = [{"target": target, "start": start, "end": end, "text": text}
               for target, start, end in editing.text_matches(pkg, text)]
    return {"version":pkg.version, "matches":matches}


def apply_batch(pkg, operations, output, *, in_place=False, password=None):
    if not isinstance(operations, list) or not operations or len(operations) > 1000:
        raise HwpxError("Batch must contain 1..1000 operations")
    results = [apply_operation(pkg, operation) for operation in operations]
    data = pkg.bytes()
    if password is not None:
        data = encrypt(data, password)
    result = save(output, data, expected=pkg.version if in_place else None,
                  command="; ".join(o["op"] for o in operations), password=password)
    result["operations"] = results
    return result


def run(args):
    if args.command == "mcp":
        try:
            from .mcp_server import make_mcp
        except ModuleNotFoundError as exc:
            if exc.name != "mcp":
                raise
            raise HwpxError('MCP support requires python -m pip install ".[mcp]"') from exc
        return make_mcp(args.workspace).run(transport="stdio")
    if args.command == "operations":
        return operation_catalog()
    if args.command == "create":
        data = read_file(args.template) if args.template else create_blank()
        password = getpass("Template HWPX password: ") if is_encrypted(data) else None
        return save(args.output, data, command="create",password=password)
    if args.file.suffix.lower() != ".hwpx":
        raise HwpxError("Only .hwpx input is supported")
    if args.command == "history":
        password = getpass("HWPX password: ") if is_encrypted(read_file(args.file)) else None
        return history(args.file, args.action, args.revision,password)
    data = read_file(args.file)
    encrypted = is_encrypted(data)
    password = getpass("HWPX password: ") if encrypted else None
    source_version = digest(data)
    plain = decrypt(data,password)
    pkg = Package(plain)
    pkg.version = source_version
    if args.command == "password":
        if args.output.resolve() == args.file.resolve():
            raise HwpxError("Password transitions require a new output to keep old history/backups separate")
        if args.action == "set" and encrypted:
            raise HwpxError("Document is already encrypted; use password change")
        if args.action in ("change","remove") and not encrypted:
            raise HwpxError("Document is not encrypted")
        new_password = None
        if args.action != "remove":
            new_password = getpass("New HWPX password: ")
            if new_password != getpass("Confirm new password: "):
                raise HwpxError("Passwords do not match")
        output_data = encrypt(plain,new_password) if new_password is not None else plain
        return save(args.output,output_data,command="password."+args.action,password=new_password)
    if args.command == "inspect":
        return pkg.inspect()
    if args.command == "validate":
        return pkg.validate()
    if args.command == "find":
        return find_text(pkg, args.text)
    if args.command == "copy":
        return save(args.output, data, command="copy",password=password)
    if args.expect_version and args.expect_version != pkg.version:
        raise HwpxError("Stale document version; inspect again")
    if args.command == "text":
        if args.text_op == "replace":
            operations = [{"op":"text.replace", "text":args.text, "with":args.replacement,
                           "target":args.target, "all_matches":args.all}]
        else:
            if not args.target:
                raise HwpxError("--target is required for insertion/deletion")
            operations = [{"op":"text.range", "target":args.target, "start":args.start,
                           "end":args.start if args.text_op == "insert" else args.end,
                           "value":args.text if args.text_op == "insert" else ""}]
    else:
        operations = json.loads(args.batch.read_text(encoding="utf-8-sig")) if args.batch else [args.operation]
    output = args.file if args.in_place else args.output
    if not args.in_place and output.resolve() == args.file.resolve():
        raise HwpxError("Use --in-place explicitly to replace the input")
    return apply_batch(pkg, operations, output, in_place=args.in_place, password=password)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
        if result is not None:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"error":str(exc)},ensure_ascii=True),file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
