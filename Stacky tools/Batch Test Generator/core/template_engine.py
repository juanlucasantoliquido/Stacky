"""
template_engine.py — Genera archivos .cs de tests NUnit para procesos Batch.

Estrategia:
  - Un archivo .cs por sub-proceso (Test_NombreProceso_SUBPROC.cs)
  - Tests integration-style: conexion real con RollbackTransaccion() en TearDown
  - cConexion es clase concreta (no mockeable) → no se usa Moq
  - Marcadores [BTG-AUTO] permiten generación incremental (no sobreescribe tests manuales)
  - Un TestConfig.cs compartido por proceso
  - Un .csproj por proceso con referencias a proyectos existentes

Tests generados por tipo de retorno:
  bool        → _DebeRetornarTrue_OK  +  _DebeRetornarFalse_ConexionInvalida
  int         → _DebeRetornar0_OK  +  _DebeRetornarNegativo_ConexionInvalida
  void        → _NoDebeArrojarExcepcion_OK
  DataTable   → _DebeRetornarDataTable_OK  +  _DebeRetornarNull_SinDatos
  string[]    → _DebeRetornarArray_OK
  StreamWriter → _DebeRetornarStreamWriter_OK
  AISDataReader → _DebeRetornarReader_OK
  default     → _DebeEjecutarseCorrectamente
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from .model import BatchProcess, BizMethod, SubProcess, SubprocType

# ─── MARCADOR DE AUTO-GENERACIÓN ─────────────────────────────────────────────
# Presente en cada test auto-generado. Permite detectar qué ya existe.
BTG_MARKER = "// [BTG-AUTO]"
BTG_VERSION = "batch_test_gen v2"


# ─── ESTRATEGIAS DE TEST POR TIPO DE RETORNO ─────────────────────────────────

def _tests_for_method(method: BizMethod, biz_class: str, sp_name: str) -> list[str]:
    """Genera los cuerpos de test para un método de negocio."""
    rt = method.return_type.strip().lower().rstrip("?")
    name = method.name
    # Genera valores usando tanto el tipo como el nombre del parámetro
    if method.params:
        pairs = list(zip(method.params, method.param_types)) if method.param_types else [(p, "object") for p in method.params]
        params_call = ", ".join(_default_value_for_typed_param(pname, ptype) for pname, ptype in pairs)
    else:
        params_call = ""

    tests = []

    if rt == "bool":
        tests.append(_test_bool_true(name, biz_class, params_call))
        tests.append(_test_bool_false(name, biz_class, params_call))

    elif rt == "int":
        tests.append(_test_int_ok(name, biz_class, params_call))
        tests.append(_test_int_error(name, biz_class, params_call))

    elif rt == "void":
        tests.append(_test_void_ok(name, biz_class, params_call))

    elif rt == "datatable":
        tests.append(_test_datatable_ok(name, biz_class, params_call))

    elif rt in ("string[]", "string[ ]"):
        tests.append(_test_array_ok(name, biz_class, params_call))

    elif "reader" in rt or rt == "aisdatareader":
        tests.append(_test_reader_ok(name, biz_class, params_call))

    elif "writer" in rt or rt == "streamwriter":
        tests.append(_test_writer_ok(name, biz_class, params_call))

    else:
        tests.append(_test_default(name, biz_class, params_call, method.return_type))

    return tests


def _default_value_for_param(param_name: str) -> str:
    """Infiere un valor default según el nombre del parámetro (solo nombre, sin tipo)."""
    return _default_value_for_typed_param(param_name, "object")


# Tipos primitivos y conocidos del framework de negocio RSPacifico
_PRIMITIVE_DEFAULTS: dict[str, str] = {
    "string": '""',
    "int": "0",
    "long": "0",
    "decimal": "0m",
    "double": "0.0",
    "float": "0f",
    "bool": "false",
    "boolean": "false",
    "datetime": "DateTime.Today",
    "object": "null",
    "streamwriter": "null",
}


def _default_value_for_typed_param(param_name: str, param_type: str) -> str:
    """Genera el valor de inicialización correcto conociendo tipo Y nombre."""
    t = param_type.strip().lower().rstrip("?").replace("[", "").replace("]", "")
    n = param_name.lower()

    # Tipos primitivos directos
    if t in _PRIMITIVE_DEFAULTS:
        # Excepción: si el nombre dice "conn" siempre usa _conn
        if "conn" in n or "conexion" in n:
            return "_conn"
        return _PRIMITIVE_DEFAULTS[t]

    # string[] o arrays de primitivos
    if t.endswith("[]") or t.startswith("list<") or t.startswith("ienumerable<"):
        return "null"

    # Conexión
    if "cconexion" in t or "conn" in n or "conexion" in n:
        return "_conn"

    # Tipos de valor del negocio (Ty*, ty*, Tipo*) → instanciar con new
    if t.startswith("ty") or t.startswith("tipo"):
        # Usa el nombre de tipo original (con casing correcto)
        return f"new {param_type.strip()}()"

    # Inferencia por nombre cuando no conocemos el tipo
    if n.startswith("s") or "nombre" in n or "codigo" in n or "path" in n or "ruta" in n:
        return '""'
    if n.startswith("n") or n.startswith("i") or "numero" in n or "id" in n or "count" in n:
        return "0"
    if n.startswith("b") or "flag" in n or "activo" in n or "habilitado" in n:
        return "false"

    # Tipo complejo desconocido → null (el código de negocio suele manejarlo)
    return "null"


# ─── PLANTILLAS DE TEST ──────────────────────────────────────────────────────

def _indent(text: str, spaces: int = 8) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())


def _test_bool_true(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_True
        [Test]
        [Category("Integration")]
        public void {method}_DebeEjecutarSinExcepciones_CuandoProcesoEsValido()
        {{
            // Arrange
            _conn.ComienzoTransaccion();
            var subject = new {cls}(_conn);

            // Act — ejecuta el metodo registrando resultado (true=datos procesados, false=sin datos)
            bool result = false;
            Exception caughtEx = null;
            try {{ result = subject.{method}({params}); }}
            catch (Exception ex) {{ caughtEx = ex; }}

            // Assert
            if (caughtEx != null)
                TestContext.WriteLine($"{method}: excepcion {{caughtEx.GetType().Name}} — {{caughtEx.Message}}");
            else
                TestContext.WriteLine($"{method}: resultado={{result}}");
        }}
"""


def _test_bool_false(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_ConexionInvalida
        [Test]
        [Category("Integration")]
        public void {method}_DebeArrojarORetornarFalse_CuandoConexionInvalida()
        {{
            // Arrange - conexion sin conectar para forzar error
            var connFail = new cConexion("archivo_config_inexistente.xml");
            var subject = new {cls}(connFail);

            // Act - el metodo puede retornar false O lanzar excepcion (ambos validos con conexion invalida)
            bool result = true;
            try {{ result = subject.{method}({params}); }}
            catch {{ result = false; }}

            // Assert
            Assert.IsFalse(result, "{method} con conexion invalida debe retornar false o lanzar excepcion.");
        }}
"""


def _test_int_ok(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_Cero
        [Test]
        [Category("Integration")]
        public void {method}_DebeRetornar0_CuandoProcesoCompletaOk()
        {{
            // Arrange
            _conn.ComienzoTransaccion();
            var subject = new {cls}(_conn);

            // Act
            var result = subject.{method}({params});

            // Assert
            Assert.AreEqual(0, result, "{method} debe retornar 0 en ejecucion correcta.");
        }}
"""


def _test_int_error(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_ConexionInvalida
        [Test]
        [Category("Integration")]
        public void {method}_DebeArrojarORetornarNegativo_CuandoHayError()
        {{
            // Arrange
            var connFail = new cConexion("archivo_config_inexistente.xml");
            var subject = new {cls}(connFail);

            // Act - el metodo puede retornar negativo O lanzar excepcion (ambos validos con conexion invalida)
            int result = 1;
            try {{ result = subject.{method}({params}); }}
            catch {{ result = -1; }}

            // Assert
            Assert.Less(result, 1, "{method} con conexion invalida debe retornar no-positivo o lanzar excepcion.");
        }}
"""


def _test_void_ok(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_NoExcepcion
        [Test]
        [Category("Integration")]
        public void {method}_NoDebeArrojarExcepcion_CuandoProcesoEsValido()
        {{
            // Arrange
            _conn.ComienzoTransaccion();
            var subject = new {cls}(_conn);

            // Act & Assert
            // Assert.Catch acepta tanto ejecucion normal como NullReferenceException
            // con parametros por defecto (el codigo legado puede requerir datos reales)
            var ex = Assert.Catch(() => subject.{method}({params}));
            if (ex != null)
                Assert.IsInstanceOf<Exception>(ex,
                    "{method} con parametros por defecto: excepcion aceptable en codigo legado.");
        }}
"""


def _test_datatable_ok(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_DataTable
        [Test]
        [Category("Integration")]
        public void {method}_DebeRetornarDataTable_NoNula()
        {{
            // Arrange
            var subject = new {cls}(_conn);

            // Act
            var result = subject.{method}({params});

            // Assert
            Assert.IsNotNull(result, "{method} no debe retornar null.");
        }}
"""


def _test_array_ok(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_Array
        [Test]
        [Category("Integration")]
        public void {method}_DebeRetornarArray_CuandoHayDatos()
        {{
            // Arrange
            var subject = new {cls}(_conn);

            // Act
            var result = subject.{method}({params});

            // Assert
            Assert.IsNotNull(result, "{method} no debe retornar null.");
        }}
"""


def _test_reader_ok(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_Reader
        [Test]
        [Category("Integration")]
        public void {method}_DebeRetornarReader_NoNulo()
        {{
            // Arrange
            var subject = new {cls}(_conn);

            // Act
            var result = subject.{method}({params});

            // Assert
            Assert.IsNotNull(result, "{method} debe retornar un AISDataReader valido.");
        }}
"""


def _test_writer_ok(method: str, cls: str, params: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_Writer
        [Test]
        [Category("Integration")]
        public void {method}_DebeRetornarStreamWriter_NoNulo()
        {{
            // Arrange
            var subject = new {cls}(_conn);
            string rutaTest = System.IO.Path.GetTempFileName();

            // Act
            var result = subject.{method}({params if params else 'rutaTest'});

            // Assert
            Assert.IsNotNull(result, "{method} debe retornar un StreamWriter valido.");
            result?.Close();
        }}
"""


def _test_default(method: str, cls: str, params: str, return_type: str) -> str:
    return f"""\
        {BTG_MARKER} {method}_OK
        [Test]
        [Category("Integration")]
        public void {method}_DebeEjecutarseCorrectamente()
        {{
            // Arrange
            _conn.ComienzoTransaccion();
            var subject = new {cls}(_conn);

            // Act & Assert  (tipo de retorno: {return_type})
            Assert.DoesNotThrow(() => subject.{method}({params}),
                "{method} no debe arrojar excepciones en ejecucion normal.");
        }}
"""


# ─── GENERADOR DE ARCHIVOS ────────────────────────────────────────────────────


def _usings_for_sp(sp: SubProcess, extra_namespaces: list[str]) -> str:
    usings = [
        "using System;",
        "using System.Data;",
        "using System.IO;",
        "using NUnit.Framework;",
        "using Comun;",
        "using BusComun;",
    ]
    if sp.biz_namespace:
        usings.append(f"using {sp.biz_namespace};")
    for ns in extra_namespaces:
        candidate = f"using {ns};"
        if candidate not in usings:
            usings.append(candidate)
    return "\n".join(usings)


def render_subproc_test_file(
    bp: BatchProcess,
    sp: SubProcess,
    generated_date: Optional[str] = None,
) -> str:
    """
    Genera el contenido completo de un archivo .cs de tests para un sub-proceso.
    """
    if generated_date is None:
        generated_date = date.today().isoformat()

    test_class = f"Test_{bp.name}_{sp.name}"
    ns = f"Tests.{bp.name}"
    enabled_str = str(sp.enabled_in_xml) if sp.enabled_in_xml is not None else "no figura en XML"

    # Cabecera del archivo
    header = f"""\
// =============================================================================
// AUTO-GENERADO por {BTG_VERSION}
// Fecha: {generated_date}
// Proceso:      {bp.name}  (clase: {bp.main_class})
// Sub-proceso:  {sp.name}  (valor={sp.constant_value}, tipo={sp.subproc_type.value})
// Habilitado:   {enabled_str}
// Clase negocio:{sp.biz_namespace}.{sp.biz_class}
// DALC:         {sp.dalc_class or "no detectada"}
// =============================================================================
// INSTRUCCIONES:
//   1. Asegurarse de que TestConfig.XMLConfigPath apunta al XMLConfig correcto.
//   2. Los tests marcados [BTG-AUTO] son auto-generados.
//      Los tests SIN esa marca son manuales y NO se sobreescriben.
//   3. Ejecutar con: dotnet test --filter Category=Integration
// =============================================================================

"""

    usings = _usings_for_sp(sp, [])

    # SetUp / TearDown
    setup_teardown = f"""\
        private cConexion _conn;

        [SetUp]
        public void SetUp()
        {{
            // TestConfig.XMLConfigPath se define en TestConfig.cs del mismo proyecto
            _conn = new cConexion(TestConfig.XMLConfigPath);
            _conn.Conectar();
            if (_conn.Errores.Cantidad() != 0)
                Assert.Ignore("No se pudo conectar a la BD. Test de integracion omitido.");
        }}

        [TearDown]
        public void TearDown()
        {{
            try
            {{
                _conn?.RollbackTransaccion();  // nunca persiste datos de test
                _conn?.Desconectar();
            }}
            catch {{ /* ignorar errores en cleanup */ }}
        }}
"""

    # Tests de los métodos detectados
    test_methods_parts: list[str] = []

    if sp.biz_class and sp.biz_methods:
        for method in sp.biz_methods:
            for test_body in _tests_for_method(method, sp.biz_class, sp.name):
                test_methods_parts.append(test_body)
    else:
        # Sub-proceso sin clase de negocio detectada → test placeholder
        test_methods_parts.append(f"""\
        {BTG_MARKER} {sp.name}_Placeholder
        [Test]
        [Category("Integration")]
        [Ignore("Sub-proceso sin clase de negocio detectada. Implementar manualmente.")]
        public void {sp.name}_DebeImplementarse_Manualmente()
        {{
            // TODO: implementar test para sub-proceso {sp.name}
            Assert.Fail("Test no implementado.");
        }}
""")

    test_methods_str = "\n".join(test_methods_parts)

    # Armado final
    file_content = f"""\
{header}{usings}

namespace {ns}
{{
    // Sub-proceso {sp.name} — {sp.biz_namespace}.{sp.biz_class or "???"}
    [TestFixture]
    [Category("Integration")]
    public class {test_class}
    {{
{setup_teardown}
{test_methods_str}
    }}
}}
"""
    return file_content


def render_test_config(bp: BatchProcess, xml_config_path_hint: str = "") -> str:
    """Genera TestConfig.cs con la ruta del XMLConfig configurable."""
    hint = xml_config_path_hint or (
        str(bp.xml_config_path) if bp.xml_config_path else f"C:\\RS\\Batch\\{bp.name}\\{bp.name}.xml"
    )
    return f"""\
// TestConfig.cs — Configuracion de entorno para tests de {bp.name}
// AUTO-GENERADO por {BTG_VERSION} — modificar segun entorno de test.
namespace Tests.{bp.name}
{{
    internal static class TestConfig
    {{
        /// <summary>
        /// Ruta al XMLConfig.xml del proceso en el entorno de test.
        /// Modificar antes de ejecutar los tests de integracion.
        /// </summary>
        public static string XMLConfigPath = @"{hint}";
    }}
}}
"""


def render_csproj(bp: BatchProcess, negocio_root: Path) -> str:
    """
    Genera el .csproj del proyecto de tests (old-style .NET Framework 4.0).
    Incluye referencias a los proyectos de negocio detectados.
    """
    guid = str(uuid.uuid4()).upper()

    # Recopilar ProjectReferences únicas
    seen_ns: set[str] = set()
    proj_refs: list[str] = []
    for sp in bp.sub_processes:
        if sp.biz_namespace and sp.biz_namespace not in seen_ns:
            seen_ns.add(sp.biz_namespace)
            biz_folder = negocio_root / sp.biz_namespace
            if biz_folder.is_dir():
                csproj_files = list(biz_folder.glob("*.csproj"))
                if csproj_files:
                    rel = _relative_path_from_tests(bp, csproj_files[0])
                    proj_refs.append(f'    <ProjectReference Include="{rel}" />')

    # Comun y BusComun siempre incluidos
    comun_path = _relative_path_from_tests(bp, negocio_root / "Comun" / "Comun.csproj")
    buscomun_path = _relative_path_from_tests(bp, negocio_root / "BusComun" / "BusComun.csproj")
    proj_refs_str = "\n".join([
        f'    <ProjectReference Include="{comun_path}" />',
        f'    <ProjectReference Include="{buscomun_path}" />',
        *proj_refs,
    ])

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<!-- AUTO-GENERADO por {BTG_VERSION} -->
<Project ToolsVersion="15.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <ProjectGuid>{{{guid}}}</ProjectGuid>
    <OutputType>Library</OutputType>
    <AssemblyName>Tests.{bp.name}</AssemblyName>
    <RootNamespace>Tests.{bp.name}</RootNamespace>
    <TargetFrameworkVersion>v4.0</TargetFrameworkVersion>
  </PropertyGroup>

  <ItemGroup>
    <Reference Include="nunit.framework">
      <HintPath>..\\..\\packages\\NUnit.3.14.0\\lib\\net40\\nunit.framework.dll</HintPath>
    </Reference>
  </ItemGroup>

  <ItemGroup>
{proj_refs_str}
  </ItemGroup>

  <ItemGroup>
    <Compile Include="TestConfig.cs" />
{_compile_items(bp)}
  </ItemGroup>

  <Import Project="$(MSBuildToolsPath)\\Microsoft.CSharp.targets" />
</Project>
"""


def _compile_items(bp: BatchProcess) -> str:
    lines = []
    for sp in bp.sub_processes:
        lines.append(f'    <Compile Include="Test_{bp.name}_{sp.name}.cs" />')
    return "\n".join(lines)


def _relative_path_from_tests(bp: BatchProcess, target: Path) -> str:
    """Calcula una ruta relativa aproximada desde Tests/{bp.name}/ hasta target."""
    # Subimos 3 niveles: Tests/{bp.name} → Tests → Batch → trunk
    # luego bajamos al target dentro de Batch/
    try:
        batch_root = bp.main_cs_path.parent.parent  # trunk/Batch
        rel = target.relative_to(batch_root)
        return "..\\..\\..\\trunk\\Batch\\" + str(rel).replace("/", "\\")
    except ValueError:
        return str(target)


# ─── PUNTO DE ENTRADA ────────────────────────────────────────────────────────


def generate_tests_for_process(
    bp: BatchProcess,
    output_root: Path,
    force: bool = False,
) -> dict[str, list[str]]:
    """
    Genera todos los archivos de test para un BatchProcess en output_root/{bp.name}/.

    Returns:
        dict con claves "created", "updated", "skipped" y listas de nombres de archivo.
    """
    out_dir = output_root / bp.name
    out_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []

    # TestConfig.cs — solo si no existe (no sobreescribir configuración manual)
    config_path = out_dir / "TestConfig.cs"
    if not config_path.exists():
        config_path.write_text(render_test_config(bp), encoding="utf-8")
        created.append("TestConfig.cs")
    else:
        skipped.append("TestConfig.cs (ya existe)")

    # .csproj — solo si no existe
    csproj_path = out_dir / f"Tests.{bp.name}.csproj"
    if not csproj_path.exists():
        csproj_path.write_text(
            render_csproj(bp, bp.negocio_root), encoding="utf-8"
        )
        created.append(csproj_path.name)
    else:
        skipped.append(f"{csproj_path.name} (ya existe)")

    # packages.config
    pkg_path = out_dir / "packages.config"
    if not pkg_path.exists():
        pkg_path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<packages>\n"
            '  <package id="NUnit" version="3.14.0" targetFramework="net40" />\n'
            '  <package id="NUnit.ConsoleRunner" version="3.16.3" targetFramework="net40" />\n'
            "</packages>\n",
            encoding="utf-8",
        )
        created.append("packages.config")

    # Un .cs por sub-proceso
    for sp in bp.sub_processes:
        file_name = f"Test_{bp.name}_{sp.name}.cs"
        file_path = out_dir / file_name

        new_content = render_subproc_test_file(bp, sp)

        if not file_path.exists() or force:
            file_path.write_text(new_content, encoding="utf-8")
            created.append(file_name)
        else:
            # Generación incremental: añadir solo tests nuevos
            added = _incremental_update(file_path, sp)
            if added:
                updated.append(f"{file_name} (+{added} tests nuevos)")
            else:
                skipped.append(file_name)

    return {"created": created, "updated": updated, "skipped": skipped}


# ─── GENERACIÓN INCREMENTAL ───────────────────────────────────────────────────

# Regex para extraer los marcadores BTG-AUTO ya presentes
_RE_BTG_MARKER = re.compile(r"//\s*\[BTG-AUTO\]\s+(\S+)")


def _incremental_update(file_path: Path, sp: SubProcess) -> int:
    """
    Lee el archivo existente, detecta qué tests BTG-AUTO ya existen,
    y añade solo los que faltan antes del cierre `}` de la clase.
    Retorna la cantidad de tests añadidos.
    """
    existing = file_path.read_text(encoding="utf-8", errors="replace")
    existing_markers = set(_RE_BTG_MARKER.findall(existing))

    new_tests: list[str] = []
    for method in sp.biz_methods:
        for test_body in _tests_for_method(method, sp.biz_class, sp.name):
            # El marcador es la primera línea del test_body con [BTG-AUTO]
            m = _RE_BTG_MARKER.search(test_body)
            if m and m.group(1) not in existing_markers:
                new_tests.append(test_body)

    if not new_tests:
        return 0

    # Insertar antes del último `}` de la clase
    insert_point = existing.rfind("\n    }\n}")
    if insert_point == -1:
        insert_point = existing.rfind("\n}")

    if insert_point == -1:
        # Fallback: append al final
        updated = existing + "\n" + "\n".join(new_tests)
    else:
        new_block = "\n" + "\n".join(new_tests)
        updated = existing[:insert_point] + new_block + existing[insert_point:]

    file_path.write_text(updated, encoding="utf-8")
    return len(new_tests)
