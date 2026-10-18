"""Minimal reader for KiCad S-expression files (read-only; never re-serializes).

KiCad files are parsed only to inspect symbols, footprints and library tables.
All writes to native files go through KiCad itself (CLI or pcbnew API).
"""

from pathlib import Path


class Symbol(str):
    """Unquoted atom, distinguishable from a quoted string."""


class ParseError(ValueError):
    pass


def parse(text):
    stack = [[]]
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            stack.append([])
            i += 1
        elif c == ")":
            if len(stack) == 1:
                raise ParseError("Unbalanced ')' at offset %d" % i)
            node = stack.pop()
            stack[-1].append(node)
            i += 1
        elif c == '"':
            i += 1
            out = []
            while True:
                if i >= n:
                    raise ParseError("Unterminated string")
                c = text[i]
                if c == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    out.append(c)
                    i += 1
            stack[-1].append("".join(out))
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            stack[-1].append(Symbol(text[i:j]))
            i = j
    if len(stack) != 1:
        raise ParseError("Unbalanced '(' (missing %d closing)" % (len(stack) - 1))
    if len(stack[0]) != 1 or not isinstance(stack[0][0], list):
        raise ParseError("Expected exactly one top-level expression")
    return stack[0][0]


def load(path):
    return parse(Path(path).read_text(encoding="utf-8"))


def head(node):
    return node[0] if isinstance(node, list) and node else None


def children(node, name):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]


def child(node, name):
    found = children(node, name)
    return found[0] if found else None


def value(node, name, default=None):
    c = child(node, name)
    return c[1] if c is not None and len(c) > 1 else default


def properties(node):
    """KiCad (property "Name" "Value" ...) pairs of one symbol/footprint."""
    return {
        p[1]: p[2] for p in children(node, "property") if len(p) > 2 and isinstance(p[2], str)
    }


def flag(node, name):
    """Read yes/no flags such as (in_bom yes) or bare (dnp)."""
    c = child(node, name)
    if c is None:
        return None
    return len(c) == 1 or c[1] in ("yes", "true")
