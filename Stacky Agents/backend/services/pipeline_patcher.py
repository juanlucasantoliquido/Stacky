"""services/pipeline_patcher.py — Plan 250 F0/F1/F5(puro).

Motor de EDICION QUIRURGICA de un pipeline YAML que YA EXISTE.

Tesis del plan (medida, no supuesta): `parse_ado_yaml -> to_ado_yaml` sobre el corpus
dorado borra 337/337 comentarios y el 48% de las lineas. Por lo tanto el editor NO
regenera: localiza nodos con `yaml.compose()` (que da marcas de linea) y hace splice
de lineas sobre el texto original, dejando byte-identico todo lo que no toco.

PURO: sin red, sin LLM, sin I/O, sin Flask. `build_anchor_index` y `apply_ops` NUNCA
lanzan: devuelven errores en español.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import yaml

from services.cicd_task_catalog import is_allowed, validate_inputs

PATCHER_VERSION = "250.1"
MAX_YAML_BYTES = 512 * 1024      # mismo limite que cicd_semantic_rules.MAX_YAML_BYTES
MAX_OPS_PER_PLAN = 12            # techo duro: un patch no es una reescritura
MAX_TEXT_LEN = 200               # display_name / valores de inputs: 1 linea, <=200 chars

_ROOT_KEYS = ("trigger", "pr", "schedules", "variables", "pool", "stages", "jobs", "steps")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


# ── Contratos ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Anchor:
    path: str                    # "stages[0].jobs[0].steps"
    kind: str                    # "seq" | "map" | "scalar"
    key_line: Optional[int]      # linea 0-based de la clave que abre el bloque; None en items
    start_line: int              # 0-based, primera linea del VALOR
    end_line: int                # 0-based INCLUSIVE, fin EFECTIVO (§2.3)
    key_col: int                 # columna de las claves hijas
    dash_col: Optional[int]      # columna del guion si el nodo vive dentro de una secuencia
    item_paths: tuple = ()       # para seq: paths de sus items, en orden
    lead_line: int = -1          # 0-based: primera linea del bloque de comentarios/blancos
                                 # que INTRODUCE a este nodo (== start_line si no hay).
                                 # Sin esto, borrar un paso deja huerfano el comentario que
                                 # lo presentaba: §2.3 se lo saca al item anterior pero
                                 # tampoco se lo da al siguiente.


@dataclass(frozen=True)
class EditOp:
    kind: str                    # "insert_after" | "insert_before" | "replace" | "delete"
    anchor_path: str
    lines: tuple                 # lineas YA indentadas; () para "delete"
    reason: str                  # español, 1 linea


@dataclass(frozen=True)
class Hunk:
    start_line: int              # 1-based sobre el ORIGINAL
    end_line: int                # 1-based INCLUSIVE; == start_line-1 si es insercion pura
    before: tuple
    after: tuple
    reason: str


@dataclass(frozen=True)
class PatchResult:
    ok: bool
    text: str                    # YAML resultante; == entrada si ok is False
    hunks: tuple
    errors: tuple


# ── Indice de anclajes ───────────────────────────────────────────────────────

def _fin_efectivo(lines: list, start: int, end_exclusive: int) -> int:
    """§2.3 — ultima linea con contenido real del nodo.

    `end_mark.line` de un item de secuencia es EXCLUSIVO y se traga las lineas en
    blanco y el comentario que introduce al item SIGUIENTE. Devolverlas como parte
    del item huerfana ese comentario sobre el paso equivocado (corrupcion silenciosa:
    el YAML sigue siendo valido).
    """
    hi = min(max(end_exclusive, start + 1), len(lines))
    for i in range(hi - 1, start - 1, -1):
        texto = lines[i].strip()
        if texto and not texto.startswith("#"):
            return i
    return min(start, max(len(lines) - 1, 0))


def _map_get(node, key: str):
    """(key_node, value_node) de una clave de un MappingNode, o (None, None)."""
    if not isinstance(node, yaml.MappingNode):
        return None, None
    for k, v in node.value:
        if isinstance(k, yaml.ScalarNode) and k.value == key:
            return k, v
    return None, None


def _first_child_col(node) -> int:
    """Columna de las CLAVES hijas.

    En una secuencia NO es `node.start_mark.column` (que es la del guion): es la del
    primer campo del primer item. Confundirlas emite el bloque nuevo con las claves de
    continuacion 2 columnas a la izquierda y produce un YAML invalido — que
    `scan_unsupported` devuelve como `()` en vez de fallar ruidosamente.
    """
    if isinstance(node, yaml.MappingNode) and node.value:
        return node.value[0][0].start_mark.column
    if isinstance(node, yaml.SequenceNode) and node.value:
        return _first_child_col(node.value[0])
    return node.start_mark.column


def _dash_col_de(lines: list, node, errores: list, path: str) -> Optional[int]:
    """Columna del guion de un item de secuencia, DERIVADA DEL ARCHIVO (§2.4).

    No se calcula como `start_mark.column - 2` (que falla con `-   task:`), sino
    mirando el texto crudo que precede a la primera clave del item. Si ahi no hay un
    guion (caso `-` solo en su linea, con las claves abajo) se devuelve un error
    accionable: NUNCA se adivina la indentacion.
    """
    linea = node.start_mark.line
    col = _first_child_col(node)
    if linea >= len(lines):
        errores.append("no se pudo ubicar el item '%s' en el texto" % path)
        return None
    prefijo = lines[linea][:col].rstrip()
    if not prefijo.endswith("-"):
        errores.append(
            "el item '%s' (linea %d) tiene el guion en una linea propia o con un "
            "formato no soportado: %r. No se adivina la indentacion; reescribi el "
            "item como '- clave: valor' para poder editarlo."
            % (path, linea + 1, lines[linea])
        )
        return None
    return len(prefijo) - 1


def _lead_line(lines: list, start: int, piso: int) -> int:
    """Primera linea del bloque contiguo de comentarios/blancos que introduce al nodo.

    Se corta en `piso` (fin efectivo del hermano anterior + 1, o la linea de la clave
    que abre la lista + 1): nunca se roba lineas de otro nodo.
    """
    i = start
    while i - 1 >= piso and i - 1 >= 0:
        texto = lines[i - 1].strip() if i - 1 < len(lines) else ""
        if texto and not texto.startswith("#"):
            break
        i -= 1
    return i


def _anchor(path: str, node, key_node, lines: list, dash_col: Optional[int],
            item_paths: tuple = (), lead_line: Optional[int] = None) -> Anchor:
    if isinstance(node, yaml.SequenceNode):
        kind = "seq"
    elif isinstance(node, yaml.MappingNode):
        kind = "map"
    else:
        kind = "scalar"
    start = node.start_mark.line
    return Anchor(
        path=path,
        kind=kind,
        key_line=(key_node.start_mark.line if key_node is not None else None),
        start_line=start,
        end_line=_fin_efectivo(lines, start, node.end_mark.line),
        key_col=(_first_child_col(node) if kind != "scalar"
                 else (key_node.start_mark.column if key_node is not None
                       else node.start_mark.column)),
        dash_col=dash_col,
        item_paths=item_paths,
        lead_line=(lead_line if lead_line is not None
                   else (key_node.start_mark.line if key_node is not None else start)),
    )


def _index_steps(path: str, node, key_node, lines: list, idx: dict, errores: list) -> None:
    """Indexa un bloque `steps` (la secuencia, cada paso y sus `inputs`)."""
    if not isinstance(node, yaml.SequenceNode):
        return
    item_paths = tuple("%s[%d]" % (path, k) for k in range(len(node.value)))
    dash_seq = None
    piso = (key_node.start_mark.line + 1) if key_node is not None else node.start_mark.line
    for k, paso in enumerate(node.value):
        d = _dash_col_de(lines, paso, errores, item_paths[k])
        if dash_seq is None:
            dash_seq = d
        lead = _lead_line(lines, paso.start_mark.line, piso)
        idx[item_paths[k]] = _anchor(item_paths[k], paso, None, lines, d, lead_line=lead)
        piso = idx[item_paths[k]].end_line + 1
        kn, inputs = _map_get(paso, "inputs")
        if isinstance(inputs, yaml.MappingNode):
            p_in = "%s.inputs" % item_paths[k]
            idx[p_in] = _anchor(p_in, inputs, kn, lines, None)
            for ck, cv in inputs.value:
                if not isinstance(ck, yaml.ScalarNode):
                    continue
                p_ck = "%s.%s" % (p_in, ck.value)
                idx[p_ck] = _anchor(p_ck, cv, ck, lines, None)
    idx[path] = _anchor(path, node, key_node, lines, dash_seq, item_paths)


def _index_job(path: str, job, lines: list, idx: dict, errores: list) -> None:
    kn, steps = _map_get(job, "steps")
    if isinstance(steps, yaml.SequenceNode):
        _index_steps("%s.steps" % path, steps, kn, lines, idx, errores)
    kn, strategy = _map_get(job, "strategy")
    if not isinstance(strategy, yaml.MappingNode):
        return
    p_st = "%s.strategy" % path
    idx[p_st] = _anchor(p_st, strategy, kn, lines, None)
    kn, run_once = _map_get(strategy, "runOnce")
    if not isinstance(run_once, yaml.MappingNode):
        return
    p_ro = "%s.runOnce" % p_st
    idx[p_ro] = _anchor(p_ro, run_once, kn, lines, None)
    kn, deploy = _map_get(run_once, "deploy")
    if not isinstance(deploy, yaml.MappingNode):
        return
    p_dep = "%s.deploy" % p_ro
    idx[p_dep] = _anchor(p_dep, deploy, kn, lines, None)
    kn, dsteps = _map_get(deploy, "steps")
    if isinstance(dsteps, yaml.SequenceNode):
        _index_steps("%s.steps" % p_dep, dsteps, kn, lines, idx, errores)


def _index_jobs(path: str, node, lines: list, idx: dict, errores: list,
                key_node=None) -> None:
    if not isinstance(node, yaml.SequenceNode):
        return
    piso = (key_node.start_mark.line + 1) if key_node is not None else node.start_mark.line
    for j, job in enumerate(node.value):
        p_job = "%s[%d]" % (path, j)
        d = _dash_col_de(lines, job, errores, p_job)
        lead = _lead_line(lines, job.start_mark.line, piso)
        idx[p_job] = _anchor(p_job, job, None, lines, d, lead_line=lead)
        piso = idx[p_job].end_line + 1
        _index_job(p_job, job, lines, idx, errores)


def build_anchor_index(yaml_text: str) -> tuple:
    """({path: Anchor}, errores). Usa `yaml.compose()`; NUNCA regex para estructura.

    Cobertura EXACTA (regla 1-bis del plan): claves de raiz, `trigger.paths[.include]`,
    stages/jobs/steps (incluido el camino `strategy.runOnce.deploy.steps` de un
    `deployment:`), los pipelines job-level y step-level, y — unica excepcion hacia
    abajo — `<step>.inputs` y `<step>.inputs.<clave>`, que `set_task_input` necesita
    para cambiar UNA linea sin re-renderizar el paso entero.

    Jamas lanza.
    """
    errores: list = []
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return {}, ("el YAML esta vacio",)
    if len(yaml_text) > MAX_YAML_BYTES:
        return {}, ("el YAML supera %d KB: fuera del rango soportado, no se analizo."
                    % (MAX_YAML_BYTES // 1024),)
    try:
        root = yaml.compose(yaml_text)
    except yaml.YAMLError as e:
        return {}, ("el YAML no se pudo interpretar: %s" % str(e).replace("\n", " "),)
    if not isinstance(root, yaml.MappingNode):
        return {}, ("el YAML no es un mapa en su raiz: no hay nada direccionable",)

    lines = yaml_text.splitlines()
    idx: dict = {}

    for clave in _ROOT_KEYS:
        kn, vn = _map_get(root, clave)
        if vn is None:
            continue
        if clave == "steps":
            _index_steps("steps", vn, kn, lines, idx, errores)
            continue
        idx[clave] = _anchor(clave, vn, kn, lines, None)

    kn, trigger = _map_get(root, "trigger")
    if isinstance(trigger, yaml.MappingNode):
        pk, paths = _map_get(trigger, "paths")
        if isinstance(paths, yaml.MappingNode):
            idx["trigger.paths"] = _anchor("trigger.paths", paths, pk, lines, None)
            ik, include = _map_get(paths, "include")
            if include is not None:
                idx["trigger.paths.include"] = _anchor(
                    "trigger.paths.include", include, ik, lines, None)

    stages_key, stages = _map_get(root, "stages")
    if isinstance(stages, yaml.SequenceNode):
        piso = ((stages_key.start_mark.line + 1) if stages_key is not None
                else stages.start_mark.line)
        for i, stage in enumerate(stages.value):
            p_stage = "stages[%d]" % i
            d = _dash_col_de(lines, stage, errores, p_stage)
            lead = _lead_line(lines, stage.start_mark.line, piso)
            idx[p_stage] = _anchor(p_stage, stage, None, lines, d, lead_line=lead)
            piso = idx[p_stage].end_line + 1
            jk, jobs = _map_get(stage, "jobs")
            if isinstance(jobs, yaml.SequenceNode):
                p_jobs = "%s.jobs" % p_stage
                _index_jobs(p_jobs, jobs, lines, idx, errores, key_node=jk)
                idx[p_jobs] = _anchor(
                    p_jobs, jobs, jk, lines,
                    _dash_col_de(lines, jobs.value[0], [], p_jobs) if jobs.value else None,
                    item_paths=tuple("%s[%d]" % (p_jobs, j) for j in range(len(jobs.value))))
        idx["stages"] = _anchor(
            "stages", stages, stages_key, lines,
            _dash_col_de(lines, stages.value[0], [], "stages") if stages.value else None,
            item_paths=tuple("stages[%d]" % i for i in range(len(stages.value))))

    jobs_key, jobs = _map_get(root, "jobs")
    if isinstance(jobs, yaml.SequenceNode):
        _index_jobs("jobs", jobs, lines, idx, errores, key_node=jobs_key)
        idx["jobs"] = _anchor(
            "jobs", jobs, jobs_key, lines,
            _dash_col_de(lines, jobs.value[0], [], "jobs") if jobs.value else None,
            item_paths=tuple("jobs[%d]" % j for j in range(len(jobs.value))))

    return idx, tuple(errores)


# ── Renderizado de UN bloque (nunca del documento) ───────────────────────────

def render_block(doc: dict, *, key_col: int, dash_col: Optional[int]) -> tuple:
    """dict de UN paso/job/stage -> lineas ya indentadas.

    Usa `yaml.safe_dump(sort_keys=False)` sobre ESE dict solo y re-indenta. Nunca
    toca el documento completo, asi que no puede borrar nada de lo que ya existe.
    """
    crudo = yaml.safe_dump(
        doc, sort_keys=False, default_flow_style=False, allow_unicode=True, width=10 ** 6,
    ).rstrip("\n").splitlines()
    if not crudo:
        return ()
    if dash_col is None:
        return tuple((" " * key_col + l) if l.strip() else "" for l in crudo)
    salida = [" " * dash_col + "- " + crudo[0]]
    salida += [(" " * key_col + l) if l.strip() else "" for l in crudo[1:]]
    return tuple(salida)


# ── Aplicacion de ops ────────────────────────────────────────────────────────

def _rango_de(op: EditOp, anchor: Anchor) -> tuple:
    """(lo, hi, es_insercion) — 0-based; para inserciones lo == hi == punto."""
    if op.kind == "insert_after":
        return anchor.end_line + 1, anchor.end_line + 1, True
    if op.kind == "insert_before":
        # arriba del comentario que INTRODUCE al nodo, no entre el comentario y el nodo
        return anchor.lead_line, anchor.lead_line, True
    if op.kind == "delete":
        # el comentario que presenta al paso se va CON el paso (si no, queda huerfano
        # sobre el paso equivocado: corrupcion silenciosa que el YAML no denuncia)
        return anchor.lead_line, anchor.end_line, False
    inicio = anchor.key_line if anchor.key_line is not None else anchor.start_line
    return inicio, anchor.end_line, False


def _solapan(a: tuple, b: tuple) -> bool:
    (lo_a, hi_a, ins_a), (lo_b, hi_b, ins_b) = a, b
    if ins_a and ins_b:
        return False
    if ins_a:
        return lo_b <= lo_a <= hi_b
    if ins_b:
        return lo_a <= lo_b <= hi_a
    return lo_a <= hi_b and lo_b <= hi_a


def apply_ops(yaml_text: str, ops: tuple) -> PatchResult:
    """Aplica las ops de abajo hacia arriba (indices estables). PURA. Nunca lanza."""
    texto = yaml_text if isinstance(yaml_text, str) else ""
    ops = tuple(ops or ())

    if len(texto) > MAX_YAML_BYTES:
        return PatchResult(False, texto, (), (
            "el YAML supera %d KB: fuera del rango soportado, no se procesa."
            % (MAX_YAML_BYTES // 1024),))
    if len(ops) > MAX_OPS_PER_PLAN:
        return PatchResult(False, texto, (), (
            "el plan tiene %d cambios y el maximo es %d: partilo en dos ediciones."
            % (len(ops), MAX_OPS_PER_PLAN),))

    indice, errores = build_anchor_index(texto)
    if errores:
        return PatchResult(False, texto, (), tuple(errores))
    if not ops:
        return PatchResult(True, texto, (), ())

    disponibles = sorted(indice)
    resueltas: list = []
    fallas: list = []
    for op in ops:
        if op.kind not in ("insert_after", "insert_before", "replace", "delete"):
            fallas.append("tipo de cambio desconocido: %r" % op.kind)
            continue
        anchor = indice.get(op.anchor_path)
        if anchor is None:
            fallas.append(
                "no existe el punto '%s' en este pipeline. Puntos disponibles: %s"
                % (op.anchor_path, ", ".join(disponibles)))
            continue
        resueltas.append((op, anchor, _rango_de(op, anchor)))
    if fallas:
        return PatchResult(False, texto, (), tuple(fallas))

    for i in range(len(resueltas)):
        for j in range(i + 1, len(resueltas)):
            if _solapan(resueltas[i][2], resueltas[j][2]):
                return PatchResult(False, texto, (), (
                    "los cambios sobre '%s' y '%s' se solapan: un patch a medias es "
                    "peor que ninguno, no se aplica ninguno."
                    % (resueltas[i][0].anchor_path, resueltas[j][0].anchor_path),))

    lineas = texto.splitlines()
    hunks: list = []
    for op, _anchor_, (lo, hi, es_ins) in sorted(
            resueltas, key=lambda r: (r[2][0], r[2][1]), reverse=True):
        if es_ins:
            antes: tuple = ()
            lineas[lo:lo] = list(op.lines)
            hunks.append(Hunk(lo + 1, lo, antes, tuple(op.lines), op.reason))
        else:
            antes = tuple(lineas[lo:hi + 1])
            lineas[lo:hi + 1] = list(op.lines)
            hunks.append(Hunk(lo + 1, hi + 1, antes, tuple(op.lines), op.reason))

    salida = "\n".join(lineas)
    if texto.endswith("\n"):
        salida += "\n"
    hunks.sort(key=lambda h: h.start_line)
    return PatchResult(True, salida, tuple(hunks), ())


# ── F1 — verbos de edicion cerrados ──────────────────────────────────────────

EDIT_VERBS = (
    "add_step",           # agregar un paso `- task:` a un job existente
    "remove_step",        # quitar un paso por su ref o indice
    "move_step",          # reordenar un paso dentro del mismo job
    "set_task_input",     # cambiar/agregar un `inputs.<clave>` de un paso existente
    "add_stage",          # agregar un stage completo antes o despues de otro
    "set_trigger_paths",  # reemplazar el bloque trigger.paths.include
    "set_schedule",       # agregar/reemplazar el bloque schedules
)

_POSITIONS = ("before", "after", "end")


@dataclass(frozen=True)
class EditIntent:
    verb: str
    target_path: str = ""
    anchor_ref: Optional[str] = None
    position: str = "end"
    task_ref: Optional[str] = None
    inputs: dict = field(default_factory=dict)
    display_name: str = ""
    values: tuple = ()
    notes: tuple = ()


def _texto_de_una_linea(valor, etiqueta: str, errores: list) -> None:
    s = str(valor)
    if "\n" in s or "\r" in s:
        errores.append("%s debe ser una sola linea (sin saltos de linea)" % etiqueta)
    if len(s) > MAX_TEXT_LEN:
        errores.append("%s supera los %d caracteres" % (etiqueta, MAX_TEXT_LEN))
    if _CONTROL_RE.search(s):
        errores.append("%s tiene caracteres de control no permitidos" % etiqueta)


def _ref_de_paso(anchor: Anchor, lines: list) -> str:
    """Ref (`PublishTestResults@2`) o verbo (`script`, `checkout`) de un item de steps."""
    try:
        doc = yaml.safe_load("\n".join(
            l[anchor.key_col:] if len(l) > anchor.key_col else ""
            for l in lines[anchor.start_line:anchor.end_line + 1]))
    except yaml.YAMLError:
        return ""
    if not isinstance(doc, dict):
        return ""
    if isinstance(doc.get("task"), str):
        return doc["task"]
    for clave in ("script", "checkout", "powershell", "bash", "pwsh", "publish", "download"):
        if clave in doc:
            return clave
    return ""


def _refs_de(indice: dict, target_path: str, lines: list) -> list:
    anchor = indice.get(target_path)
    if anchor is None:
        return []
    return [(p, _ref_de_paso(indice[p], lines)) for p in anchor.item_paths]


def _inputs_actuales(indice: dict, intent: EditIntent, lines: list) -> dict:
    """`inputs` que HOY tiene el paso apuntado por (target_path, anchor_ref). {} si no."""
    anchor = indice.get(intent.target_path)
    if anchor is None or anchor.kind != "seq":
        return {}
    for path, ref in _refs_de(indice, intent.target_path, lines):
        if ref != intent.anchor_ref:
            continue
        a_in = indice.get("%s.inputs" % path)
        if a_in is None:
            return {}
        crudo = "\n".join(
            l[a_in.key_col:] if len(l) > a_in.key_col else ""
            for l in lines[a_in.start_line:a_in.end_line + 1])
        try:
            doc = yaml.safe_load(crudo)
        except yaml.YAMLError:
            return {}
        return doc if isinstance(doc, dict) else {}
    return {}


def _step_doc(intent: EditIntent) -> dict:
    """Mismo orden de claves que pipeline_renderers._task_step_doc: task -> displayName
    -> condition -> inputs."""
    doc: dict = {"task": intent.task_ref}
    if intent.display_name:
        doc["displayName"] = intent.display_name
    if intent.inputs:
        doc["inputs"] = dict(intent.inputs)
    return doc


def plan_edit(yaml_text: str, intent: EditIntent, *, profile: str) -> tuple:
    """(ops, errores). DETERMINISTA: mismo (yaml_text, intent, profile) => mismas ops,
    byte por byte, siempre. NO aplica nada: solo planifica."""
    errores: list = []
    if not isinstance(intent, EditIntent) or intent.verb not in EDIT_VERBS:
        return (), ("verbo no soportado: %r (los soportados son %s)"
                    % (getattr(intent, "verb", None), ", ".join(EDIT_VERBS)),)
    if intent.position not in _POSITIONS:
        return (), ("posicion no soportada: %r (before | after | end)" % intent.position,)

    indice, errs = build_anchor_index(yaml_text)
    if errs:
        return (), tuple(errs)
    lines = yaml_text.splitlines()

    if intent.display_name:
        _texto_de_una_linea(intent.display_name, "el nombre visible", errores)
    for k, v in (intent.inputs or {}).items():
        _texto_de_una_linea(k, "la clave de input %r" % k, errores)
        _texto_de_una_linea(v, "el valor del input %r" % k, errores)
    for v in intent.values or ():
        _texto_de_una_linea(v, "el valor %r" % v, errores)

    if intent.verb in ("add_step", "set_task_input"):
        if not intent.task_ref:
            errores.append("%s necesita una tarea del catalogo (task_ref)" % intent.verb)
        elif not is_allowed(profile, intent.task_ref):
            errores.append(
                "la tarea '%s' no esta en el catalogo del perfil '%s': el editor no "
                "puede introducir una tarea fuera del catalogo."
                % (intent.task_ref, profile))
        elif intent.verb == "add_step":
            errores.extend(validate_inputs(profile, intent.task_ref, intent.inputs or {}))
        else:
            # `set_task_input` cambia UNA clave de un paso que ya existe: validar solo
            # el dict recibido dispararia "falta el input requerido X" para todos los que
            # el paso YA tiene. Se valida el resultado EFECTIVO (los actuales + el nuevo),
            # que ademas es mas estricto: el paso tiene que quedar valido despues.
            efectivos = dict(_inputs_actuales(indice, intent, lines))
            efectivos.update(intent.inputs or {})
            errores.extend(validate_inputs(profile, intent.task_ref, efectivos))

    if errores:
        return (), tuple(errores)

    fn = {
        "add_step": _plan_add_step,
        "remove_step": _plan_remove_step,
        "move_step": _plan_move_step,
        "set_task_input": _plan_set_task_input,
        "add_stage": _plan_add_stage,
        "set_trigger_paths": _plan_set_trigger_paths,
        "set_schedule": _plan_set_schedule,
    }[intent.verb]
    return fn(intent, indice, lines)


def _seq_objetivo(intent: EditIntent, indice: dict, esperado_kind: str = "seq"):
    anchor = indice.get(intent.target_path)
    if anchor is None:
        return None, ("no existe el punto '%s' en este pipeline. Puntos disponibles: %s"
                      % (intent.target_path, ", ".join(sorted(indice))),)
    if anchor.kind != esperado_kind:
        return None, ("el punto '%s' no es una lista editable" % intent.target_path,)
    return anchor, ()


def _resolver_ancla(intent: EditIntent, indice: dict, anchor: Anchor, lines: list):
    """Path del item de referencia dentro de `anchor`, segun anchor_ref/position."""
    refs = _refs_de(indice, anchor.path, lines)
    if intent.position == "end" or not intent.anchor_ref:
        if not anchor.item_paths:
            return None, ("el bloque '%s' esta vacio" % anchor.path,)
        return anchor.item_paths[-1], ()
    for path, ref in refs:
        if ref == intent.anchor_ref:
            return path, ()
    return None, ("no encontre '%s' dentro de '%s'. Los pasos que si estan: %s"
                  % (intent.anchor_ref, anchor.path,
                     ", ".join(r for _p, r in refs if r) or "(ninguno reconocible)"),)


def _plan_add_step(intent, indice, lines):
    anchor, err = _seq_objetivo(intent, indice)
    if err:
        return (), err
    destino, err = _resolver_ancla(intent, indice, anchor, lines)
    if err:
        return (), err
    bloque = render_block(_step_doc(intent), key_col=anchor.key_col, dash_col=anchor.dash_col)
    kind = "insert_before" if intent.position == "before" else "insert_after"
    return (EditOp(kind=kind, anchor_path=destino, lines=bloque,
                   reason="agregar el paso %s" % intent.task_ref),), ()


def _plan_remove_step(intent, indice, lines):
    anchor, err = _seq_objetivo(intent, indice)
    if err:
        return (), err
    destino, err = _resolver_ancla(
        EditIntent(verb="remove_step", target_path=intent.target_path,
                   anchor_ref=intent.anchor_ref, position="before"),
        indice, anchor, lines)
    if err:
        return (), err
    return (EditOp(kind="delete", anchor_path=destino, lines=(),
                   reason="quitar el paso %s" % (intent.anchor_ref or destino)),), ()


def _plan_move_step(intent, indice, lines):
    anchor, err = _seq_objetivo(intent, indice)
    if err:
        return (), err
    origen, err = _resolver_ancla(
        EditIntent(verb="move_step", target_path=intent.target_path,
                   anchor_ref=intent.anchor_ref, position="before"),
        indice, anchor, lines)
    if err:
        return (), err
    refs = dict(_refs_de(indice, anchor.path, lines))
    destino = None
    for path, ref in refs.items():
        if ref == (intent.values[0] if intent.values else None) and path != origen:
            destino = path
            break
    if destino is None:
        return (), ("move_step necesita, en `values`, la ref del paso junto al cual "
                    "moverlo. Pasos disponibles: %s"
                    % ", ".join(r for r in refs.values() if r),)
    a_origen = indice[origen]
    # el paso viaja CON el comentario que lo presenta (mismo criterio que `delete`)
    bloque = tuple(lines[a_origen.lead_line:a_origen.end_line + 1])
    kind = "insert_before" if intent.position == "before" else "insert_after"
    return (
        EditOp(kind="delete", anchor_path=origen, lines=(),
               reason="sacar el paso de su lugar actual"),
        EditOp(kind=kind, anchor_path=destino, lines=bloque,
               reason="reubicarlo junto a %s" % refs[destino]),
    ), ()


def _plan_set_task_input(intent, indice, lines):
    anchor, err = _seq_objetivo(intent, indice)
    if err:
        return (), err
    destino, err = _resolver_ancla(
        EditIntent(verb="set_task_input", target_path=intent.target_path,
                   anchor_ref=intent.anchor_ref, position="before"),
        indice, anchor, lines)
    if err:
        return (), err
    if len(intent.inputs or {}) != 1:
        return (), ("set_task_input cambia exactamente un input por vez",)
    clave, valor = next(iter(intent.inputs.items()))
    a_inputs = indice.get("%s.inputs" % destino)
    a_clave = indice.get("%s.inputs.%s" % (destino, clave))
    if a_clave is not None:
        nueva = render_block({clave: valor}, key_col=a_clave.key_col, dash_col=None)
        return (EditOp(kind="replace", anchor_path=a_clave.path, lines=nueva,
                       reason="cambiar %s a %r" % (clave, valor)),), ()
    if a_inputs is None:
        return (), ("el paso '%s' no tiene bloque `inputs`: agregarlo desde cero no "
                    "esta soportado por set_task_input" % destino,)
    nueva = render_block({clave: valor}, key_col=a_inputs.key_col, dash_col=None)
    ultimo = a_inputs
    return (EditOp(kind="insert_after", anchor_path=ultimo.path, lines=nueva,
                   reason="agregar el input %s" % clave),), ()


def _plan_add_stage(intent, indice, lines):
    anchor = indice.get("stages")
    if anchor is None or anchor.kind != "seq":
        return (), ("este pipeline no tiene un bloque `stages` editable",)
    destino = None
    if intent.anchor_ref:
        for path in anchor.item_paths:
            a = indice[path]
            crudo = "\n".join(l[a.key_col:] if len(l) > a.key_col else ""
                              for l in lines[a.start_line:a.end_line + 1])
            try:
                doc = yaml.safe_load(crudo)
            except yaml.YAMLError:
                doc = None
            if isinstance(doc, dict) and doc.get("stage") == intent.anchor_ref:
                destino = path
                break
        if destino is None:
            return (), ("no encontre el stage '%s'" % intent.anchor_ref,)
    else:
        if not anchor.item_paths:
            return (), ("el bloque `stages` esta vacio",)
        destino = anchor.item_paths[-1]
    nombre = intent.display_name or "NuevoStage"
    doc = {"stage": nombre, "jobs": []}
    if intent.values:
        doc["displayName"] = intent.values[0]
    bloque = render_block(doc, key_col=anchor.key_col, dash_col=anchor.dash_col)
    kind = "insert_before" if intent.position == "before" else "insert_after"
    return (EditOp(kind=kind, anchor_path=destino, lines=bloque,
                   reason="agregar el stage %s" % nombre),), ()


def _plan_set_trigger_paths(intent, indice, lines):
    anchor = indice.get("trigger.paths.include")
    if anchor is None:
        return (), ("este pipeline no tiene `trigger.paths.include`: no se puede "
                    "reemplazar lo que no existe",)
    if not intent.values:
        return (), ("set_trigger_paths necesita al menos una ruta en `values`",)
    nueva = render_block({"include": list(intent.values)},
                         key_col=(anchor.key_line is not None
                                  and lines[anchor.key_line].index("include") or 0),
                         dash_col=None)
    return (EditOp(kind="replace", anchor_path=anchor.path, lines=nueva,
                   reason="reemplazar las rutas del trigger"),), ()


def _plan_set_schedule(intent, indice, lines):
    if not intent.values:
        return (), ("set_schedule necesita el cron en `values`",)
    doc = {"schedules": [{"cron": intent.values[0],
                          "displayName": intent.display_name or "Programado",
                          "branches": {"include": list(intent.values[1:]) or ["main"]},
                          "always": True}]}
    bloque = render_block(doc, key_col=0, dash_col=None)
    existente = indice.get("schedules")
    if existente is not None:
        return (EditOp(kind="replace", anchor_path="schedules", lines=bloque,
                       reason="reemplazar la programacion"),), ()
    ancla = indice.get("trigger") or indice.get("pr") or indice.get("variables")
    if ancla is None:
        return (), ("no encontre donde insertar `schedules` en este pipeline",)
    return (EditOp(kind="insert_after", anchor_path=ancla.path, lines=bloque,
                   reason="agregar la programacion"),), ()


# ── F5 (parte pura) — esquema cerrado del intent ─────────────────────────────

def _validate_inputs_parcial(profile: str, ref: str, inputs: dict) -> list:
    """Valida SOLO las claves recibidas (nombre valido + valor dentro del enum), sin
    exigir los inputs requeridos que el paso ya tiene. Reusa el validador real: rellena
    los requeridos con un placeholder en vez de recortar mensajes por texto."""
    from services.cicd_task_catalog import get_task  # noqa: PLC0415

    spec = get_task(profile, ref)
    if spec is None:
        return validate_inputs(profile, ref, inputs)
    completo = {i.name: (i.allowed_values[0] if i.allowed_values else "_")
                for i in spec.inputs if i.required}
    completo.update(inputs or {})
    return validate_inputs(profile, ref, completo)


INTENT_SCHEMA: dict = {
    "verb": {"type": "str", "required": True, "enum": EDIT_VERBS},
    "target_path": {"type": "str", "required": False},
    "anchor_ref": {"type": "str", "required": False, "nullable": True},
    "position": {"type": "str", "required": False, "enum": _POSITIONS},
    "task_ref": {"type": "str", "required": False, "nullable": True},
    "inputs": {"type": "dict", "required": False},
    "display_name": {"type": "str", "required": False},
    "values": {"type": "list", "required": False},
    "notes": {"type": "list", "required": False},
}


def validate_intent_dict(d: dict, *, profile: str) -> tuple:
    """(EditIntent|None, errores). Sin red, sin LLM, sin I/O. Nunca lanza.

    Es la contracara de EDIT_VERBS: valida el JSON que produce el modelo contra el
    esquema cerrado Y contra el catalogo del perfil, antes de que llegue al motor.
    """
    errores: list = []
    if not isinstance(d, dict):
        return None, ("la respuesta del modelo no es un objeto JSON",)

    desconocidas = sorted(set(d) - set(INTENT_SCHEMA))
    if desconocidas:
        errores.append("campos no reconocidos: %s" % ", ".join(desconocidas))

    verb = d.get("verb")
    if not isinstance(verb, str) or verb not in EDIT_VERBS:
        return None, tuple(errores + [
            "verbo no soportado: %r (los soportados son %s)" % (verb, ", ".join(EDIT_VERBS))])

    position = d.get("position") or "end"
    if position not in _POSITIONS:
        errores.append("posicion no soportada: %r (before | after | end)" % position)

    inputs = d.get("inputs") or {}
    if not isinstance(inputs, dict):
        errores.append("`inputs` debe ser un objeto")
        inputs = {}

    values = d.get("values") or ()
    if not isinstance(values, (list, tuple)):
        errores.append("`values` debe ser una lista")
        values = ()

    notes = d.get("notes") or ()
    if not isinstance(notes, (list, tuple)):
        errores.append("`notes` debe ser una lista")
        notes = ()

    display_name = d.get("display_name") or ""
    if not isinstance(display_name, str):
        errores.append("`display_name` debe ser texto")
        display_name = ""
    else:
        _texto_de_una_linea(display_name, "el nombre visible", errores)

    task_ref = d.get("task_ref")
    if task_ref is not None and not isinstance(task_ref, str):
        errores.append("`task_ref` debe ser texto")
        task_ref = None
    if task_ref and not is_allowed(profile, task_ref):
        errores.append(
            "la tarea '%s' no esta en el catalogo del perfil '%s': el modelo no puede "
            "inventar tareas." % (task_ref, profile))
    elif task_ref and verb == "set_task_input":
        # cambia UNA clave de un paso que YA existe: exigirle aca los inputs requeridos
        # del paso completo daria "falta el input requerido X" siempre. La validacion
        # COMPLETA (con los inputs reales del paso) la hace plan_edit, que si tiene el YAML.
        errores.extend(_validate_inputs_parcial(profile, task_ref, inputs))
    elif task_ref:
        errores.extend(validate_inputs(profile, task_ref, inputs))

    for k, v in inputs.items():
        _texto_de_una_linea(k, "la clave de input %r" % k, errores)
        _texto_de_una_linea(v, "el valor del input %r" % k, errores)

    if errores:
        return None, tuple(errores)

    return EditIntent(
        verb=verb,
        target_path=str(d.get("target_path") or ""),
        anchor_ref=(str(d["anchor_ref"]) if d.get("anchor_ref") else None),
        position=position,
        task_ref=task_ref,
        inputs=dict(inputs),
        display_name=display_name,
        values=tuple(str(v) for v in values),
        notes=tuple(str(n) for n in notes),
    ), ()
