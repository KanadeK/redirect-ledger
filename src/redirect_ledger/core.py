"""A strict exact-path redirect graph, independent of any hosting provider."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

MAX_BYTES = 16 * 1024 * 1024
MAX_RULES = 100_000
MAX_PATH = 4096
STATUSES = frozenset({301, 302, 303, 307, 308})
UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
PATH_CHARS = UNRESERVED | frozenset("/%!$&'()+,;=:@")
PERCENT = re.compile(r"%([0-9a-fA-F]{2})")


class InputError(ValueError):
    """The input cannot be interpreted under the documented exact-path model."""


@dataclass(frozen=True)
class Rule:
    source: str
    target: str
    status: int
    row: int = 0


@dataclass(frozen=True)
class Resolution:
    terminal: str | None
    hops: int | None
    cycle_id: str | None
    statuses: frozenset[int]


def local_path(value: str) -> str:
    """Canonicalize unreserved escapes, retaining case and trailing slash."""
    if not isinstance(value, str) or not value or len(value) > MAX_PATH:
        raise InputError("path must contain 1..4096 characters")
    if any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise InputError("paths must use printable ASCII; percent-encode UTF-8 characters")
    if not value.startswith("/") or "//" in value:
        raise InputError("path must start with one slash and contain no repeated slash")
    if any(char in value for char in "\\?#*[]{}"):
        raise InputError("query, fragment, backslash, glob and bracket syntax are unsupported")
    if any(char not in PATH_CHARS for char in value):
        raise InputError("unsupported URL path character")
    if "%" in PERCENT.sub("", value):
        raise InputError("invalid percent escape")

    def replace(match: re.Match[str]) -> str:
        code = int(match.group(1), 16)
        if code < 33 or code == 127 or chr(code) in "/\\%":
            raise InputError("encoded separator, control, whitespace or percent is unsupported")
        char = chr(code)
        return char if char in UNRESERVED else f"%{code:02X}"

    value = PERCENT.sub(replace, value)
    if any(segment in {".", ".."} for segment in value.split("/")):
        raise InputError("dot path segments are unsupported")
    return value


def target_url(value: str) -> str:
    if value.startswith("/"):
        return local_path(value)
    if len(value) > MAX_PATH or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise InputError("target must use printable ASCII and contain at most 4096 characters")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise InputError("invalid target URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "?" in value
        or "#" in value
        or "\\" in value
        or port == 0
    ):
        raise InputError(
            "target must be a root path or HTTP(S) URL without credentials/query/fragment"
        )
    host = parsed.hostname.lower()
    if ":" not in host and not re.fullmatch(r"[a-z0-9.-]+", host):
        raise InputError("invalid ASCII hostname")
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority += f":{port}"
    return urlunsplit((parsed.scheme, authority, local_path(parsed.path or "/"), "", ""))


def read_text(path: str | Path) -> str:
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise InputError("input exceeds 16 MiB")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("input is not UTF-8") from exc


def parse_rules(text: str) -> list[Rule]:
    """Parse CSV with an exact schema; ambiguous duplicate sources are fatal."""
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    rules: list[Rule] = []
    seen: dict[str, int] = {}
    try:
        if next(reader, None) != ["source", "target", "status"]:
            raise InputError("CSV header must be exactly source,target,status")
        for fields in reader:
            row = reader.line_num
            if len(rules) >= MAX_RULES:
                raise InputError("input exceeds 100000 rules")
            if len(fields) != 3:
                raise InputError(f"CSV record ending on line {row}: expected three fields")
            try:
                source, target = local_path(fields[0]), target_url(fields[1])
                if fields[2] not in {str(status) for status in STATUSES}:
                    raise InputError("status must be 301, 302, 303, 307 or 308")
                if source in seen:
                    raise InputError(f"duplicate source; first defined on line {seen[source]}")
            except InputError as exc:
                raise InputError(f"CSV record ending on line {row}: {exc}") from exc
            seen[source] = row
            rules.append(Rule(source, target, int(fields[2]), row))
    except csv.Error as exc:
        raise InputError(f"invalid CSV near line {reader.line_num}") from exc
    if not rules:
        raise InputError("redirect map contains no rules")
    return rules


def parse_inventory(text: str) -> set[str]:
    paths: set[str] = set()
    for row, line in enumerate(text.splitlines(), 1):
        if len(paths) >= MAX_RULES:
            raise InputError("inventory exceeds 100000 paths")
        if not line:
            continue
        try:
            path = local_path(line)
        except InputError as exc:
            raise InputError(f"inventory line {row}: {exc}") from exc
        if path in paths:
            raise InputError(f"inventory line {row}: duplicate canonical path")
        paths.add(path)
    if not paths:
        raise InputError("inventory contains no paths")
    return paths


def resolve(rules: dict[str, Rule]) -> tuple[dict[str, Resolution], dict[str, list[str]]]:
    """Resolve a functional graph in O(n), with no recursion or expanded traces."""
    cache: dict[str, Resolution] = {}
    cycles: dict[str, list[str]] = {}
    for root in sorted(rules):
        if root in cache:
            continue
        trail: list[str] = []
        positions: dict[str, int] = {}
        node = root
        while node in rules and node not in cache and node not in positions:
            positions[node] = len(trail)
            trail.append(node)
            node = rules[node].target
        if node in positions:
            begin = positions[node]
            cycle = trail[begin:]
            smallest = min(range(len(cycle)), key=cycle.__getitem__)
            cycle = cycle[smallest:] + cycle[:smallest]
            identity = cycle[0]
            cycles[identity] = cycle
            base = Resolution(None, None, identity, frozenset(rules[p].status for p in cycle))
            for member in cycle:
                cache[member] = base
            trail = trail[:begin]
        else:
            base = cache.get(node, Resolution(node, 0, None, frozenset()))
        for member in reversed(trail):
            base = Resolution(
                base.terminal,
                base.hops + 1 if base.hops is not None else None,
                base.cycle_id,
                base.statuses | {rules[member].status},
            )
            cache[member] = base
    return cache, cycles


def audit(rules: list[Rule], inventory: set[str] | None = None) -> dict:
    """Return deterministic findings and a conservative complete-map plan."""
    graph: dict[str, Rule] = {}
    for rule in rules:
        source, target = local_path(rule.source), target_url(rule.target)
        if source in graph or rule.status not in STATUSES:
            raise InputError("duplicate source or unsupported status in rules")
        graph[source] = Rule(source, target, rule.status, rule.row)
    if not graph or len(graph) > MAX_RULES:
        raise InputError("expected 1..100000 rules")
    if inventory is not None:
        inventory = {local_path(path) for path in inventory}
        if not inventory:
            raise InputError("inventory contains no paths")
    resolutions, cycles = resolve(graph)
    findings = [
        {"severity": "error", "code": "cycle", "source": key, "members": cycles[key]}
        for key in sorted(cycles)
    ]
    records = []
    for source in sorted(graph):
        rule, result = graph[source], resolutions[source]
        terminal = result.terminal
        internal = terminal is not None and terminal.startswith("/")
        missing = inventory is not None and internal and terminal not in inventory
        if missing:
            findings.append(
                {
                    "severity": "error",
                    "code": "missing_terminal",
                    "source": source,
                    "terminal": terminal,
                }
            )
        if inventory is not None and source in inventory:
            findings.append({"severity": "error", "code": "inventory_shadowed", "source": source})
        if result.hops is not None and result.hops > 1:
            findings.append(
                {"severity": "warning", "code": "chain", "source": source, "hops": result.hops}
            )
        shorten = (
            result.hops is not None
            and result.hops > 1
            and result.statuses in {frozenset({301}), frozenset({308})}
        )
        records.append(
            {
                "source": source,
                "target": rule.target,
                "status": rule.status,
                "line": rule.row,
                "terminal": terminal,
                "hops": result.hops,
                "cycle_id": result.cycle_id,
                "outcome": "cycle"
                if result.cycle_id is not None
                else "missing"
                if missing
                else "external_unchecked"
                if not internal
                else "present"
                if inventory is not None
                else "internal_unchecked",
                "plan_target": terminal if shorten else rule.target,
                "shortened": shorten,
            }
        )
    errors = sum(item["severity"] == "error" for item in findings)
    return {
        "schema_version": 1,
        "model": "exact-path-no-query",
        "inventory_checked": inventory is not None,
        "summary": {
            "rules": len(records),
            "errors": errors,
            "warnings": len(findings) - errors,
            "shortenable": sum(item["shortened"] for item in records),
        },
        "cycles": cycles,
        "findings": findings,
        "rules": records,
    }


def plan_csv(report: dict) -> str:
    if report["summary"]["errors"]:
        raise InputError("plan refused: resolve all audit errors first")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["source", "target", "status"])
    for rule in report["rules"]:
        writer.writerow([rule["source"], rule["plan_target"], rule["status"]])
    return output.getvalue()


def write_new(path: str | Path, text: str) -> None:
    """Never truncate an existing input, symlink destination, or prior report."""
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
