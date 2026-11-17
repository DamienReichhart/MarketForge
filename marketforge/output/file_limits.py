# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Open-file limits of the process."""

from __future__ import annotations

import sys

# File descriptors kept free for everything else when Parquet writers are open.
_FD_HEADROOM = 64


def ensure_open_file_capacity(n_files: int) -> None:
    """
    Make sure this process may keep ``n_files`` files open at once.

    A Parquet file can only be finished, not appended to, so every Parquet
    output stays open until generation ends. Default soft limits (256 on
    macOS, 1024 on Linux) are below what a whole-catalog run needs; the soft
    limit is raised towards the hard limit when necessary.

    Raises:
        OSError: if the hard limit is too low.
    """
    try:
        import resource
    except ImportError:  # Windows: per-process handle limits are far higher.
        return
    needed = n_files + _FD_HEADROOM
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft == resource.RLIM_INFINITY or soft >= needed:
        return
    target = needed if hard == resource.RLIM_INFINITY else min(hard, needed)
    if sys.platform == "darwin":  # setrlimit fails above kern.maxfilesperproc
        target = min(target, 10_240)
    if target > soft:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            soft = target
        except (ValueError, OSError):
            pass
    if soft < needed:
        raise OSError(
            f"Parquet output keeps every file open until the end: {n_files} files need "
            f"~{needed} file descriptors but this process may open only {soft}. "
            "Raise the limit (ulimit -n), request fewer instruments or timeframes, "
            "or use CSV."
        )
