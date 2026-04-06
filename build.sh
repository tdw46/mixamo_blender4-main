#!/bin/bash

set -u

echo "========================================"
echo "Building Mixamo Rig Extension"
echo "========================================"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTENSION_DIR="$SCRIPT_DIR"
MANIFEST_PATH="$EXTENSION_DIR/blender_manifest.toml"

if [[ ! -f "$MANIFEST_PATH" ]]; then
    echo "Build FAILED - blender_manifest.toml not found"
    echo "Expected: $MANIFEST_PATH"
    exit 1
fi

find_blender() {
    if [[ -n "${BLENDER_PATH:-}" && -x "${BLENDER_PATH}" ]]; then
        printf '%s\n' "${BLENDER_PATH}"
        return 0
    fi

    local app_bundle
    local blender_bin
    local latest_version=""
    local latest_blender_bin=""
    local bundle_name
    local bundle_version

    shopt -s nullglob
    for app_bundle in /Applications/Blender*.app; do
        blender_bin="$app_bundle/Contents/MacOS/Blender"
        if [[ ! -x "$blender_bin" ]]; then
            continue
        fi

        bundle_name="$(basename "$app_bundle")"
        if [[ "$bundle_name" =~ ^Blender.*[^0-9]([0-9]+([.][0-9]+)*)\.app$ ]]; then
            bundle_version="${BASH_REMATCH[1]}"

            if [[ -z "$latest_version" ]]; then
                latest_version="$bundle_version"
                latest_blender_bin="$blender_bin"
                continue
            fi

            if [[ "$(printf '%s\n%s\n' "$latest_version" "$bundle_version" | sort -V | tail -n 1)" == "$bundle_version" ]]; then
                latest_version="$bundle_version"
                latest_blender_bin="$blender_bin"
            fi
        fi
    done
    shopt -u nullglob

    if [[ -n "$latest_blender_bin" ]]; then
        printf '%s\n' "$latest_blender_bin"
        return 0
    fi

    for blender_bin in \
        "/Applications/Blender.app/Contents/MacOS/Blender" \
        "/Applications/Blender Dev.app/Contents/MacOS/Blender"
    do
        if [[ -x "$blender_bin" ]]; then
            printf '%s\n' "$blender_bin"
            return 0
        fi
    done

    if command -v blender >/dev/null 2>&1; then
        command -v blender
        return 0
    fi

    return 1
}

BLENDER_BIN="$(find_blender)"
if [[ -z "$BLENDER_BIN" ]]; then
    echo "Build FAILED - Blender executable not found"
    echo
    echo "Set BLENDER_PATH to your Blender binary, for example:"
    echo '  BLENDER_PATH="/Applications/Blender.app/Contents/MacOS/Blender" ./build.sh'
    exit 1
fi

read_manifest_value() {
    local key="$1"
    local value
    value="$(
        sed -nE "s/^${key}[[:space:]]*=[[:space:]]*\"([^\"]+)\".*/\\1/p" "$MANIFEST_PATH" \
            | head -n 1
    )"
    printf '%s\n' "$value"
}

EXTENSION_ID="$(read_manifest_value "id")"
EXTENSION_VERSION="$(read_manifest_value "version")"

if [[ -z "$EXTENSION_ID" || -z "$EXTENSION_VERSION" ]]; then
    echo "Build FAILED - could not read id/version from blender_manifest.toml"
    exit 1
fi

PACKAGE_NAME="${EXTENSION_ID}-${EXTENSION_VERSION}.zip"
PACKAGE_PATH="$EXTENSION_DIR/$PACKAGE_NAME"

echo "Blender Path: $BLENDER_BIN"
echo "Extension Directory: $EXTENSION_DIR"
echo
echo "Building package: $PACKAGE_NAME"
echo

if [[ -f "$PACKAGE_PATH" ]]; then
    echo "Removing existing package..."
    rm -f "$PACKAGE_PATH"
    echo
fi

echo "Running Blender extension build..."
"$BLENDER_BIN" \
    --factory-startup \
    --command extension build \
    --source-dir "$EXTENSION_DIR" \
    --output-dir "$EXTENSION_DIR"

echo
if [[ -f "$PACKAGE_PATH" ]]; then
    PACKAGE_SIZE="$(stat -f%z "$PACKAGE_PATH" 2>/dev/null || wc -c < "$PACKAGE_PATH")"
    echo "========================================"
    echo "Build completed successfully!"
    echo "========================================"
    echo
    echo "Package: $PACKAGE_NAME"
    echo "Size: $PACKAGE_SIZE bytes"
    echo "Location: $EXTENSION_DIR"
    echo
    exit 0
fi

echo "========================================"
echo "Build FAILED - package not created"
echo "========================================"
echo
echo "Expected package: $PACKAGE_NAME"
echo "Check the output above for errors."
echo
exit 1
