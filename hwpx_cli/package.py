"""Bounded package IO and exact, versioned element addresses."""

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED, BadZipFile

from lxml import etree as E

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "opf": "http://www.idpf.org/2007/opf/",
}
HEADER = "Contents/header.xml"
CONTENT = "Contents/content.hpf"
MAX_PACKAGE = 256 * 1024 * 1024
MAX_ENTRY = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_ENTRIES = 10000


class HwpxError(ValueError):
    pass


class EncryptedHwpxError(HwpxError):
    pass


def q(name):
    prefix, local = name.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def xml(data):
    parser = E.XMLParser(resolve_entities=False, load_dtd=False, no_network=True,
                         recover=False, huge_tree=False, remove_blank_text=False)
    try:
        root = E.fromstring(data, parser)
    except E.XMLSyntaxError as exc:
        raise HwpxError(f"Invalid XML: {exc}") from exc
    if root.getroottree().docinfo.doctype or any(isinstance(n, E._Entity) for n in root.iter()):
        raise HwpxError("DTD and entity declarations are not allowed")
    return root


def safe_name(name):
    if (not name or "\\" in name or "\x00" in name or ":" in name
            or name.startswith("/") or any(p in (".", "..", "") for p in name.rstrip("/").split("/"))):
        raise HwpxError(f"Unsafe package path: {name!r}")
    return name


def local_name(node):
    return E.QName(node).localname if isinstance(node.tag, str) else ""


def text_of(paragraph):
    """Only this paragraph's direct runs; nested tables are separate containers."""
    result = []
    for run in paragraph.findall(q("hp:run")):
        for t in run.findall(q("hp:t")):
            result.append(t.text or "")
            for child in t:
                tag = local_name(child)
                result.append("\n" if tag == "lineBreak" else "\t" if tag == "tab" else "\ufffc")
                result.append(child.tail or "")
    return "".join(result)


class Package:
    def __init__(self, data, raw_only=False):
        if len(data) > MAX_PACKAGE:
            raise HwpxError("Compressed package size limit exceeded")
        self.original = data
        self.version = sha256(data).hexdigest()
        self.parts, self.infos, self.trees, self.dirty = {}, [], {}, set()
        self.allocated = {}
        try:
            with ZipFile(BytesIO(data)) as z:
                infos = z.infolist()
                if len(infos) > MAX_ENTRIES:
                    raise HwpxError("Too many ZIP entries")
                total = 0
                for info in infos:
                    safe_name(info.filename)
                    if info.filename in self.parts:
                        raise HwpxError(f"Duplicate ZIP entry: {info.filename}")
                    if info.flag_bits & 1:
                        raise HwpxError("Encrypted ZIP is unsupported; HWPX encryption requires its own codec")
                    total += info.file_size
                    if info.file_size > MAX_ENTRY or total > MAX_TOTAL:
                        raise HwpxError("Decompression size limit exceeded")
                    with z.open(info) as stream:
                        payload = stream.read(min(MAX_ENTRY, MAX_TOTAL - total + info.file_size) + 1)
                    if len(payload) != info.file_size:
                        raise HwpxError("ZIP entry size mismatch or decompression limit exceeded")
                    self.parts[info.filename] = payload
                    self.infos.append(deepcopy(info))
                self.comment = z.comment
        except (BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise HwpxError(f"Cannot read HWPX package: {exc}") from exc
        for required in ("mimetype", "version.xml", HEADER, CONTENT, "META-INF/container.xml"):
            if required not in self.parts:
                raise HwpxError(f"Required package entry missing: {required}")
        if (self.parts["mimetype"] != b"application/hwp+zip" or self.infos[0].filename != "mimetype"
                or self.infos[0].compress_type != ZIP_STORED):
            raise HwpxError("mimetype must be the first, uncompressed entry: application/hwp+zip")
        self.signed = any("signature" in n.lower() for n in self.parts)
        if raw_only:
            return
        if any(local_name(n) == "encryption-data" for name in self.parts
               if name.endswith("manifest.xml") for n in self.tree(name).iter()):
            raise EncryptedHwpxError("Encrypted HWPX requires a password")
        manifest = self.tree(CONTENT)
        self.items = {}
        script_ids = set()
        for item in manifest.findall("opf:manifest/opf:item", NS):
            ident = item.get("id")
            if not ident or ident in self.items:
                raise HwpxError("Empty or duplicate manifest ID")
            href = item.get("href", "")
            media_type = item.get("media-type", "").split(";", 1)[0].strip().lower()
            if media_type in {"application/x-javascript", "application/javascript", "text/javascript"}:
                script_ids.add(ident)
            if item.get("isEmbeded", "1") == "0":
                self.items[ident] = None
            else:
                self.items[ident] = self.resolve_href(href)
        self.sections = []
        for ref in manifest.findall("opf:spine/opf:itemref", NS):
            ident = ref.get("idref")
            if ident not in self.items:
                raise HwpxError(f"Unknown spine ID: {ident}")
            if ident in script_ids:
                continue
            name = self.items[ident]
            if name and self.tree(name).tag == q("hs:sec"):
                if name in self.sections:
                    raise HwpxError("Duplicate section in spine")
                self.sections.append(name)
        if not self.sections:
            raise HwpxError("No sections in manifest/spine")
        self.tree(HEADER)

    def resolve_href(self, href):
        decoded = unquote(href)
        if urlsplit(decoded).scheme or urlsplit(decoded).netloc or "#" in decoded or "?" in decoded:
            raise HwpxError(f"Unsupported embedded resource URI: {href}")
        safe_name(decoded)
        for candidate in (decoded, str(PurePosixPath(CONTENT).parent / decoded)):
            if candidate in self.parts:
                return candidate
        raise HwpxError(f"Missing manifest resource: {href}")

    def tree(self, name):
        if name not in self.trees:
            self.trees[name] = xml(self.parts[name])
        return self.trees[name]

    def address(self, name, node):
        indexes = []
        while node.getparent() is not None:
            parent = node.getparent()
            indexes.append(str(parent.index(node)))
            node = parent
        return name + "#" + "/".join(reversed(indexes))

    def target(self, address, tag=None):
        try:
            name, path = address.split("#", 1)
            if name not in self.sections and name != HEADER:
                raise HwpxError("Target must be a section or header XML")
            node = self.tree(name)
            for part in path.split("/") if path else []:
                if not part.isdecimal():
                    raise HwpxError("Target paths use nonnegative child indices")
                node = node[int(part)]
        except (ValueError, IndexError, KeyError) as exc:
            raise HwpxError(f"Invalid target address: {address}") from exc
        if tag and node.tag != q(tag):
            raise HwpxError(f"Expected {tag}, found {local_name(node)}")
        return name, node

    def mark(self, name):
        if self.signed:
            raise HwpxError("Editing signed packages is not supported")
        self.dirty.add(name)
        if name in self.sections:
            # Layout changes can affect every following paragraph, including table cells.
            for layout in self.tree(name).iter(q("hp:linesegarray")):
                layout.getparent().remove(layout)

    def new_id(self, tag, attr="id"):
        drawings = {"hp:tbl","hp:pic","hp:rect","hp:line","hp:ellipse","hp:polygon","hp:container","hp:equation"}
        tags = {q(t) for t in drawings} if tag in drawings else {q(tag)}
        values = [int(n.get(attr)) for name in self.sections for n in self.tree(name).iter() if n.tag in tags
                  if n.get(attr, "").isdecimal()]
        key = ("drawing" if tag in drawings else tag, attr)
        value = max(max(values, default=0), self.allocated.get(key, 0)) + 1
        self.allocated[key] = value
        return str(value)

    INSPECT_KINDS = {"p", "tbl", "pic", "rect", "ellipse", "line", "equation", "header", "footer",
                     "footNote", "endNote", "fieldBegin", "bookmark"}

    def elements(self, kind=None):
        for name in self.sections:
            for node in self.tree(name).iter():
                node_kind = local_name(node)
                if node_kind in self.INSPECT_KINDS and (kind is None or node_kind == kind):
                    yield name, node, node_kind

    def element_info(self, name, node, kind, *, text_limit=None):
        row = {"target": self.address(name, node), "kind": kind}
        if text_limit is None:
            row["attributes"] = dict(node.attrib)
        if node.tag == q("hp:p"):
            text = text_of(node)
            if text_limit is not None and len(text) > text_limit:
                row["text_truncated"] = True
                text = text[:text_limit]
            row["text"] = text
        return row

    def inspect(self):
        rows = [self.element_info(*element) for element in self.elements()]
        return {"version": self.version, "sections": self.sections, "entries": len(self.parts), "elements": rows}

    def validate(self):
        head = self.tree(HEADER)
        definitions = {}
        for tag, attr in (("charPr", "charPrIDRef"), ("paraPr", "paraPrIDRef"),
                          ("style", "styleIDRef"), ("borderFill", "borderFillIDRef")):
            nodes = list(head.iter(q("hh:" + tag)))
            ids = [n.get("id") for n in nodes]
            if len(ids) != len(set(ids)):
                raise HwpxError(f"Duplicate {tag} ID")
            definitions[attr] = set(ids)
        for name in self.sections:
            for node in self.tree(name).iter():
                for attr, ids in definitions.items():
                    value = node.get(attr)
                    if value is not None and value not in ids:
                        raise HwpxError(f"Dangling {attr}={value} in {name}")
                if node.tag == q("hc:img") and node.get("binaryItemIDRef") not in self.items:
                    raise HwpxError("Dangling image reference")
                if node.tag == q("hp:tbl"):
                    from .tables import grid
                    grid(node)
        return {"valid": True, "sections": len(self.sections)}

    def bytes(self):
        if not self.dirty:
            return self.original
        self.validate()
        parts = dict(self.parts)
        for name in self.dirty:
            if name in self.trees:
                parts[name] = E.tostring(self.trees[name], encoding="UTF-8", xml_declaration=True)
        output = BytesIO()
        with ZipFile(output, "w") as z:
            z.comment = self.comment
            written = set()
            for info in self.infos:
                if info.filename in parts:
                    z.writestr(info, parts[info.filename])
                    written.add(info.filename)
            for name in parts.keys() - written:
                safe_name(name)
                z.writestr(name, parts[name], compress_type=ZIP_DEFLATED)
        result = output.getvalue()
        Package(result).validate()
        return result
