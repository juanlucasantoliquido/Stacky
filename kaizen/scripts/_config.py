#!/usr/bin/env python3
"""Lector YAML mínimo (subset) — stdlib pura, sin PyYAML.

Soporta lo que usan los archivos de config de Kaizen:
  - comentarios con '#'
  - mapeos anidados por indentación
  - escalares: int, float, true/false, null, y strings (con o sin comillas)
  - listas de escalares (líneas '- item')

No es un parser YAML completo; es predecible y suficiente para config/*.yaml propios.
Portabilidad: no importa nada externo ni el proyecto padre.
"""
from __future__ import annotations

from pathlib import Path


def _coerce(value: str):
    v = value.strip()
    if v == "" or v == "~" or v.lower() == "null":
        return None
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if len(v) >= 2 and ((v[0], v[-1]) in (('"', '"'), ("'", "'"))):
        return v[1:-1]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _strip_comment(line: str) -> str:
    in_s = None
    out = []
    for ch in line:
        if in_s:
            out.append(ch)
            if ch == in_s:
                in_s = None
        elif ch in ("'", '"'):
            in_s = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out)


def load_yaml(path: str | Path) -> dict:
    path = Path(path)
    root: dict = {}
    # Cada frame: {"indent": int, "obj": dict|list, "owner": dict|None, "key": str|None}
    stack: list[dict] = [{"indent": -1, "obj": root, "owner": None, "key": None}]

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        while len(stack) > 1 and indent <= stack[-1]["indent"]:
            stack.pop()
        frame = stack[-1]
        parent = frame["obj"]

        if content.startswith("- "):
            # El contenedor actual debe ser una lista; si es un dict vacío recién creado,
            # lo convertimos a lista en su dueño.
            if isinstance(parent, dict):
                if parent:
                    raise ValueError("lista mezclada con claves en %s: %r" % (path, raw))
                new_list: list = []
                if frame["owner"] is not None:
                    frame["owner"][frame["key"]] = new_list
                else:
                    raise ValueError("lista en raíz no soportada en %s" % path)
                frame["obj"] = new_list
                parent = new_list
            parent.append(_coerce(content[2:]))
            continue

        if ":" not in content:
            raise ValueError("línea sin clave en %s: %r" % (path, raw))
        key, _, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()

        if not isinstance(parent, dict):
            raise ValueError("clave dentro de una lista en %s: %r" % (path, raw))

        if rest == "":
            child: dict = {}
            parent[key] = child
            stack.append({"indent": indent, "obj": child, "owner": parent, "key": key})
        else:
            parent[key] = _coerce(rest)

    return root
