"""Mapped drive letters -> their UNC shares, so a path works on any runner.

A Control Room run node's service account does not necessarily have the
office drive letters mapped (or has them mapped to different storage), so a
path read from the database or config such as ``X:\\POST RECEIVED`` is
translated to the share it names before anything touches the file system.
The map is the office `net use` list. A path on any other drive (``C:``) or
already UNC is returned unchanged.
"""

from __future__ import annotations

import os

#: Drive letter -> UNC root, from `net use` on an office machine.
DRIVE_MAP: dict[str, str] = {
    "E": r"\\inspiredenergysolutions.local\DFS\Public\EDIRoot",
    "I": r"\\inspiredenergysolutions.local\DFS\Public\!IES",
    "L": r"\\inspiredenergysolutions.local\DFS\Public\!ES",
    "M": r"\\inspiredenergysolutions.local\DFS\Informed\Data1",
    "O": r"\\inspiredenergysolutions.local\DFS\BromleyShares\STC",
    "Q": r"\\inspiredenergysolutions.local\DFS\Public\Quality",
    "R": r"\\IES-BU-FS-V01\Burgess Hill\InprovaEnergy",
    "S": r"\\inspiredenergysolutions.local\DFS\Shares\ShareSpace",
    "T": r"\\inspiredenergysolutions.local\DFS\Public\!ES\Bureau",
    "U": r"\\inspiredenergysolutions.local\DFS\Public\Universal",
    "V": r"\\ies-dc-07\FEML\Public",
    "W": r"\\inspiredenergysolutions.local\dfs\Public\STC",
    "X": r"\\inspiredenergysolutions.local\DFS\Public\!CC",
    "Y": r"\\inspiredenergysolutions.local\DFS\Public\SystemLink",
}


def to_unc(path) -> str:
    """Return *path* with a mapped drive letter replaced by its UNC share.

    ``X:\\POST RECEIVED`` -> ``\\\\inspiredenergysolutions.local\\DFS\\Public\\!CC\\POST RECEIVED``.
    Drive letters are matched case-insensitively and ``/`` separators after
    the drive are accepted. Anything else (an unmapped drive, a relative or
    UNC path, an empty string) comes back as given, as a string.
    """
    text = os.fspath(path) if path is not None else ""
    if len(text) < 2 or text[1] != ":" or (len(text) > 2 and text[2] not in "\\/"):
        return text
    share = DRIVE_MAP.get(text[0].upper())
    if share is None:
        return text
    rest = text[3:].replace("/", "\\")
    return share + "\\" + rest if rest else share


def from_unc(path, like) -> str:
    """Return *path* spelled with *like*'s drive letter when *like* is a mapped drive.

    The inverse of ``to_unc`` for a path built under ``to_unc(like)``: a
    caller that records the drive-letter form (a database column other
    processes match on) can file through the share and still record what it
    was given. Returns *path* unchanged when it does not start with
    ``to_unc(like)`` or *like* was not translated.
    """
    text = os.fspath(path)
    original = os.fspath(like) if like is not None else ""
    unc_root = to_unc(original)
    if unc_root == original or not text.lower().startswith(unc_root.lower()):
        return text
    tail = text[len(unc_root):]
    if tail and tail[0] not in "\\/":
        return text
    return original.rstrip("\\/") + tail if tail else original
