#!/usr/bin/env bash
# OrveX Panel - build the Vue/Vite frontends of the bundled addons.
#
# Every bundled addon that ships a `Frontend/App` (Vite) project is built into
# `Frontend/Components/<addon>/dist/`, which the panel serves through the
# `backend/public/components/<addon>` symlinks. The built output is committed,
# so you only need to run this after changing an addon's frontend source.
#
# Usage:
#   scripts/build-addon-frontends.sh              # build every addon
#   scripts/build-addon-frontends.sh billingcore  # build specific addons
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADDONS_DIR="$ROOT/backend/storage/addons"

if command -v pnpm >/dev/null 2>&1; then
    PNPM=(pnpm)
elif command -v corepack >/dev/null 2>&1; then
    PNPM=(corepack pnpm)
else
    echo "pnpm is required (install Node.js 20+ and run: corepack enable pnpm)" >&2
    exit 1
fi

if [ "$#" -gt 0 ]; then
    targets=("$@")
else
    targets=()
    for app in "$ADDONS_DIR"/*/Frontend/App; do
        [ -f "$app/package.json" ] || continue
        targets+=("$(basename "$(dirname "$(dirname "$app")")")")
    done
fi

failed=()
for addon in "${targets[@]}"; do
    app="$ADDONS_DIR/$addon/Frontend/App"
    if [ ! -f "$app/package.json" ]; then
        echo "!! $addon has no Frontend/App/package.json, skipping" >&2
        continue
    fi
    echo "==> Building $addon"
    if (
        cd "$app"
        "${PNPM[@]}" install --frozen-lockfile --config.confirmModulesPurge=false
        "${PNPM[@]}" run build
    ); then
        echo "    $addon built"
    else
        echo "!! $addon failed to build" >&2
        failed+=("$addon")
    fi
done

if [ "${#failed[@]}" -gt 0 ]; then
    echo "Failed addons: ${failed[*]}" >&2
    exit 1
fi
echo "All addon frontends built."
