"""Plan 259 — Guias de configuracion exactas por proveedor de tickets.

PURO: sin flask, sin IO, sin red. Datos + 3 funciones de lookup.
El contenido es el MISMO en Codex CLI, Claude Code CLI y GitHub Copilot Pro
porque no interviene ningun LLM: es una tabla.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideStep:
    id: str          # kebab-case estable; los checks lo referencian
    title: str       # <= 90 chars
    detail: str      # texto llano, puede tener varias frases
    where: str       # "gitlab" | "stacky" | "windows"
    trap: str = ""   # "" o la trampa concreta a evitar


@dataclass(frozen=True)
class GuideCheck:
    id: str          # "chk-*"
    title: str
    fixes_step: str  # DEBE ser el .id de un GuideStep de la misma guia


@dataclass(frozen=True)
class SetupGuide:
    provider: str          # "gitlab"
    display_name: str      # "GitLab"
    summary: str           # 1 parrafo
    required_fields: tuple[str, ...]
    steps: tuple[GuideStep, ...]
    checks: tuple[GuideCheck, ...]


GITLAB_GUIDE = SetupGuide(
    provider="gitlab",
    display_name="GitLab",
    summary=(
        "Stacky se conecta a GitLab por su API v4 con un token personal. Necesitás tres "
        "datos: la URL base de tu GitLab, el path del proyecto y un token con permiso de "
        "API. El token se guarda cifrado en tu equipo y nunca sale de acá salvo hacia tu "
        "propia instancia de GitLab."
    ),
    required_fields=("gitlab_url", "gitlab_project", "gitlab_token"),
    steps=(
        GuideStep(
            id="gl-01-instancia",
            title="1. Identificá la URL base de tu GitLab",
            detail=(
                "Si usás GitLab en la nube es https://gitlab.com . Si tu empresa tiene el "
                "suyo, es la raíz del sitio, por ejemplo https://gitlab.miempresa.com . "
                "Va SIN barra al final y SIN /api/v4 : eso lo agrega Stacky. "
                "Para confirmar, abrí <URL>/api/v4/version en el navegador: si te devuelve "
                "un JSON o un 401, la URL está bien; si te devuelve 404, está mal."
            ),
            where="gitlab",
            trap="Pegar la URL del proyecto en vez de la del sitio. La URL base NO incluye el nombre del grupo ni del proyecto.",
        ),
        GuideStep(
            id="gl-02-token",
            title="2. Creá un Personal Access Token con permiso 'api'",
            detail=(
                "En GitLab (versiones 16.x y 17.x): hacé clic en tu foto arriba a la derecha "
                "→ 'Edit profile' → en el menú de la izquierda 'Access tokens' → 'Add new token'. "
                "Ponele de nombre 'stacky-agents'. Elegí una fecha de vencimiento (GitLab obliga "
                "a poner una). En la lista de permisos ('scopes') marcá 'api'. "
                "Con 'read_api' Stacky solo puede LEER: no podría comentar el ticket, cambiar la "
                "etiqueta ni cerrarlo. Apretá 'Create' y COPIÁ el token en ese momento: GitLab no "
                "te lo vuelve a mostrar nunca más."
            ),
            where="gitlab",
            trap="Cerrar la pantalla sin copiar el token. Si pasa, no se puede recuperar: hay que crear otro.",
        ),
        GuideStep(
            id="gl-03-rol",
            title="3. Verificá que tu usuario tenga rol suficiente en el proyecto",
            detail=(
                "En el proyecto de GitLab: menú 'Manage' → 'Members'. Buscá tu usuario. "
                "Con rol 'Reporter' Stacky puede leer los tickets. Para comentar, cambiar "
                "etiquetas y cerrar, necesitás 'Developer' o superior. "
                "El token nunca te da más permisos de los que ya tenés vos."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-04-project-path",
            title="4. Anotá el path del proyecto",
            detail=(
                "Es lo que viene después del dominio en la URL del proyecto, sin https:// y "
                "sin la parte /-/algo. Ejemplo: si la URL es "
                "https://gitlab.com/acme/backend/api entonces el path es acme/backend/api . "
                "También se acepta el número de ID del proyecto, que figura en "
                "'Settings' → 'General', arriba de todo, como 'Project ID'. "
                "Las barras las codifica Stacky solo."
            ),
            where="gitlab",
            trap="Escribir solo el último tramo ('api'). Hay que poner el path completo con los grupos y subgrupos.",
        ),
        GuideStep(
            id="gl-05-issues",
            title="5. Confirmá que el proyecto tenga los Issues habilitados",
            detail=(
                "En el proyecto: 'Settings' → 'General' → 'Visibility, project features, "
                "permissions' → la perilla 'Issues' tiene que estar encendida. "
                "Si está apagada, GitLab responde 404 cuando Stacky pide la lista de tickets, "
                "aunque la URL y el token estén perfectos."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-06-grupo",
            title="6. (Opcional) Grupo, solo si vas a usar épicas nativas",
            detail=(
                "El campo 'Grupo' es únicamente para las épicas nativas de GitLab, que son una "
                "función de los planes Premium y Ultimate. Es el path del grupo raíz, por "
                "ejemplo 'acme'. Si lo dejás vacío, Stacky trabaja con issues comunes, que "
                "funcionan en todos los planes incluido el gratuito."
            ),
            where="gitlab",
        ),
        GuideStep(
            id="gl-07-stacky-alta",
            title="7. Cargá los datos en Stacky",
            detail=(
                "En Stacky: 'Nuevo Proyecto' → elegí el botón '🦊 GitLab' → completá "
                "Nombre interno, Workspace root, URL base (paso 1), Path del proyecto (paso 4) "
                "y pegá el Token (paso 2). El Grupo (paso 6) es opcional."
            ),
            where="stacky",
        ),
        GuideStep(
            id="gl-08-motor",
            title="8. Dejá tildada la casilla 'Activar el motor GitLab'",
            detail=(
                "Viene tildada. Enciende la perilla STACKY_GITLAB_ENABLED, que es el interruptor "
                "general del soporte GitLab y de fábrica viene apagada. Se enciende recién cuando "
                "apretás 'Crear e inicializar': hasta ese momento el control 'El motor GitLab está "
                "encendido' de 'Verificar ahora' te va a decir que está apagado y que se va a "
                "activar al crear. Si la destildás, el proyecto se crea igual pero cada "
                "sincronización va a fallar con el mensaje "
                "'issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false'. "
                "Si más adelante querés apagarla o volver a prenderla: esta perilla se guarda "
                "en el archivo .env del servidor de Stacky, en la línea "
                "STACKY_GITLAB_ENABLED, y hoy no hay ninguna pantalla que la muestre. "
                "No la confundas con las perillas de 'Paridad de proveedores' del panel de "
                "Configuración, que son otras."
            ),
            where="stacky",
        ),
        GuideStep(
            id="gl-09-donde-queda",
            title="9. Dónde queda guardado el token",
            detail=(
                "En backend/projects/<NOMBRE>/auth/gitlab_auth.json , cifrado con DPAPI de "
                "Windows y atado a tu usuario de Windows. Ni Stacky ni nadie puede leerlo desde "
                "otro usuario o desde otra máquina. Si copiás la carpeta a otra PC, hay que "
                "volver a pegar el token. "
                "Si ya tenías un gitlab_auth.json viejo con el token sin cifrar, la primera vez "
                "que Stacky lo lea lo va a cifrar y a reescribir en ese mismo lugar: desde ahí "
                "queda atado a tu usuario de Windows igual que los demás."
            ),
            where="windows",
        ),
        GuideStep(
            id="gl-10-env-precedencia",
            title="10. Cuidado con la variable de entorno GITLAB_TOKEN",
            detail=(
                "Si en tu equipo existe la variable de entorno GITLAB_TOKEN, esa GANA sobre el "
                "token guardado por proyecto. Con dos proyectos GitLab distintos, los dos "
                "terminarían usando el mismo token y uno de los dos va a fallar. "
                "Recomendación: no definas GITLAB_TOKEN en el entorno y dejá que cada proyecto "
                "use el suyo."
            ),
            where="windows",
            trap="Un token viejo en el entorno hace fallar un token nuevo y correcto cargado por pantalla.",
        ),
        GuideStep(
            id="gl-11-ssl",
            title="11. Redes de empresa con certificado propio",
            detail=(
                "Si tu GitLab usa un certificado emitido por la autoridad certificante de la "
                "empresa, importá esa autoridad al almacén de certificados de Windows "
                "('Entidades de certificación raíz de confianza'). "
                "Stacky no ofrece 'desactivar la verificación SSL' para GitLab a propósito: "
                "sería mandar tu token por un canal que no se puede verificar."
            ),
            where="windows",
        ),
        GuideStep(
            id="gl-12-verificar",
            title="12. Verificá antes de crear",
            detail=(
                "Apretá 'Verificar ahora' en este mismo panel. Corre 5 controles de solo lectura "
                "contra tu GitLab y te dice exactamente cuál falla y qué paso de esta guía lo "
                "arregla. No crea ni modifica nada en GitLab."
            ),
            where="stacky",
        ),
    ),
    checks=(
        GuideCheck(id="chk-flag",      title="El motor GitLab está encendido",              fixes_step="gl-08-motor"),
        GuideCheck(id="chk-instancia", title="La URL responde y es un GitLab",              fixes_step="gl-01-instancia"),
        GuideCheck(id="chk-token",     title="El token es válido",                          fixes_step="gl-02-token"),
        GuideCheck(id="chk-scope",     title="El token tiene el permiso 'api'",              fixes_step="gl-02-token"),
        GuideCheck(id="chk-proyecto",  title="El proyecto existe y tiene Issues habilitado", fixes_step="gl-04-project-path"),
    ),
)


SETUP_GUIDES: dict[str, SetupGuide] = {"gitlab": GITLAB_GUIDE}


def guide_exists(provider: str) -> bool:
    return (provider or "").strip().lower() in SETUP_GUIDES


def guide_for(provider: str) -> SetupGuide | None:
    return SETUP_GUIDES.get((provider or "").strip().lower())


def guide_as_dict(provider: str) -> dict | None:
    """Serializa la guia para la API. None si el proveedor no tiene guia."""
    g = guide_for(provider)
    if g is None:
        return None
    return {
        "provider": g.provider,
        "display_name": g.display_name,
        "summary": g.summary,
        "required_fields": list(g.required_fields),
        "steps": [
            {"id": s.id, "title": s.title, "detail": s.detail, "where": s.where, "trap": s.trap}
            for s in g.steps
        ],
        "checks": [
            {"id": c.id, "title": c.title, "fixes_step": c.fixes_step} for c in g.checks
        ],
    }


__all__ = ["GuideStep", "GuideCheck", "SetupGuide", "SETUP_GUIDES",
           "GITLAB_GUIDE", "guide_exists", "guide_for", "guide_as_dict"]
