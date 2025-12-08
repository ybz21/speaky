#!/bin/bash
set -e

APP_NAME="speek-input"
VERSION="1.0.0"
ARCH="amd64"
BUILD_DIR="build"
DIST_DIR="dist"
DEB_DIR="${BUILD_DIR}/${APP_NAME}_${VERSION}_${ARCH}"

echo "=== Building SpeekInput ${VERSION} ==="

# Clean
rm -rf "${BUILD_DIR}" "${DIST_DIR}"
mkdir -p "${BUILD_DIR}" "${DIST_DIR}"

# Install dependencies
pip install pyinstaller

# Build with PyInstaller
echo "=== Running PyInstaller ==="
pyinstaller \
    --name="${APP_NAME}" \
    --onefile \
    --windowed \
    --add-data="resources:resources" \
    --hidden-import="PyQt5.sip" \
    --hidden-import="whisper" \
    --hidden-import="openai" \
    --hidden-import="requests" \
    --hidden-import="yaml" \
    --hidden-import="numpy" \
    --hidden-import="pynput" \
    --hidden-import="pyaudio" \
    src/speek_input/main.py

# Create deb structure
echo "=== Creating deb package ==="
mkdir -p "${DEB_DIR}/DEBIAN"
mkdir -p "${DEB_DIR}/usr/bin"
mkdir -p "${DEB_DIR}/usr/share/applications"
mkdir -p "${DEB_DIR}/usr/share/icons/hicolor/256x256/apps"

# Copy binary
cp "dist/${APP_NAME}" "${DEB_DIR}/usr/bin/"
chmod 755 "${DEB_DIR}/usr/bin/${APP_NAME}"

# Create control file
cat > "${DEB_DIR}/DEBIAN/control" << EOF
Package: ${APP_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: xdotool, libportaudio2
Maintainer: SpeekInput <speek-input@example.com>
Description: Linux voice input method
 A voice input tool for Linux with hotkey activation,
 supporting multiple speech recognition engines including
 local Whisper and online services.
EOF

# Create desktop entry
cat > "${DEB_DIR}/usr/share/applications/${APP_NAME}.desktop" << EOF
[Desktop Entry]
Name=SpeekInput
Comment=Voice Input Method
Exec=${APP_NAME}
Icon=${APP_NAME}
Terminal=false
Type=Application
Categories=Utility;Accessibility;
Keywords=voice;speech;input;
EOF

# Copy icon if exists
if [ -f "resources/icon.png" ]; then
    cp "resources/icon.png" "${DEB_DIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
fi

# Build deb
dpkg-deb --build "${DEB_DIR}" "${DIST_DIR}/${APP_NAME}_${VERSION}_${ARCH}.deb"

echo "=== Build complete ==="
echo "Package: ${DIST_DIR}/${APP_NAME}_${VERSION}_${ARCH}.deb"
