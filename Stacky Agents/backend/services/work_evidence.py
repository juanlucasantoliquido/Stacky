"""Plan 293 F11b — Evidencias de prueba: guardar, previsualizar y adjuntar.

El pliego lo pide TRES veces, y una es su criterio de exito:
  - "Adjuntar imagenes, capturas de pantalla o archivos como evidencia del testing."
  - "Previsualizar las evidencias antes de crear la Pull Request."
  - "Estrategia para subir, almacenar y asociar imagenes a una Pull Request."

POR QUE SE VALIDA POR BYTES Y NO POR EXTENSION
----------------------------------------------
Un adjunto es una VIA DE ENTRADA. La extension del nombre la elige quien sube el
archivo, asi que `captura.png` puede ser cualquier cosa. Se mira la FIRMA REAL
del contenido (magic bytes) y, si no coincide con un tipo permitido, se rechaza
aunque el nombre diga lo contrario.

PROHIBIDO `link_attachment` DE GITLAB (services/gitlab_provider.py:521-537)
--------------------------------------------------------------------------
Lee la descripcion actual del issue y, si el GET previo falla, asume "" y la
PISA ENTERA con solo el markdown del adjunto. Es perdida de datos silenciosa.
Este modulo NUNCA lo llama: sube con `upload_attachment` y devuelve el markdown
para que `change_proposal.build_description` lo embeba en la descripcion que se
manda AL CREAR la propuesta, en un unico llamado. Hay un caso negativo que lo
vigila.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import runtime_paths
from services.incident_store import sanitize_filename

# Topes: los mismos valores ya probados del intake de incidencias
# (services/incident_store.py:23-25). Decision pendiente del operador: ver §D9.
MAX_ARCHIVOS = 10
MAX_BYTES_POR_ARCHIVO = 10 * 1024 * 1024   # 10 MB
MAX_BYTES_TOTAL = 25 * 1024 * 1024         # 25 MB

# Firmas REALES aceptadas. (prefijo, desplazamiento, tipo, extension canonica)
_FIRMAS: tuple[tuple[bytes, int, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", ".png"),
    (b"\xff\xd8\xff", 0, "image/jpeg", ".jpg"),
    (b"GIF87a", 0, "image/gif", ".gif"),
    (b"GIF89a", 0, "image/gif", ".gif"),
    (b"BM", 0, "image/bmp", ".bmp"),
    (b"WEBP", 8, "image/webp", ".webp"),   # RIFF....WEBP
    (b"%PDF-", 0, "application/pdf", ".pdf"),
)

_ID_VALIDO = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def raiz() -> Path:
    """Carpeta de las evidencias. Vive en el area de datos de Stacky, NUNCA en
    el repositorio del operador: un archivo dentro del repo apareceria como
    cambio sin confirmar y ensuciaria su tablero."""
    return runtime_paths.data_dir() / "work_evidence"


def _carpeta(sesion: str) -> Path:
    return raiz() / sesion


def nueva_sesion() -> str:
    """Identificador opaco de una tanda de evidencias. No lleva datos del
    operador ni rutas de su disco."""
    return uuid.uuid4().hex[:16]


def detectar_tipo(contenido: bytes) -> tuple[str, str] | None:
    """(tipo, extension) si el CONTENIDO coincide con un formato permitido.

    None significa "no es un formato que aceptemos", sin importar como se llame
    el archivo.
    """
    for prefijo, desplazamiento, tipo, ext in _FIRMAS:
        if contenido[desplazamiento:desplazamiento + len(prefijo)] == prefijo:
            return tipo, ext
    return None


def _leer_meta(sesion: str) -> list[dict]:
    ruta = _carpeta(sesion) / "meta.json"
    if not ruta.exists():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return datos if isinstance(datos, list) else []
    except (OSError, ValueError):
        return []


def _escribir_meta(sesion: str, entradas: list[dict]) -> None:
    carpeta = _carpeta(sesion)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "meta.json").write_text(
        json.dumps(entradas, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def guardar(sesion: str, archivos: list[tuple[str, bytes]]) -> dict:
    """Guarda las evidencias de una tanda. Devuelve
    {'ok', 'archivos': [...], 'rechazados': [{'nombre','motivo'}]}.

    Nunca lanza por culpa de un archivo malo: lo rechaza con motivo y sigue con
    los demas, para que una captura corrupta no tire abajo toda la carga.
    """
    if not _ID_VALIDO.match(sesion or ""):
        return {"ok": False, "codigo": "sesion_invalida", "archivos": [], "rechazados": []}

    existentes = _leer_meta(sesion)
    total_actual = sum(int(e.get("bytes") or 0) for e in existentes)

    aceptados: list[dict] = []
    rechazados: list[dict] = []

    for nombre_crudo, contenido in archivos or []:
        nombre = sanitize_filename(nombre_crudo)

        if len(existentes) + len(aceptados) >= MAX_ARCHIVOS:
            rechazados.append({"nombre": nombre, "motivo": "demasiados_archivos"})
            continue
        if len(contenido) > MAX_BYTES_POR_ARCHIVO:
            rechazados.append({"nombre": nombre, "motivo": "archivo_muy_grande"})
            continue
        if total_actual + len(contenido) > MAX_BYTES_TOTAL:
            rechazados.append({"nombre": nombre, "motivo": "total_muy_grande"})
            continue

        detectado = detectar_tipo(contenido)
        if detectado is None:
            # El nombre puede decir ".png" y el contenido ser otra cosa. Manda
            # el contenido.
            rechazados.append({"nombre": nombre, "motivo": "formato_no_permitido"})
            continue

        tipo, ext = detectado
        guardado = f"{len(existentes) + len(aceptados):02d}{ext}"
        carpeta = _carpeta(sesion)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / guardado).write_bytes(contenido)

        total_actual += len(contenido)
        aceptados.append({
            "nombre": nombre,          # el que ve el operador, ya saneado
            "guardado": guardado,      # el del disco: SIEMPRE derivado, nunca el de entrada
            "tipo": tipo,
            "bytes": len(contenido),
        })

    if aceptados:
        _escribir_meta(sesion, existentes + aceptados)

    return {"ok": True, "codigo": None, "archivos": aceptados, "rechazados": rechazados}


def listar(sesion: str) -> list[dict]:
    """Las evidencias de la tanda, para la PREVISUALIZACION previa a proponer.

    NUNCA devuelve rutas absolutas del disco del operador: solo el nombre que el
    mismo puso y el nombre interno con el que se sirve la vista previa.
    """
    if not _ID_VALIDO.match(sesion or ""):
        return []
    return [
        {"nombre": e.get("nombre"), "guardado": e.get("guardado"),
         "tipo": e.get("tipo"), "bytes": e.get("bytes")}
        for e in _leer_meta(sesion)
    ]


def ruta_de(sesion: str, guardado: str) -> Path | None:
    """Ruta en disco de una evidencia, para servir la vista previa.

    Anti path-traversal: el nombre interno tiene que ser EXACTAMENTE uno de los
    que figuran en el meta; nunca se arma la ruta con lo que llega de afuera.
    """
    if not _ID_VALIDO.match(sesion or ""):
        return None
    for e in _leer_meta(sesion):
        if e.get("guardado") == guardado:
            candidata = _carpeta(sesion) / str(guardado)
            if candidata.exists():
                return candidata
    return None


def subir_al_proveedor(sesion: str, project: str | None = None) -> dict:
    """Sube las evidencias al servidor y devuelve el markdown para EMBEBER.

    Devuelve {'ok', 'markdown': [str], 'degradado': dict|None, 'fallidos': [...]}.

    NO llama a `link_attachment`: ese pisa la descripcion del issue. El markdown
    que sale de aca lo embebe `change_proposal.build_description` en la
    descripcion que se manda AL CREAR la propuesta, en un unico llamado.

    Si el proveedor no sabe subir (Azure DevOps devuelve un adjunto de work item,
    que NO se puede embeber en una propuesta), se DECLARA la degradacion en vez
    de fallar: las evidencias quedan guardadas en Stacky y se listan por nombre.
    """
    evidencias = listar(sesion)
    if not evidencias:
        return {"ok": True, "markdown": [], "degradado": None, "fallidos": []}

    try:
        from services.tracker_provider import get_tracker_provider

        proveedor = get_tracker_provider(project=project)
    except Exception:  # noqa: BLE001
        return {
            "ok": True, "markdown": [], "fallidos": [],
            "degradado": _degradacion("no hay un servidor donde subir las evidencias", "desconocido"),
        }

    nombre_proveedor = getattr(proveedor, "name", type(proveedor).__name__)
    subir = getattr(proveedor, "upload_attachment", None)
    if subir is None or "gitlab" not in str(nombre_proveedor).lower():
        # Azure DevOps SI tiene upload_attachment, pero devuelve el adjunto de un
        # WORK ITEM: esa URL no se muestra embebida dentro de una propuesta de
        # cambio. Se declara y se sigue.
        return {
            "ok": True, "markdown": [], "fallidos": [],
            "degradado": _degradacion(
                "este servidor no permite mostrar las capturas dentro de la propuesta",
                str(nombre_proveedor),
            ),
        }

    markdown: list[str] = []
    fallidos: list[dict] = []
    for e in evidencias:
        ruta = ruta_de(sesion, e["guardado"])
        if ruta is None:
            fallidos.append({"nombre": e["nombre"], "motivo": "no_encontrada"})
            continue
        try:
            resultado = subir(str(ruta), e["nombre"]) or {}
        except Exception:  # noqa: BLE001
            # Una captura que no sube NO puede voltear la propuesta entera.
            fallidos.append({"nombre": e["nombre"], "motivo": "no_se_pudo_subir"})
            continue
        md = resultado.get("markdown") or resultado.get("url") or ""
        if md:
            markdown.append(md)
        else:
            fallidos.append({"nombre": e["nombre"], "motivo": "sin_enlace"})

    return {"ok": True, "markdown": markdown, "degradado": None, "fallidos": fallidos}


def _degradacion(motivo: str, proveedor: str) -> dict:
    """Forma canonica de una degradacion declarada. Se reusa `construir_entrada`
    (que es PURA); `declarar` NO sirve aca porque exige un execution_id y el
    tablero no tiene ejecucion (services/capability_degradation.py:123-124)."""
    from services.capability_degradation import construir_entrada

    return construir_entrada(
        capability="git.evidence.embed",
        reason=motivo,
        provider=proveedor,
        site="work_evidence.subir_al_proveedor",
    )
