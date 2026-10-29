"""Shared stable-filesystem containment and link checks."""

import stat
from pathlib import Path


class PathSafetyError(ValueError):
    """An existing path is missing, unsafe, or has an unexpected type."""


def check_path(path: Path, root: Path | None = None, *, directory: bool) -> None:
    """Reject links/reparse points at every component, including root ancestors.

    This is a policy check for a stable filesystem, not protection against a
    hostile process concurrently replacing paths between checking and opening.
    """
    try:
        for component in (*reversed(path.parents), path):
            info = component.lstat()
            if stat.S_ISLNK(info.st_mode) or (
                getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                raise PathSafetyError(f"Links and reparse points are not allowed: {component}")
        resolved = path.resolve(strict=True)
        if root is not None and not resolved.is_relative_to(root):
            raise PathSafetyError(f"Path escapes configured root: {path}")
        mode = path.stat().st_mode
        if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
            raise PathSafetyError(f"Expected {'directory' if directory else 'regular file'}: {path}")
    except (OSError, RuntimeError):
        raise PathSafetyError(f"Missing or inaccessible path: {path}") from None

