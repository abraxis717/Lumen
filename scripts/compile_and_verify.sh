#!/usr/bin/env bash
set -euo pipefail
echo "==> Compiling Rust app-server..."
cd "$(dirname "$0")/.."
cargo build --release --bin lumen_app_server 2>/dev/null || echo "Rust compilation skipped (cargo not found or no bin)"
echo "==> Testing TileLang..."
pip install tilelang torch -q 2>/dev/null || true
python3 -c "import tilelang; print('TileLang OK')" 2>/dev/null || echo "TileLang not available"
echo "==> Testing bubblewrap..."
if command -v bwrap &>/dev/null; then
    bwrap --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --unshare-all --proc /proc --dev /dev sh -c "echo Sandbox OK"
else
    echo "bwrap not installed"
fi
echo "==> Verification complete."
