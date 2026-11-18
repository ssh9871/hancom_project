"""Local MCP tools for the same HWPX editor and storage used by the CLI."""

from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .cli import apply_batch, operation_catalog
from .creation import create_blank
from .editing import text_matches
from .package import EncryptedHwpxError, HwpxError, Package, local_name
from .storage import read_file, save


class TextReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, Field(min_length=1)]
    replacement: str


def make_mcp(workspace: Path) -> FastMCP:
    root = workspace.resolve(strict=True)
    if not root.is_dir():
        raise HwpxError("MCP workspace must be a directory")

    server = FastMCP(
        "HWPX Editor",
        log_level="WARNING",
        instructions=(
            "For known literal replacements, call hwpx_replace once per document. "
            "It finds matches, saves, and validates in one call. Use its counts to confirm the edit. "
            "For other edits, prefer hwpx_find or a filtered hwpx_inspect, then hwpx_apply with the returned version. "
            "Use hwpx_operations with a family only if you need the operation syntax. "
            "Use a new output path unless the user wants to update the source. "
            "Relative paths are resolved from the configured workspace."
        ),
    )
    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
    edit_file = ToolAnnotations(destructiveHint=True, openWorldHint=False)

    def local_path(value: str, suffix: str | None = None) -> Path:
        if not value:
            raise HwpxError("Path must not be empty")
        path = (root / value).resolve()
        if not path.is_relative_to(root):
            raise HwpxError("Path is outside the MCP workspace")
        if suffix and path.suffix.lower() != suffix:
            raise HwpxError("Document paths must use the .hwpx extension")
        return path

    def load_document(path: Path) -> Package:
        if not path.is_file():
            raise HwpxError("HWPX document is not a regular file")
        try:
            return Package(read_file(path))
        except EncryptedHwpxError as exc:
            raise HwpxError("Use the interactive hwpx CLI for password-protected documents") from exc

    def prepare_edit(path, output, in_place, expected_version):
        if in_place == (output is not None):
            raise HwpxError("Choose a new output path or set in_place=true")
        source = local_path(path, ".hwpx")
        destination = source if in_place else local_path(output, ".hwpx")
        if not in_place and destination == source:
            raise HwpxError("Use in_place=true to replace the input")
        pkg = load_document(source)
        if expected_version is not None and expected_version != pkg.version:
            raise HwpxError("Stale document version; inspect again")
        return pkg, destination

    def page(items, key: str, offset: int, limit: int) -> dict[str, Any]:
        selected = []
        end = offset + limit
        total = 0
        for total, item in enumerate(items, 1):
            if offset < total <= end:
                selected.append(item)
        return {key: selected, "total": total, "next_offset": end if end < total else None}

    @server.tool(annotations=read_only)
    def hwpx_operations(family: str | None = None) -> dict[str, Any]:
        """Get hwpx_apply syntax for one family such as table, image, or format. Omit family for the full catalog."""
        operations = operation_catalog()["operations"]
        contracts = Path(__file__).with_name("operations.md").read_text(encoding="utf-8")
        if family is not None:
            operations = [name for name in operations if name.startswith(family + ".")]
            if not operations:
                raise HwpxError("Unknown operation family")
            contracts = "\n".join(line for line in contracts.splitlines() if line.startswith(f"| `{family}."))
        return {
            "operations": operations,
            "contracts": contracts,
        }

    @server.tool(annotations=read_only)
    def hwpx_inspect(
        path: str, offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=200)] = 15,
        kind: str | None = None, target: str | None = None,
        detail: Literal["compact", "full"] = "compact",
    ) -> dict[str, Any]:
        """Browse document targets and version (limit 1–200, default 15).

        Filter by kind (p, tbl, pic, etc.) or one exact target. Compact mode omits raw
        attributes and caps text at 160 characters. Use detail=full for exact text and attributes.
        Prefer hwpx_find when the text is known.
        """
        pkg = load_document(local_path(path, ".hwpx"))
        if kind is not None and kind not in pkg.INSPECT_KINDS:
            raise HwpxError("Unknown element kind")
        elements = pkg.elements(kind)
        if target is not None:
            name, node = pkg.target(target)
            node_kind = local_name(node)
            if name not in pkg.sections or node_kind not in pkg.INSPECT_KINDS or kind not in (None, node_kind):
                raise HwpxError("Target does not match an inspectable document element")
            elements = [(name, node, node_kind)]
        result = page(elements, "elements", offset, limit)
        result["elements"] = [pkg.element_info(*element, text_limit=160 if detail == "compact" else None)
                              for element in result["elements"]]
        return {"version": pkg.version, "sections": pkg.sections, "entries": len(pkg.parts), **result}

    @server.tool(annotations=read_only)
    def hwpx_find(
        path: str, text: str, offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=200)] = 15,
    ) -> dict[str, Any]:
        """Find literal text even inside cells. Return version and [start, end) code-point offsets. Limit 1–200."""
        pkg = load_document(local_path(path, ".hwpx"))
        matches = ({"target": target, "start": start, "end": end, "text": text}
                   for target, start, end in text_matches(pkg, text))
        return {"version": pkg.version, **page(matches, "matches", offset, limit)}

    @server.tool(annotations=read_only)
    def hwpx_validate(path: str) -> dict[str, Any]:
        """Check HWPX structure, style and image references, and table geometry."""
        return load_document(local_path(path, ".hwpx")).validate()

    @server.tool(annotations=ToolAnnotations(destructiveHint=False, openWorldHint=False))
    def hwpx_create(output: str) -> dict[str, Any]:
        """Create a blank HWPX at a new path. Existing files are refused."""
        return save(local_path(output, ".hwpx"), create_blank(), command="create")

    @server.tool(annotations=edit_file)
    def hwpx_replace(
        path: str, replacements: Annotated[list[TextReplacement], Field(min_length=1, max_length=1000)],
        output: str | None = None, in_place: bool = False, expected_version: str | None = None,
    ) -> dict[str, Any]:
        """Replace all matches for known literal text in the document, including cells, and validate the saved HWPX.

        Pass ordered {text, replacement} objects and a new output path or in_place=true.
        Call directly with the source path. A missing match aborts the entire batch. Counts are in request order.
        Use hwpx_find and hwpx_apply for a replacement limited to a selected location.
        """
        pkg, destination = prepare_edit(path, output, in_place, expected_version)
        operations = [{"op": "text.replace", "text": item.text, "with": item.replacement, "all_matches": True}
                      for item in replacements]
        saved = apply_batch(pkg, operations, destination, in_place=in_place)
        counts = saved.pop("operations")
        return {**saved, "counts": counts, "valid": True}

    @server.tool(annotations=edit_file)
    def hwpx_apply(
        path: str, expected_version: str, operations: list[dict],
        output: str | None = None, in_place: bool = False,
    ) -> dict[str, Any]:
        """Apply 1–1000 ordered operations atomically using a version from inspect or find.

        Supply a new output path or explicitly set in_place=true. Use hwpx_operations(family=...)
        for syntax. Addresses refer to the state after preceding operations. Save validates the result.
        """
        pkg, destination = prepare_edit(path, output, in_place, expected_version)

        local_operations = []
        for operation in operations:
            if operation.get("op") in ("image.insert", "image.replace"):
                value = operation.get("path")
                if not isinstance(value, str):
                    raise HwpxError("Image path must be a string")
                image = local_path(value)
                if not image.is_file():
                    raise HwpxError("Image is not a regular file")
                operation = {**operation, "path": str(image)}
            local_operations.append(operation)
        return {**apply_batch(pkg, local_operations, destination, in_place=in_place), "valid": True}

    return server
