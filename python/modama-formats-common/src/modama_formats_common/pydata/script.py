"""Python scripts: what the source says about itself, parsed with `ast`, never executed.

The shebang, the module docstring, the module-level dunder names assigned a
literal (PEP 8, "Module Level Dunder Names": `__version__`, `__author__` …)
and the imported module names (spec formats/pydata, "A Python script is
described by its source, never run").
"""

import ast

from .values import Walk

# 19,419 .py files in the October listing, 0.3 GB, none over 5 MB; a larger
# file is generated or data, not a script to describe
MAX_SOURCE = 1 << 20


def dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def imports(tree: ast.Module) -> list[str]:
    """The imported module names in the order first found, as written (relative ones with their dots)."""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append("." * node.level + (node.module or ""))
    return list(dict.fromkeys(names))


def assigned(tree: ast.Module):
    """(name, value) of each module-level assignment of a literal to a dunder name."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and dunder(target.id):
            try:
                yield target.id, ast.literal_eval(value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                continue  # not a literal: an expression to run


def described(path: str) -> tuple[dict, dict, list[str]]:
    """original_metadata, mapped_metadata and the summary line of a script."""
    with open(path, "rb", buffering=0) as f:
        source = f.read(MAX_SOURCE + 1)
    walk = Walk()
    first = source.split(b"\n", 1)[0]
    if first.startswith(b"#!"):
        walk.add("shebang", first.rstrip(b"\r").decode("utf-8", "replace"))
    if len(source) > MAX_SOURCE:
        return walk.values, {"not_parsed": f"larger than {MAX_SOURCE} bytes"}, []
    try:
        # From bytes: the parser honours the encoding declaration (PEP 263)
        tree = ast.parse(source)
    except SyntaxError as e:  # Python 2, or not Python
        return walk.values, {"not_parsed": f"{e.msg} (line {e.lineno})"}, []
    except (ValueError, MemoryError, RecursionError) as e:  # NUL bytes, deep nesting
        return walk.values, {"not_parsed": str(e) or type(e).__name__}, []
    docstring = ast.get_docstring(tree, clean=False)
    if docstring is not None:
        walk.add("docstring", docstring)
    for name, value in assigned(tree):
        walk.add(name, value)
    walk.add("imports", imports(tree))
    lines = (docstring or "").strip().splitlines()
    return walk.values, {}, lines[:1]
