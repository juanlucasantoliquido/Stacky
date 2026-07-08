/**
 * pipelineStepSnippets.ts — Plan 97 F1-bis (ampliado en F1-ter)
 * Biblioteca ESTÁTICA de acciones de pipeline prehechas (step snippets).
 * Cada snippet produce un StepDraft real y editable (specBuilder.ts).
 * Provider-neutral: sin interpolación $(VAR)/$VAR (paridad ADO+GitLab).
 */
import type { StepDraft } from "./specBuilder";
import type { StackId } from "./pipelinePresets";

export type SnippetCategory =
  | "dependencias" | "lint" | "test" | "build" | "publicar" | "calidad"
  | "seguridad" | "versionar"   // F1-ter — categorías nuevas
  | "infra";                    // F1-ter v4 (C3) — hadolint/yamllint/terraform/helm/ansible

export const SNIPPET_CATEGORIES: readonly SnippetCategory[] = [
  "dependencias", "lint", "test", "build", "publicar", "calidad",
  "seguridad", "versionar", "infra",
];

export interface StepSnippet {
  id: string;               // único, kebab-case
  category: SnippetCategory;
  label: string;            // texto corto en la UI (español)
  description: string;      // 1 frase en llano
  // v4 (C2) — metadata OPCIONAL para plug-and-play. NO afecta a build():
  // son pistas para la UI, nunca se copian al StepDraft resultante.
  needsEdit?: boolean;      // true si el script trae un literal que el operador DEBE editar (ej. tag de imagen)
  requires?: string;        // herramienta que debe existir en el runner (ej. "docker"); undefined = toolchain estándar del stack
  stacks: readonly StackId[]; // Plan 104 F0 — a qué stacks aplica; [] = "all"
  build: () => StepDraft;   // función pura, siempre devuelve StepDraft NUEVO
}

function step(name: string, script: string): StepDraft {
  return { name, script, env: {} };
}

export const PIPELINE_STEP_SNIPPETS: readonly StepSnippet[] = [
  // ── dependencias ──
  { id: "dep-pip-install", category: "dependencias", label: "pip install (requirements.txt)", description: "Instala dependencias Python con pip.", stacks: ["python"], build: () => step("instalar-dependencias", "pip install -r requirements.txt") },
  { id: "dep-poetry-install", category: "dependencias", label: "poetry install", description: "Instala dependencias con Poetry.", stacks: ["python"], build: () => step("instalar-dependencias", "poetry install --no-interaction") },
  { id: "dep-npm-ci", category: "dependencias", label: "npm ci", description: "Instala dependencias Node de forma reproducible.", stacks: ["node"], build: () => step("instalar-dependencias", "npm ci") },
  { id: "dep-yarn-install", category: "dependencias", label: "yarn install (frozen)", description: "Instala dependencias con Yarn sin tocar el lockfile.", stacks: ["node"], build: () => step("instalar-dependencias", "yarn install --frozen-lockfile") },
  { id: "dep-dotnet-restore", category: "dependencias", label: "dotnet restore", description: "Restaura paquetes NuGet.", stacks: ["dotnet"], build: () => step("restaurar", "dotnet restore") },
  // ── lint ──
  { id: "lint-flake8", category: "lint", label: "flake8", description: "Chequeo de estilo Python con flake8.", stacks: ["python"], build: () => step("lint", "python -m flake8 .") },
  { id: "lint-black-check", category: "lint", label: "black --check", description: "Verifica formato Python con black (sin modificar).", stacks: ["python"], build: () => step("lint-formato", "python -m black --check .") },
  { id: "lint-ruff", category: "lint", label: "ruff check", description: "Linter Python rápido con ruff.", stacks: ["python"], build: () => step("lint", "python -m ruff check .") },
  { id: "lint-eslint", category: "lint", label: "npm run lint", description: "Corre el script de lint de Node si existe.", stacks: ["node"], build: () => step("lint", "npm run lint --if-present") },
  { id: "lint-prettier-check", category: "lint", label: "prettier --check", description: "Verifica formato con Prettier (sin modificar).", stacks: ["node"], build: () => step("lint-formato", "npx prettier --check .") },
  { id: "lint-dotnet-format", category: "lint", label: "dotnet format --verify", description: "Verifica formato .NET sin aplicar cambios.", stacks: ["dotnet"], build: () => step("lint-formato", "dotnet format --verify-no-changes") },
  // ── test ──
  { id: "test-pytest", category: "test", label: "pytest", description: "Corre la suite de tests Python.", stacks: ["python"], build: () => step("test", "python -m pytest -q") },
  { id: "test-pytest-cov", category: "test", label: "pytest + cobertura", description: "Corre pytest generando reporte de cobertura XML.", stacks: ["python"], build: () => step("test-cobertura", "python -m pytest --cov --cov-report=xml") },
  { id: "test-npm-test", category: "test", label: "npm test", description: "Corre el script de tests de Node si existe.", stacks: ["node"], build: () => step("test", "npm test --if-present") },
  { id: "test-jest", category: "test", label: "jest --ci", description: "Corre Jest en modo CI.", stacks: ["node"], build: () => step("test", "npx jest --ci") },
  { id: "test-dotnet", category: "test", label: "dotnet test", description: "Corre los tests .NET en Release.", stacks: ["dotnet"], build: () => step("test", "dotnet test --no-build --configuration Release") },
  // ── build ──
  { id: "build-npm", category: "build", label: "npm run build", description: "Compila el proyecto Node si existe el script.", stacks: ["node"], build: () => step("compilar", "npm run build --if-present") },
  { id: "build-dotnet-release", category: "build", label: "dotnet build (Release)", description: "Compila la solución .NET en Release.", stacks: ["dotnet"], build: () => step("compilar", "dotnet build --configuration Release --no-restore") },
  { id: "build-python", category: "build", label: "python -m build", description: "Empaqueta el proyecto Python (sdist+wheel).", stacks: ["python"], build: () => step("compilar", "python -m build") },
  { id: "build-docker", category: "build", label: "docker build", description: "Construye la imagen Docker (editá el tag).", needsEdit: true, requires: "docker", stacks: [], build: () => step("docker-build", "docker build -t myapp:latest .") },
  // ── publicar / artefactos ──
  { id: "pub-docker-push", category: "publicar", label: "docker push", description: "Publica la imagen Docker (editá el tag).", needsEdit: true, requires: "docker", stacks: [], build: () => step("docker-push", "docker push myapp:latest") },
  { id: "pub-dotnet-publish", category: "publicar", label: "dotnet publish", description: "Publica el binario .NET a ./publish.", stacks: ["dotnet"], build: () => step("publicar", "dotnet publish -c Release -o ./publish") },
  { id: "pub-npm-pack", category: "publicar", label: "npm pack", description: "Genera el tarball del paquete npm.", stacks: ["node"], build: () => step("empaquetar", "npm pack") },
  { id: "pub-tar-dist", category: "publicar", label: "tar dist/", description: "Empaqueta la carpeta dist en un .tgz (tar disponible en Windows y Linux modernos).", stacks: [], build: () => step("empaquetar", "tar -czf dist.tgz dist") },
  // ── calidad ──
  { id: "qual-sonar", category: "calidad", label: "sonar-scanner", description: "Análisis de calidad con SonarQube (lee sonar-project.properties).", requires: "sonar-scanner", stacks: [], build: () => step("calidad", "sonar-scanner") },
  { id: "qual-coverage-report", category: "calidad", label: "coverage report", description: "Muestra el reporte de cobertura Python en consola.", stacks: ["python"], build: () => step("cobertura", "python -m coverage report") },
  // ── F1-ter — dependencias (más stacks) ──
  { id: "dep-composer-install", category: "dependencias", label: "composer install", description: "Instala dependencias PHP con Composer.", stacks: ["php"], build: () => step("instalar-dependencias", "composer install --no-interaction --prefer-dist") },
  { id: "dep-go-download", category: "dependencias", label: "go mod download", description: "Descarga módulos Go.", stacks: ["go"], build: () => step("instalar-dependencias", "go mod download") },
  { id: "dep-cargo-fetch", category: "dependencias", label: "cargo fetch", description: "Descarga dependencias Rust.", stacks: ["rust"], build: () => step("instalar-dependencias", "cargo fetch") },
  // ── F1-ter — lint (más stacks) ──
  { id: "lint-go-vet", category: "lint", label: "go vet", description: "Análisis estático de Go.", stacks: ["go"], build: () => step("lint", "go vet ./...") },
  { id: "lint-cargo-clippy", category: "lint", label: "cargo clippy", description: "Linter de Rust con Clippy (falla en warnings).", stacks: ["rust"], build: () => step("lint", "cargo clippy -- -D warnings") },
  // ── F1-ter — build (más stacks) ──
  { id: "build-go", category: "build", label: "go build", description: "Compila todos los paquetes Go.", stacks: ["go"], build: () => step("compilar", "go build ./...") },
  { id: "build-cargo-release", category: "build", label: "cargo build (release)", description: "Compila Rust en modo release.", stacks: ["rust"], build: () => step("compilar", "cargo build --release") },
  { id: "build-maven", category: "build", label: "mvn package", description: "Empaqueta un proyecto Maven (sin tests).", stacks: ["java"], build: () => step("compilar", "mvn -B -DskipTests package") },
  { id: "build-gradle", category: "build", label: "gradle build", description: "Compila y arma con Gradle.", stacks: ["java"], build: () => step("compilar", "./gradlew build") },
  // ── F1-ter — test (más stacks) ──
  { id: "test-go", category: "test", label: "go test", description: "Corre los tests de Go.", stacks: ["go"], build: () => step("test", "go test ./...") },
  { id: "test-cargo", category: "test", label: "cargo test", description: "Corre los tests de Rust.", stacks: ["rust"], build: () => step("test", "cargo test") },
  { id: "test-maven", category: "test", label: "mvn verify", description: "Corre la fase verify de Maven (tests + checks).", stacks: ["java"], build: () => step("test", "mvn -B verify") },
  { id: "test-phpunit", category: "test", label: "phpunit", description: "Corre los tests PHP con PHPUnit.", stacks: ["php"], build: () => step("test", "vendor/bin/phpunit") },
  // ── F1-ter — publicar (más) ──
  { id: "pub-twine-check", category: "publicar", label: "twine check", description: "Valida los artefactos Python antes de publicar.", stacks: ["python"], build: () => step("validar-artefacto", "python -m twine check dist/*") },
  // ── F1-ter — seguridad ──
  { id: "sec-npm-audit", category: "seguridad", label: "npm audit", description: "Reporta vulnerabilidades de dependencias Node.", stacks: ["node"], build: () => step("auditar-seguridad", "npm audit --audit-level=high") },
  { id: "sec-pip-audit", category: "seguridad", label: "pip-audit", description: "Reporta vulnerabilidades de dependencias Python.", requires: "pip-audit", stacks: ["python"], build: () => step("auditar-seguridad", "python -m pip_audit") },
  { id: "sec-dotnet-vuln", category: "seguridad", label: "dotnet list --vulnerable", description: "Lista paquetes NuGet con vulnerabilidades conocidas.", stacks: ["dotnet"], build: () => step("auditar-seguridad", "dotnet list package --vulnerable") },
  { id: "sec-trivy-fs", category: "seguridad", label: "trivy fs", description: "Escanea el filesystem por vulnerabilidades con Trivy.", requires: "trivy", stacks: [], build: () => step("auditar-seguridad", "trivy fs .") },
  // ── F1-ter — versionar ──
  { id: "ver-git-describe", category: "versionar", label: "git describe", description: "Imprime la versión derivada del último tag Git.", stacks: [], build: () => step("version", "git describe --tags --always") },
  { id: "ver-git-short-sha", category: "versionar", label: "git short SHA", description: "Imprime el SHA corto del commit actual.", stacks: [], build: () => step("version", "git rev-parse --short HEAD") },
  // ── v4 C3 — lint / typecheck / formato (toolchain nativo) ──
  { id: "lint-mypy", category: "lint", label: "mypy", description: "Chequeo de tipos estático Python con mypy.", requires: "mypy", stacks: ["python"], build: () => step("typecheck", "python -m mypy .") },
  { id: "lint-tsc", category: "lint", label: "tsc --noEmit", description: "Chequeo de tipos TypeScript sin emitir salida.", stacks: ["node"], build: () => step("typecheck", "npx tsc --noEmit") },
  { id: "lint-cargo-fmt", category: "lint", label: "cargo fmt --check", description: "Verifica formato Rust sin modificar.", stacks: ["rust"], build: () => step("lint-formato", "cargo fmt --check") },
  { id: "lint-gofmt", category: "lint", label: "gofmt -l", description: "Lista archivos Go mal formateados.", stacks: ["go"], build: () => step("lint-formato", "gofmt -l .") },
  // ── v4 C3 — test (más) ──
  { id: "test-pytest-fast", category: "test", label: "pytest -x (falla rápido)", description: "Corre pytest y corta en el primer fallo.", stacks: ["python"], build: () => step("test", "python -m pytest -x -q") },
  { id: "test-vitest", category: "test", label: "vitest run", description: "Corre los tests con Vitest en modo CI.", stacks: ["node"], build: () => step("test", "npx vitest run") },
  { id: "test-go-race", category: "test", label: "go test -race", description: "Corre los tests de Go con detector de carreras.", stacks: ["go"], build: () => step("test", "go test -race ./...") },
  // ── v4 C3 — seguridad (más) ──
  { id: "sec-bandit", category: "seguridad", label: "bandit", description: "Análisis de seguridad de código Python.", requires: "bandit", stacks: ["python"], build: () => step("auditar-seguridad", "python -m bandit -r . -q") },
  { id: "sec-gitleaks", category: "seguridad", label: "gitleaks", description: "Busca secretos filtrados en el repo.", requires: "gitleaks", stacks: [], build: () => step("auditar-secretos", "gitleaks detect --no-banner") },
  { id: "sec-semgrep", category: "seguridad", label: "semgrep", description: "Análisis estático de seguridad multi-lenguaje.", requires: "semgrep", stacks: [], build: () => step("auditar-seguridad", "semgrep scan --error") },
  // ── v4 C3 — infra (categoría nueva) ──
  { id: "infra-hadolint", category: "infra", label: "hadolint", description: "Linter de Dockerfile.", requires: "hadolint", stacks: [], build: () => step("lint-dockerfile", "hadolint Dockerfile") },
  { id: "infra-yamllint", category: "infra", label: "yamllint", description: "Linter de archivos YAML.", requires: "yamllint", stacks: [], build: () => step("lint-yaml", "yamllint .") },
  { id: "infra-tf-fmt", category: "infra", label: "terraform fmt -check", description: "Verifica formato Terraform sin modificar.", requires: "terraform", stacks: [], build: () => step("tf-formato", "terraform fmt -check -recursive") },
  { id: "infra-tf-validate", category: "infra", label: "terraform validate", description: "Valida la configuración Terraform (requiere init previo).", requires: "terraform", stacks: [], build: () => step("tf-validar", "terraform validate") },
  { id: "infra-helm-lint", category: "infra", label: "helm lint", description: "Valida un chart de Helm.", requires: "helm", stacks: [], build: () => step("helm-lint", "helm lint .") },
  { id: "infra-helm-package", category: "infra", label: "helm package", description: "Empaqueta un chart de Helm.", requires: "helm", stacks: [], build: () => step("helm-package", "helm package .") },
  { id: "infra-ansible-lint", category: "infra", label: "ansible-lint", description: "Linter de playbooks de Ansible.", requires: "ansible-lint", stacks: [], build: () => step("ansible-lint", "ansible-lint") },
];

// Plan 104 F0 — filtro por stack + guard de validez de StackId.
export function filterSnippetsByStack(
  snippets: readonly StepSnippet[], stack: StackId | "all"
): readonly StepSnippet[] {
  if (stack === "all") return snippets;
  return snippets.filter((s) => s.stacks.length === 0 || s.stacks.includes(stack));
}

export const STACK_OPTIONS: readonly (StackId | "all")[] = [
  "all", "dotnet", "node", "python", "go", "rust", "java", "php", "generic",
];

// [C5] guard defensivo — si el detector de stack (plan 97) evoluciona y
// devuelve un valor no listado en STACK_OPTIONS, el filtro NO muta (degrada
// silencioso, sin romper). Exportado (no solo local al builder) para que sea
// testeable de forma pura, aquí junto a STACK_OPTIONS.
export function isStackId(x: unknown): x is StackId | "all" {
  return typeof x === "string" && (STACK_OPTIONS as readonly string[]).includes(x);
}

export function getSnippetsByCategory(cat: SnippetCategory): readonly StepSnippet[] {
  return PIPELINE_STEP_SNIPPETS.filter((s) => s.category === cat);
}
