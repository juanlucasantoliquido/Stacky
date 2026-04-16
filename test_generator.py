"""
test_generator.py — X-04: Auto-Generacion de Tests Unitarios para el Fix.

Despues de que DEV completa la implementacion, antes de invocar QA,
genera tests unitarios para el codigo nuevo usando Claude API.

Los tests cubren:
  - El caso feliz del fix
  - El caso que generaba el bug original
  - Al menos un edge case identificado en el analisis PM

QA recibe los tests generados como parte de su prompt.
Los tests aprobados se agregan al proyecto de tests automaticamente.

Uso:
    from test_generator import TestGenerator
    gen = TestGenerator(project_name)
    result = gen.generate_tests(ticket_folder, ticket_id)
    # result["test_file"]    → ruta del archivo de tests generado
    # result["test_content"] → contenido del archivo
    # result["qa_section"]   → bloque Markdown para inyectar en prompt QA
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mantis.test_generator")

BASE_DIR = Path(__file__).parent


class TestGenerator:
    """
    Genera tests unitarios para fixes de tickets usando VS Code Copilot Bridge (puerto 5051).
    Si el bridge no esta disponible, genera un template de tests con estructura correcta.
    """

    def __init__(self, project_name: str):
        self.project_name = project_name
        self._config      = self._load_config()
        self._tests_output_dir = (
            BASE_DIR / "projects" / project_name / "generated_tests"
        )
        self._tests_output_dir.mkdir(parents=True, exist_ok=True)

    # ── API publica ──────────────────────────────────────────────────────────

    def generate_tests(self, ticket_folder: str, ticket_id: str) -> dict:
        """
        Genera tests unitarios para el fix del ticket.
        Retorna dict con: test_file, test_content, qa_section, success.
        """
        folder = Path(ticket_folder)

        # Leer artefactos del ticket
        inc_content   = self._read_file(folder / self._find_inc_file(folder))
        analisis      = self._read_file(folder / "ANALISIS_TECNICO.md")
        arquitectura  = self._read_file(folder / "ARQUITECTURA_SOLUCION.md")
        tareas        = self._read_file(folder / "TAREAS_DESARROLLO.md")
        dev_completado = self._read_file(folder / "DEV_COMPLETADO.md")
        svn_changes   = self._read_file(folder / "SVN_CHANGES.md")

        # Detectar framework de tests del proyecto
        framework = self._detect_test_framework()

        # Extraer archivos modificados
        modified_files = self._extract_modified_files(dev_completado, svn_changes)

        logger.info("[X-04] Generando tests para ticket %s (framework: %s)", ticket_id, framework)

        # Generar tests via Claude API o template fallback
        test_content = self._generate_via_api(
            ticket_id=ticket_id,
            inc_content=inc_content,
            analisis=analisis,
            arquitectura=arquitectura,
            tareas=tareas,
            dev_completado=dev_completado,
            modified_files=modified_files,
            framework=framework,
        )

        # Guardar archivo de tests
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_filename = f"Tests_{ticket_id}_{timestamp}.cs"
        test_path = self._tests_output_dir / test_filename

        test_path.write_text(test_content, encoding="utf-8")

        # Tambien guardar en carpeta del ticket
        ticket_test_path = folder / "TESTS_GENERADOS.cs"
        ticket_test_path.write_text(test_content, encoding="utf-8")

        # Generar seccion para prompt QA
        qa_section = self._build_qa_section(
            test_content, ticket_id, modified_files, framework
        )

        # Guardar seccion QA en carpeta del ticket para que pipeline_watcher la use
        qa_section_path = folder / "TESTS_QA_SECTION.md"
        qa_section_path.write_text(qa_section, encoding="utf-8")

        logger.info("[X-04] Tests generados: %s", test_path)

        return {
            "success":      True,
            "ticket_id":    ticket_id,
            "test_file":    str(test_path),
            "test_content": test_content,
            "qa_section":   qa_section,
            "framework":    framework,
        }

    def get_qa_injection(self, ticket_folder: str) -> Optional[str]:
        """
        Retorna la seccion QA pre-generada si existe.
        Llamado por prompt_builder.py antes de generar el prompt de QA.
        """
        qa_section_path = Path(ticket_folder) / "TESTS_QA_SECTION.md"
        if qa_section_path.exists():
            return qa_section_path.read_text(encoding="utf-8", errors="ignore")
        return None

    # ── Privados ─────────────────────────────────────────────────────────────

    def _generate_via_api(
        self, ticket_id: str, inc_content: str, analisis: str,
        arquitectura: str, tareas: str, dev_completado: str,
        modified_files: list, framework: str,
    ) -> str:
        """Intenta generar tests via VS Code Copilot Bridge. Fallback a template si falla."""
        # Truncar inputs para no exceder contexto
        def trunc(s: str, n: int = 2000) -> str:
            return s[:n] + "..." if len(s) > n else s

        prompt = f"""Genera tests unitarios en C# ({framework}) para el siguiente fix de bug.

## Ticket {ticket_id} — Descripcion del problema
{trunc(inc_content, 1500)}

## Analisis Tecnico (causa raiz identificada)
{trunc(analisis, 2000)}

## Arquitectura de Solucion
{trunc(arquitectura, 1500)}

## Archivos modificados
{chr(10).join(f'- {f}' for f in modified_files[:8])}

## Completado por DEV
{trunc(dev_completado, 1000)}

---

Genera una clase de tests en C# que cubra EXACTAMENTE:
1. **TestCaseFeliz**: el escenario normal que ahora funciona correctamente
2. **TestCasoOriginalDelBug**: el caso exacto que generaba el bug (debe pasar con el fix)
3. **TestEdgeCase**: al menos un caso borde identificado en el analisis

Usa {framework}. El codigo debe compilar. Usa nombres descriptivos para los metodos.
Incluye comentarios indicando que bug cubre cada test.
Responde SOLO con el codigo C# sin explicaciones adicionales.
"""

        try:
            from copilot_bridge import _try_bridge
            config   = self._config
            ws_root  = config.get("workspace_root", "")
            agent    = config.get("agents", {}).get("dev", "")

            if _try_bridge(prompt, agent_name=agent or None,
                           workspace_root=ws_root or None):
                logger.info("[X-04] Prompt de tests enviado al bridge Copilot")
                # El bridge envia el prompt a Copilot; resultado generado en VS Code.
                # Guardamos el prompt para que el desarrollador vea que se solicito.
                return self._generate_template(ticket_id, modified_files, framework,
                                               bridge_sent=True)
        except Exception as exc:
            logger.warning("[X-04] Error en Copilot Bridge: %s — usando template", exc)

        return self._generate_template(ticket_id, modified_files, framework)

    def _generate_template(self, ticket_id: str, modified_files: list, framework: str,
                           bridge_sent: bool = False) -> str:
        """Genera un template de tests con estructura correcta para completar manualmente."""
        primary_file = modified_files[0] if modified_files else "ClaseAfectada"
        class_name   = Path(primary_file).stem if primary_file != "ClaseAfectada" else "ClaseAfectada"

        attr = "[TestMethod]" if framework == "MSTest" else "[Test]"
        base_class = ": TestBase" if framework == "NUnit" else ""
        using = "using Microsoft.VisualStudio.TestTools.UnitTesting;" if framework == "MSTest" else "using NUnit.Framework;"

        bridge_note = (
            "// NOTA: El prompt completo fue enviado a VS Code Copilot via bridge (puerto 5051).\n"
            "//       El agente DEV generara los tests completos en VS Code.\n"
            "//       Este template sirve como referencia de estructura.\n"
        ) if bridge_sent else "// COMPLETAR: reemplazar TODO con la logica de prueba correspondiente\n"

        return f"""// Auto-generado por Stacky X-04 para ticket {ticket_id}
// Framework: {framework}
{bridge_note}

{using}

namespace Tests.{self.project_name}
{{
    [{framework if framework == "MSTest" else "TestFixture"}]
    public class Tests_{ticket_id}_{class_name}{base_class}
    {{
        // TODO: Inicializar dependencias y mocks necesarios
        private {class_name} _sut; // System Under Test

        [{"TestInitialize" if framework == "MSTest" else "SetUp"}]
        public void Setup()
        {{
            // TODO: Inicializar _sut y sus dependencias
            // _sut = new {class_name}(...);
        }}

        /// <summary>
        /// Caso feliz: el flujo normal funciona correctamente post-fix
        /// Bug cubierto: {ticket_id}
        /// </summary>
        {attr}
        public void {class_name}_CasoNormal_DebeRetornarExitosamente()
        {{
            // Arrange
            // TODO: configurar datos de prueba validos

            // Act
            // var resultado = _sut.MetodoFijado(...);

            // Assert
            // Assert.IsNotNull(resultado);
        }}

        /// <summary>
        /// Reproduce el bug original: antes del fix este caso fallaba
        /// Bug cubierto: {ticket_id}
        /// </summary>
        {attr}
        public void {class_name}_CasoBugOriginal_NoDebeGenerarExcepcion()
        {{
            // Arrange
            // TODO: configurar el escenario exacto que causaba el bug

            // Act & Assert
            // Assert.DoesNotThrow(() => _sut.MetodoFijado(...));
        }}

        /// <summary>
        /// Edge case detectado en el analisis tecnico
        /// </summary>
        {attr}
        public void {class_name}_EdgeCase_DebeComportarseCorrectamente()
        {{
            // Arrange
            // TODO: configurar caso borde segun ANALISIS_TECNICO.md

            // Act
            // var resultado = _sut.MetodoFijado(valorBorde);

            // Assert
            // TODO: verificar comportamiento esperado
        }}
    }}
}}
"""

    def _build_qa_section(
        self, test_content: str, ticket_id: str, modified_files: list, framework: str
    ) -> str:
        """Genera el bloque Markdown para inyectar en el prompt de QA."""
        test_lines = test_content.count("\n")
        test_count = test_content.count("[TestMethod]") + test_content.count("[Test]")

        return f"""## Tests Unitarios Generados — Ticket {ticket_id}

**Framework:** {framework}
**Tests generados:** {test_count}
**Archivo:** `generated_tests/Tests_{ticket_id}_*.cs`
**Archivos cubiertos:** {', '.join(Path(f).name for f in modified_files[:3])}

### Tests a Validar

Como parte de tu revision QA, verifica que los tests generados:
1. Cubren el caso que causaba el bug original
2. El caso feliz post-fix funciona correctamente
3. No hay casos borde criticos sin cubrir

### Codigo de Tests (para revision)

```csharp
{test_content[:1500]}{"..." if len(test_content) > 1500 else ""}
```

### Checklist QA — Tests

- [ ] Los tests representan correctamente el comportamiento esperado
- [ ] El caso del bug original esta cubierto
- [ ] Los tests compilarian sin errores
- [ ] Aprobar agregar al proyecto de tests del repositorio
"""

    def _detect_test_framework(self) -> str:
        """Detecta el framework de tests del proyecto."""
        workspace = self._config.get("workspace_root", "")
        if workspace:
            ws = Path(workspace)
            # Buscar references en .csproj
            for csproj in ws.rglob("*.csproj"):
                try:
                    content = csproj.read_text(encoding="utf-8", errors="ignore")
                    if "NUnit" in content:
                        return "NUnit"
                    if "xunit" in content.lower():
                        return "xUnit"
                    if "MSTest" in content or "Microsoft.VisualStudio.TestTools" in content:
                        return "MSTest"
                except Exception:
                    pass
        return "MSTest"  # default para proyectos .NET legacy

    def _extract_modified_files(self, dev_completado: str, svn_changes: str) -> list:
        """Extrae archivos modificados de DEV_COMPLETADO.md y SVN_CHANGES.md."""
        files = set()
        combined = (dev_completado or "") + "\n" + (svn_changes or "")
        for match in re.finditer(r"[\w.\-/\\]+\.(?:cs|aspx|vb|aspx\.cs)", combined):
            files.add(match.group(0).replace("\\", "/"))
        return list(files)[:10]

    def _find_inc_file(self, folder: Path) -> str:
        """Retorna el nombre del archivo INC en la carpeta del ticket."""
        for f in folder.glob("INC-*.md"):
            return f.name
        return "INCIDENTE.md"

    def _read_file(self, fpath) -> str:
        if fpath and Path(fpath).exists():
            try:
                return Path(fpath).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        return ""

    def _load_config(self) -> dict:
        cfg = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
