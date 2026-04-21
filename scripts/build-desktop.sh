#!/usr/bin/env bash
# Build the Extract Agent desktop app (macOS).
# Bundles the Python backend via PyInstaller, then runs `tauri build`.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -x "./.venv/bin/pyinstaller" ]]; then
  echo "ERROR: ./.venv/bin/pyinstaller not found." >&2
  echo "       Run: ./.venv/bin/pip install pyinstaller" >&2
  exit 1
fi

echo "==> Building Python sidecar with PyInstaller..."
./.venv/bin/pyinstaller --clean --noconfirm backend.spec

SIDECAR_BIN="./dist/extract-agent-backend/extract-agent-backend"
if [[ ! -x "$SIDECAR_BIN" ]]; then
  echo "ERROR: PyInstaller did not produce the expected binary at $SIDECAR_BIN" >&2
  exit 1
fi

echo "==> Building Tauri app..."
cd frontend
npm run tauri:build

echo ""
echo "Done. Artifacts:"
echo "  frontend/src-tauri/target/release/bundle/macos/Extract Agent.app"
echo "  frontend/src-tauri/target/release/bundle/dmg/Extract Agent_0.1.0_aarch64.dmg"
