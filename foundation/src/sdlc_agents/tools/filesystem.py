"""Read UTF-8 text within a configured project root; never write or execute."""

import os
import re
import stat
from fnmatch import fnmatchcase
from pathlib import PureWindowsPath
from typing import Any

from ..paths import PathSafetyError, check_path
from .base import ToolAccessError, ToolContext, ToolDescriptor

DEFAULT_EXCLUSIONS = (
    ".git", ".aws", ".ssh", ".azure", ".kube", ".env*", ".npmrc", ".pypirc",
    "credentials*", "secrets*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore",
    "id_rsa*", "id_ed25519*", "id_ecdsa*",
)


def _reserved_component(part: str) -> bool:
    """Portable Windows filename restrictions, including device aliases."""
    stem = part.split(".", 1)[0].rstrip(" ").upper()
    return (any(ord(char) < 32 or char in '<>"|?*' for char in part)
            or stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
            or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem) is not None)


class ReadTextTool:
    @property
    def descriptor(self) -> ToolDescriptor:
        return ToolDescriptor.model_validate({
            "tool_id": "fs.read_text", "required_capabilities": ("filesystem.read",),
            "inputs": {"schema": {
                "type": "object", "properties": {"path": {"type": "string", "minLength": 1}},
                "required": ["path"], "additionalProperties": False,
            }},
            "outputs": {"schema": {
                "type": "object", "properties": {"text": {"type": "string"}},
                "required": ["text"], "additionalProperties": False,
            }},
        })

    async def invoke(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        raw = arguments["path"]
        # Accept portable slash paths only. Reject drive/UNC/ADS/device aliases
        # even on POSIX so the same request cannot become unsafe on Windows.
        parts = raw.split("/")
        if ("\\" in raw or ":" in raw or "\x00" in raw or PureWindowsPath(raw).drive
                or any(part in ("", ".", "..") or part != part.rstrip(" .")
                       or _reserved_component(part) for part in parts)):
            raise ToolAccessError("Unsafe relative path")
        patterns = (*DEFAULT_EXCLUSIONS, *context.excluded_patterns)
        if any(fnmatchcase(value.casefold(), pattern.casefold())
               for pattern in patterns for value in (raw, *parts)):
            raise ToolAccessError("Resource is excluded")
        path = context.source_root.joinpath(*parts)
        try:
            check_path(context.source_root, directory=True)
            check_path(path, context.source_root, directory=False)
            # Hard links can alias excluded files without traversing a symlink.
            before = path.stat()
            if before.st_nlink != 1:
                raise ToolAccessError("Hard-linked files are not allowed")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
                    raise ToolAccessError("File changed during authorization")
                check_path(path, context.source_root, directory=False)
                content = stream.read(context.max_read_bytes + 1)
        except PathSafetyError:
            raise ToolAccessError("Path is inaccessible or outside policy") from None
        if len(content) > context.max_read_bytes:
            raise ValueError("File exceeds configured read limit")
        text = content.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("Binary content is unsupported")
        return {"text": text}
