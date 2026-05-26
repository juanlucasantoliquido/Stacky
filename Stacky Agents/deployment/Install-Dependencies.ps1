#Requires -Version 5.1
<#
.SYNOPSIS
    Instala y repara dependencias locales para Stacky Agents.
.DESCRIPTION
    Prepara una maquina Windows para desarrollar, compilar y empaquetar
    Stacky Agents. Es idempotente: se puede ejecutar varias veces.
#>

[CmdletBinding()]
param(
    [switch]$NoPause,
    [switch]$SkipWinget,
    [switch]$SkipFrontend,
    [switch]$SkipBackend,
    [switch]$SkipVsCodeExtension,
    [switch]$SkipVSCodeInstall,
    [switch]$InstallInnoSetup,
    [switch]$ForceNpmInstall,
    [switch]$ForceVsix,
    [switch]$ValidateBuild
)

$ErrorActionPreference = "Stop"

$deploymentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Split-Path -Parent $deploymentDir
$backendDir = Join-Path $appRoot "backend"
$frontendDir = Join-Path $appRoot "frontend"
$vsixDir = Join-Path $appRoot "vscode_extension"
$logDir = Join-Path $appRoot "data\install_logs"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir ("install-dependencies-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

try {
    Start-Transcript -LiteralPath $logFile -Force | Out-Null
} catch {
    Write-Host "[WARN] No se pudo iniciar transcript: $($_.Exception.Message)" -ForegroundColor Yellow
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ">> $Message" -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Message)
    Write-Host "   [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "   [WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "   [ERROR] $Message" -ForegroundColor Red
}

function Update-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $knownPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts",
        "$env:LOCALAPPDATA\Programs\Python\Python312",
        "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts",
        "$env:ProgramFiles\nodejs",
        "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin",
        "${env:ProgramFiles(x86)}\Inno Setup 6"
    ) | Where-Object { $_ -and (Test-Path $_) }

    $env:Path = (@($machinePath, $userPath, $env:Path) + $knownPaths) -join ";"
}

function Invoke-CommandWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $appRoot,
        [int]$Retries = 2,
        [switch]$AllowFailure
    )

    $lastExit = 0
    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        Write-Host "   Ejecutando: $FilePath $($Arguments -join ' ')" -ForegroundColor DarkGray
        Push-Location $WorkingDirectory
        try {
            & $FilePath @Arguments
            $lastExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }

        if ($lastExit -eq 0 -or $null -eq $lastExit) {
            return
        }

        if ($attempt -lt $Retries) {
            Write-Warn "Fallo intento $attempt/$Retries (exit=$lastExit). Reintentando..."
            Start-Sleep -Seconds ([Math]::Min(8, 2 * $attempt))
        }
    }

    if ($AllowFailure) {
        Write-Warn "Comando fallido pero no bloqueante: $FilePath"
        return
    }

    throw "Comando fallido con exit code ${lastExit}: $FilePath $($Arguments -join ' ')"
}

function Install-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($SkipWinget) {
        throw "$Name no esta instalado y SkipWinget esta activo."
    }

    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "$Name no esta instalado y winget no esta disponible."
    }

    Write-Step "Instalando $Name con winget"
    Invoke-CommandWithRetry -FilePath $winget.Source -Arguments @(
        "install",
        "--id", $Id,
        "--source", "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--silent"
    ) -WorkingDirectory $appRoot -Retries 2
    Update-ProcessPath
}

function Get-PythonCandidate {
    $candidates = @(
        @{ Command = "py"; Args = @("-3.11") },
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "python"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        try {
            $command = [string]$candidate.Command
            $args = [string[]]$candidate.Args
            $versionOutput = & $command @args --version 2>&1
            if ($versionOutput -match "Python\s+(\d+)\.(\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -eq 3 -and $minor -ge 11) {
                    return [pscustomobject]@{
                        Command = $command
                        Args = $args
                        Version = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
                    }
                }
            }
        } catch {
        }
    }

    return $null
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)][object]$Python,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$WorkingDirectory = $appRoot,
        [int]$Retries = 2
    )

    Invoke-CommandWithRetry -FilePath ([string]$Python.Command) `
        -Arguments ([string[]]$Python.Args + $Arguments) `
        -WorkingDirectory $WorkingDirectory `
        -Retries $Retries
}

function Ensure-Python {
    Write-Step "Validando Python 3.11+"
    Update-ProcessPath
    $python = Get-PythonCandidate
    if (-not $python) {
        Install-WingetPackage -Id "Python.Python.3.11" -Name "Python 3.11"
        $python = Get-PythonCandidate
    }
    if (-not $python) {
        throw "No se pudo resolver Python 3.11+. Instala Python 3.11+ y vuelve a ejecutar."
    }
    Write-OK "Python $($python.Version)"
    return $python
}

function Ensure-Node {
    Write-Step "Validando Node.js 18+ y npm"
    Update-ProcessPath
    $node = Get-Command "node.exe" -ErrorAction SilentlyContinue
    $npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue

    $validNode = $false
    if ($node) {
        try {
            $nodeVersion = (& $node.Source --version 2>&1).Trim()
            if ($nodeVersion -match "v(\d+)\.(\d+)\.(\d+)") {
                $validNode = ([int]$Matches[1] -ge 18)
            }
        } catch {
        }
    }

    if (-not $validNode -or -not $npm) {
        Install-WingetPackage -Id "OpenJS.NodeJS.LTS" -Name "Node.js LTS"
        $node = Get-Command "node.exe" -ErrorAction SilentlyContinue
        $npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    }

    if (-not $node -or -not $npm) {
        throw "No se pudo resolver Node.js/npm. Instala Node.js 18+ y vuelve a ejecutar."
    }

    $nodeVersion = (& $node.Source --version 2>&1).Trim()
    $npmVersion = (& $npm.Source --version 2>&1).Trim()
    Write-OK "Node $nodeVersion / npm $npmVersion"
    return [pscustomobject]@{ Node = $node.Source; Npm = $npm.Source }
}

function Ensure-OptionalTools {
    Write-Step "Validando herramientas auxiliares"

    if (Get-Command "git.exe" -ErrorAction SilentlyContinue) {
        Write-OK "Git disponible"
    } else {
        try {
            Install-WingetPackage -Id "Git.Git" -Name "Git"
            Write-OK "Git instalado"
        } catch {
            Write-Warn "Git no disponible. El release se puede generar igual, pero sin commit hash."
        }
    }

    $codeAvailable = Get-Command "code.cmd" -ErrorAction SilentlyContinue
    if (-not $codeAvailable) {
        $codeAvailable = Get-Command "code" -ErrorAction SilentlyContinue
    }
    if (-not $codeAvailable -and -not $SkipVSCodeInstall) {
        try {
            Install-WingetPackage -Id "Microsoft.VisualStudioCode" -Name "Visual Studio Code"
            $codeAvailable = Get-Command "code.cmd" -ErrorAction SilentlyContinue
            if (-not $codeAvailable) {
                $codeAvailable = Get-Command "code" -ErrorAction SilentlyContinue
            }
        } catch {
            Write-Warn "No se pudo instalar VS Code automaticamente. La extension podra instalarse manualmente."
        }
    }
    if ($codeAvailable) {
        Write-OK "VS Code CLI disponible"
    } else {
        Write-Warn "VS Code CLI no disponible"
    }

    if ($InstallInnoSetup) {
        $iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
        if (-not $iscc) {
            $defaultIscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
            if (Test-Path $defaultIscc) {
                $iscc = Get-Item $defaultIscc
            }
        }
        if (-not $iscc) {
            try {
                Install-WingetPackage -Id "JRSoftware.InnoSetup" -Name "Inno Setup"
            } catch {
                Write-Warn "No se pudo instalar Inno Setup. El build portable/zip seguira funcionando."
            }
        } else {
            Write-OK "Inno Setup disponible"
        }
    }
}

function Ensure-Backend {
    param([Parameter(Mandatory = $true)][object]$Python)

    if ($SkipBackend) {
        Write-Warn "Backend omitido por parametro SkipBackend"
        return
    }

    Write-Step "Preparando backend Python"
    $venvDir = Join-Path $backendDir ".venv"
    $venvPythonPath = Join-Path $venvDir "Scripts\python.exe"

    if (-not (Test-Path $venvPythonPath)) {
        Write-Host "   Creando virtualenv en backend\.venv" -ForegroundColor DarkGray
        Invoke-Python -Python $Python -Arguments @("-m", "venv", $venvDir) -WorkingDirectory $backendDir -Retries 1
    }

    $venvPython = [pscustomobject]@{ Command = $venvPythonPath; Args = @(); Version = "venv" }
    Invoke-Python -Python $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel") -WorkingDirectory $backendDir -Retries 2
    Invoke-Python -Python $venvPython -Arguments @("-m", "pip", "install", "-r", (Join-Path $backendDir "requirements.txt")) -WorkingDirectory $backendDir -Retries 2
    Invoke-Python -Python $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pyinstaller") -WorkingDirectory $backendDir -Retries 2
    Invoke-Python -Python $venvPython -Arguments @("-c", "import flask, sqlalchemy, pydantic, requests, yaml; print('backend deps ok')") -WorkingDirectory $backendDir -Retries 1
    Write-OK "Backend listo"
}

function Invoke-NpmInstall {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$NpmPath
    )

    $hasLock = Test-Path (Join-Path $Directory "package-lock.json")
    if ($hasLock -and -not $ForceNpmInstall) {
        try {
            Invoke-CommandWithRetry -FilePath $NpmPath -Arguments @("ci") -WorkingDirectory $Directory -Retries 2
            return
        } catch {
            Write-Warn "npm ci fallo. Verificando cache y usando npm install como fallback."
            Invoke-CommandWithRetry -FilePath $NpmPath -Arguments @("cache", "verify") -WorkingDirectory $Directory -Retries 1 -AllowFailure
        }
    }

    Invoke-CommandWithRetry -FilePath $NpmPath -Arguments @("install") -WorkingDirectory $Directory -Retries 2
}

function Ensure-Frontend {
    param([Parameter(Mandatory = $true)][string]$NpmPath)

    if ($SkipFrontend) {
        Write-Warn "Frontend omitido por parametro SkipFrontend"
        return
    }

    Write-Step "Preparando frontend React/Vite"
    Invoke-NpmInstall -Directory $frontendDir -NpmPath $NpmPath
    if ($ValidateBuild) {
        Invoke-CommandWithRetry -FilePath $NpmPath -Arguments @("run", "build") -WorkingDirectory $frontendDir -Retries 1
    }
    Write-OK "Frontend listo"
}

function Ensure-VsCodeExtension {
    param([Parameter(Mandatory = $true)][string]$NpmPath)

    if ($SkipVsCodeExtension) {
        Write-Warn "Extension VS Code omitida por parametro SkipVsCodeExtension"
        return
    }

    Write-Step "Preparando extension VS Code"
    Invoke-NpmInstall -Directory $vsixDir -NpmPath $NpmPath
    Invoke-CommandWithRetry -FilePath $NpmPath -Arguments @("run", "compile") -WorkingDirectory $vsixDir -Retries 1

    $pkg = Get-Content -LiteralPath (Join-Path $vsixDir "package.json") -Raw | ConvertFrom-Json
    $expectedVsix = Join-Path $vsixDir ("stacky-agents-{0}.vsix" -f $pkg.version)
    if ($ForceVsix -or -not (Test-Path $expectedVsix)) {
        Write-Host "   Generando VSIX stacky-agents-$($pkg.version).vsix" -ForegroundColor DarkGray
        try {
            Invoke-CommandWithRetry -FilePath "npx.cmd" -Arguments @("--yes", "@vscode/vsce", "package", "--allow-missing-repository") -WorkingDirectory $vsixDir -Retries 2
        } catch {
            $latestVsix = Get-ChildItem -Path $vsixDir -Filter "stacky-agents-*.vsix" -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime, Name |
                Select-Object -Last 1
            if ($latestVsix) {
                Write-Warn "No se pudo regenerar VSIX; se usara el existente: $($latestVsix.Name)"
            } else {
                throw
            }
        }
    }

    Write-OK "Extension VS Code lista"
}

try {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " Instalador Dependencias - Stacky Agents" -ForegroundColor Cyan
    Write-Host " App root: $appRoot" -ForegroundColor Gray
    Write-Host " Log     : $logFile" -ForegroundColor Gray
    Write-Host "============================================================" -ForegroundColor Cyan

    $python = Ensure-Python
    $node = Ensure-Node
    Ensure-OptionalTools
    Ensure-Backend -Python $python
    Ensure-Frontend -NpmPath $node.Npm
    Ensure-VsCodeExtension -NpmPath $node.Npm

    Write-Host ""
    Write-Host "Dependencias listas." -ForegroundColor Green
    Write-Host "Ahora podes ejecutar PrepararPublicacion.bat para generar DeployStackyAgents." -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host ""
    Write-Fail $_.Exception.Message
    Write-Host ""
    Write-Host "Revisa el log para el detalle completo:" -ForegroundColor Yellow
    Write-Host "  $logFile" -ForegroundColor Yellow
    Write-Host ""
    exit 1
} finally {
    try {
        Stop-Transcript | Out-Null
    } catch {
    }
}

if (-not $NoPause) {
    Write-Host "Pulsa Enter para cerrar..."
    [void][Console]::ReadLine()
}
