#!/bin/bash
# EMR Timestamp Archaeologist - Build Script (Unix/Mac)
# Usage: ./build.sh [clean] [dev] [exe]

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Clean build artifacts
clean() {
    log_info "Cleaning build artifacts..."
    rm -rf dist/ build/ .pytest_cache/ .ruff_cache/ .mypy_cache/ coverage/ node_modules/.cache/
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    find . -type f -name "*.pyo" -delete 2>/dev/null || true
    log_info "Clean complete"
}

# Build TypeScript
build_ts() {
    log_info "Building TypeScript..."
    if [ ! -f "tsconfig.json" ]; then
        log_error "tsconfig.json not found"
        exit 1
    fi
    npx tsc
    log_info "TypeScript build complete"
}

# Build Python
build_python() {
    log_info "Building Python modules..."
    PYTHON_SRC_DIRS=(
        "src/py"
        "src/py/detectors"
    )

    for dir in "${PYTHON_SRC_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            log_info "Compiling Python files in $dir/"
            find "$dir" -name "*.py" -type f | while read -r file; do
                python3 -m py_compile "$file" && echo "  Compiled: $file" || log_error "Failed to compile: $file"
            done
        fi
    done
    log_info "Python build complete"
}

# Run tests
run_tests() {
    log_info "Running tests..."
    # Python tests
    if [ -d "src/py/tests" ]; then
        log_info "Running Python tests..."
        cd src/py
        python3 -m pytest tests/ -v --tb=short || log_warn "Some Python tests failed"
        cd "$PROJECT_ROOT"
    fi

    # Node.js tests
    if [ -d "src/cli" ]; then
        log_info "Running Node.js tests..."
        # Note: Node tests require compiled JS files
        if [ -d "dist/cli" ]; then
            node --test dist/cli/tests/ 2>/dev/null || log_warn "No Node.js tests found or tests failed"
        else
            log_warn "Skipping Node.js tests - dist/cli not found. Run 'npm run build' first."
        fi
    fi
    log_info "Tests complete"
}

# Create executable with PyInstaller (optional)
create_executable() {
    log_info "Creating executable with PyInstaller..."
    if ! command -v pyinstaller &> /dev/null; then
        log_warn "PyInstaller not found. Install with: pip install pyinstaller"
        return 1
    fi

    pyinstaller --name emr-archaeologist \
        --onefile \
        --console \
        --clean \
        --additional-hooks-dir=. \
        src/py/cli.py || log_error "PyInstaller failed"

    log_info "Executable created at dist/emr-archaeologist"
}

# Development mode - watch for changes
dev_mode() {
    log_info "Starting development mode (watch for changes)..."
    if command -v inotifywait &> /dev/null; then
        # Linux - use inotifywait
        log_info "Watching for file changes..."
        inotifywait -r -e modify,create,delete --exclude 'node_modules|\.git' src/ data/ templates/
    else
        # macOS - use fswatch
        if command -v fswatch &> /dev/null; then
            log_info "Watching for file changes (fswatch)..."
            fswatch -r --exclude=node_modules --exclude=\.git src/ data/ templates/
        else
            log_warn "No file watcher found. Install inotifywait (Linux) or fswatch (macOS)"
            log_info "Running tsc in watch mode instead..."
            npx tsc --watch
        fi
    fi
}

# Main build
build() {
    log_info "Starting full build..."
    clean
    build_ts
    build_python
    log_info "Build complete!"
    log_info "Output directory: dist/"
    log_info "Run 'npm run dev' for development mode"
}

# Parse arguments
case "${1:-build}" in
    clean)
        clean
        ;;
    dev)
        dev_mode
        ;;
    exe)
        create_executable
        ;;
    test)
        clean
        build_ts
        build_python
        run_tests
        ;;
    *)
        build
        ;;
esac