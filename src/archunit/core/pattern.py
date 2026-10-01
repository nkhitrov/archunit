"""Module name patterns in the Java ArchUnit style.

Syntax (segments are separated by dots):

- ``shop.di`` — exactly the module ``shop.di``;
- ``shop..`` — ``shop`` and all of its descendants at any depth (Java: ``com.shop..``);
- ``..domain..`` — any module whose name contains the segment ``domain``;
- ``shop.features.*`` — exactly one segment in place of ``*`` (``shop.features.core``, not ``shop.features.core.x``);
- ``shop.features.*..`` — direct children of ``shop.features`` and everything below them.

Unlike pytest-archon, where ``app*`` is a string prefix (and also matches ``application``), matching is
done segment by segment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ANY_SEGMENTS = "**"  # internal representation of ``..``
_ANY_SEGMENT = "*"
_SEGMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _parse(source: str) -> tuple[str, ...]:
    if not source or _ANY_SEGMENTS in source:
        raise ValueError(f"invalid package pattern: {source!r}")
    parts = source.replace("..", f".{_ANY_SEGMENTS}.").split(".")
    if parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    if not parts or any(part != _ANY_SEGMENTS and part != _ANY_SEGMENT and not _SEGMENT.fullmatch(part) for part in parts):
        raise ValueError(f"invalid package pattern: {source!r}")
    if any(a == b == _ANY_SEGMENTS for a, b in zip(parts, parts[1:])):
        raise ValueError(f"invalid package pattern: {source!r}")
    return tuple(parts)


def _match(tokens: tuple[str, ...], segments: tuple[str, ...]) -> bool:
    # reachable[j]: the tokens seen so far cover the first j segments
    reachable = [True] + [False] * len(segments)
    for token in tokens:
        if token == _ANY_SEGMENTS:
            for j in range(1, len(reachable)):
                reachable[j] = reachable[j] or reachable[j - 1]
            continue
        nxt = [False] * len(reachable)
        for j in range(1, len(reachable)):
            nxt[j] = reachable[j - 1] and (token == _ANY_SEGMENT or token == segments[j - 1])
        reachable = nxt
    return reachable[-1]


@dataclass(frozen=True, slots=True)
class PackagePattern:
    """A compiled pattern. Invalid syntax raises ``ValueError`` on creation."""

    source: str
    _tokens: tuple[str, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_tokens", _parse(self.source))

    def matches(self, module_name: str) -> bool:
        """True if the fully qualified module name matches the pattern."""
        return _match(self._tokens, tuple(module_name.split(".")))
