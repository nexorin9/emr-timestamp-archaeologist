# EMR Timestamp Archaeologist - Build Script (Windows)
# Usage: .\build.ps1 [clean] [dev] [exe] [test]

param(
    [ValidateSet("clean", "dev", "exe", "test", "build")]
    [string]$Action = "build"
)

$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
Set-Location $ProjectRoot

function Write-Info($message) {
    Write-Host "[INFO] $message" -ForegroundColor Green
}

function Write-Warn($message) {
    Write-Host "[WARN] $message" -ForegroundColor Yellow
}

function Write-Err($message) {
    Write-Host "[ERROR] $message" -ForegroundColor Red
}

# Clean build artifacts
function Clean-Build {
    Write-Info "Cleaning build artifacts..."

    # Remove common build directories
    $dirsToRemove = @("dist", "build", ".pytest_cache", ".ruff_cache", ".mypy_cache", "coverage", "node_modules\.cache")
    foreach ($dir in $dirsToRemove) {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir
            Write-Info "Removed: $dir"
        }
    }

    # Remove Python cache files
    Get-ChildItem -Recurse -Directory -Filter "__pycache__" 2>$null | ForEach-Object {
        Remove-Item -Recurse -Force $_.FullName
        Write-Info "Removed: $($_.FullName)"
    }

    Get-ChildItem -Recurse -File -Filter "*.pyc" 2>$null | ForEach-Object {
        Remove-Item -Force $_.FullName
    }

    Get-ChildItem -Recurse -File -Filter "*.pyo" 2>$null | ForEach-Object {
        Remove-Item -Force $_.FullName
    }

    Write-Info "Clean complete"
}

# Build TypeScript
function Build-TypeScript {
    Write-Info "Building TypeScript..."

    if (-not (Test-Path "tsconfig.json")) {
        Write-Err "tsconfig.json not found"
        exit 1
    }

    npx tsc
    if ($LASTEXITCODE -ne 0) {
        Write-Err "TypeScript compilation failed"
        exit 1
    }

    Write-Info "TypeScript build complete"
}

# Build Python modules
function Build-Python {
    Write-Info "Building Python modules..."

    $pythonDirs = @("src\py", "src\py\detectors")

    foreach ($dir in $pythonDirs) {
        if (Test-Path $dir) {
            Write-Info "Compiling Python files in $dir\"
            Get-ChildItem -Path $dir -Filter "*.py" -File | ForEach-Object {
                python -m py_compile $_.FullName
                if ($LASTEXITCODE -eq 0) {
                    Write-Info "  Compiled: $($_.Name)"
                } else {
                    Write-Err "  Failed: $($_.Name)"
                }
            }
        }
    }

    Write-Info "Python build complete"
}

# Run tests
function Run-Tests {
    Write-Info "Running tests..."

    # Python tests
    if (Test-Path "src\py\tests") {
        Write-Info "Running Python tests..."
        Set-Location "src\py"
        python -m pytest tests/ -v --tb=short
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Some Python tests failed"
        }
        Set-Location $ProjectRoot
    }

    # Node.js tests (require compiled files)
    if (Test-Path "src\cli") {
        Write-Info "Running Node.js tests..."
        if (Test-Path "dist\cli") {
            node --test dist\cli\tests\ 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "No Node.js tests found or tests failed"
            }
        } else {
            Write-Warn "Skipping Node.js tests - dist\cli not found. Run 'npm run build' first."
        }
    }

    Write-Info "Tests complete"
}

# Create executable with PyInstaller (optional)
function Create-Executable {
    Write-Info "Creating executable with PyInstaller..."

    try {
        $pyinstallerVersion = python -m PyInstaller --version 2>$null
    } catch {
        $pyinstallerVersion = $null
    }

    if (-not $pyinstallerVersion) {
        Write-Warn "PyInstaller not found. Install with: pip install pyinstaller"
        return
    }

    Write-Info "Using PyInstaller: $pyinstallerVersion"

    python -m PyInstaller --name emr-archaeologist `
        --onefile `
        --console `
        --clean `
        --additional-hooks-dir=. `
        src\py\cli.py

    if ($LASTEXITCODE -eq 0) {
        Write-Info "Executable created at dist\emr-archaeologist.exe"
    } else {
        Write-Err "PyInstaller failed"
    }
}

# Development mode
function Start-DevMode {
    Write-Info "Starting development mode..."

    # Check if TypeScript is installed
    if (Get-Command tsc -ErrorAction SilentlyContinue) {
        Write-Info "Starting TypeScript compiler in watch mode..."
        Start-Process -FilePath "npx" -ArgumentList "tsc --watch" -NoNewWindow
    }

    # Simple file watcher using PowerShell
    Write-Info "Watching for file changes in src/, data/, templates/..."
    Write-Info "Press Ctrl+C to stop."

    $watcher = New-Object System.IO.FileSystemWatcher
    $watcher.Path = $ProjectRoot
    $watcher.IncludeSubdirectories = $true
    $watcher.ExcludePatterns = @("node_modules", ".git", "__pycache__", "*.pyc", "*.pyo", "*.log", "*.tmp")

    $lastEvent = Get-Date

    Register-ObjectEvent $watcher "Changed" -Action {
        $item = Get-Item $EventArgs.FullPath
        if ($item.LastWriteTime -gt $script:lastEvent) {
            $script:lastEvent = $item.LastWriteTime
            Write-Host "[CHANGED] $($EventArgs.Name)" -ForegroundColor Cyan
        }
    }

    Register-ObjectEvent $watcher "Created" -Action {
        Write-Host "[CREATED] $($EventArgs.Name)" -ForegroundColor Green
    }

    Register-ObjectEvent $watcher "Deleted" -Action {
        Write-Host "[DELETED] $($EventArgs.Name)" -ForegroundColor Red
    }

    try {
        $watcher.EnableRaisingEvents = $true
        while ($true) { Start-Sleep -Seconds 1 }
    } finally {
        $watcher.EnableRaisingEvents = $false
        Unregister-Event -SubscriptionId *
        $watcher.Dispose()
    }
}

# Main build
function Build-All {
    Write-Info "Starting full build..."
    Clean-Build
    Build-TypeScript
    Build-Python
    Write-Info "Build complete!"
    Write-Info "Output directory: dist\"
    Write-Info "Run '.\build.ps1 -Action dev' for development mode"
}

# Execute action
switch ($Action) {
    "clean" {
        Clean-Build
    }
    "dev" {
        Start-DevMode
    }
    "exe" {
        Create-Executable
    }
    "test" {
        Clean-Build
        Build-TypeScript
        Build-Python
        Run-Tests
    }
    "build" {
        Build-All
    }
}