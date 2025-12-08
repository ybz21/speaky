#!/usr/bin/env python3
"""
Cross-platform build script for Speaky.
Builds standalone executables that don't require Python installation.

Usage:
    python build.py              # Build for current platform
    python build.py --all        # Build for all platforms (requires each OS)

System dependencies (cannot be bundled):
    Linux:   sudo apt install libportaudio2 xdotool xclip
    macOS:   brew install portaudio
    Windows: None (all dependencies bundled)
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "speaky"
VERSION = "1.0.0"

# System dependencies that cannot be bundled
SYSTEM_DEPS = {
    "linux": ["libportaudio2", "xdotool", "xclip"],
    "macos": ["portaudio"],
    "windows": [],
}

def get_platform():
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Windows":
        return "windows"
    else:
        return "linux"

def check_system_deps():
    """Check if system dependencies are installed"""
    plat = get_platform()
    deps = SYSTEM_DEPS.get(plat, [])

    if not deps:
        return True

    missing = []
    if plat == "linux":
        for dep in deps:
            result = subprocess.run(
                ["dpkg", "-s", dep],
                capture_output=True
            )
            if result.returncode != 0:
                missing.append(dep)
    elif plat == "macos":
        for dep in deps:
            result = subprocess.run(
                ["brew", "list", dep],
                capture_output=True
            )
            if result.returncode != 0:
                missing.append(dep)

    if missing:
        print(f"Missing system dependencies: {', '.join(missing)}")
        if plat == "linux":
            print(f"Run: sudo apt install {' '.join(missing)}")
        elif plat == "macos":
            print(f"Run: brew install {' '.join(missing)}")
        return False

    return True

def clean():
    """Clean build directories"""
    for d in ["build", "dist", f"{APP_NAME}.spec"]:
        if os.path.isfile(d):
            os.remove(d)
        elif os.path.isdir(d):
            shutil.rmtree(d)
    print("Cleaned build directories")

def install_deps():
    """Install build dependencies"""
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "pyinstaller", "PyQt5", "pynput", "pyaudio",
                    "numpy", "pyyaml", "openai", "requests", "websockets"],
                   check=True)
    print("Installed dependencies")

def get_macos_arch():
    """Get current macOS architecture"""
    machine = platform.machine()
    if machine == "arm64":
        return "arm64"
    else:
        return "x86_64"

def build_executable(target_arch=None):
    """Build executable with PyInstaller

    Args:
        target_arch: For macOS, can be 'x86_64', 'arm64', or 'universal2'
    """
    plat = get_platform()

    # Base PyInstaller args
    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        # Add data files
        "--add-data", f"speaky/locales{os.pathsep}speaky/locales",
    ]

    # Add resources if exists
    if os.path.isdir("resources"):
        args.extend(["--add-data", f"resources{os.pathsep}resources"])

    # Hidden imports
    hidden_imports = [
        "PyQt5.sip",
        "PyQt5.QtWidgets",
        "PyQt5.QtCore",
        "PyQt5.QtGui",
        "pynput.keyboard",
        "pynput.keyboard._xorg",
        "pynput.keyboard._win32",
        "pynput.keyboard._darwin",
        "yaml",
        "numpy",
        "websockets",
    ]
    for imp in hidden_imports:
        args.extend(["--hidden-import", imp])

    # Platform-specific options
    if plat == "macos":
        args.extend([
            "--osx-bundle-identifier", "com.speaky.app",
        ])
        # Set target architecture
        if target_arch:
            args.extend(["--target-arch", target_arch])
        if os.path.exists("resources/icon.icns"):
            args.extend(["--icon", "resources/icon.icns"])
    elif plat == "windows":
        if os.path.exists("resources/icon.ico"):
            args.extend(["--icon", "resources/icon.ico"])
    elif plat == "linux":
        # Linux doesn't need windowed mode for tray apps
        args.remove("--windowed")

    # Entry point
    args.append("speaky/main.py")

    arch_info = f" ({target_arch})" if target_arch else ""
    print(f"Building for {plat}{arch_info}...")
    subprocess.run(args, check=True)
    print(f"Build complete: dist/{APP_NAME}")

def package_linux():
    """Create .deb package for Linux"""
    arch = "amd64" if platform.machine() == "x86_64" else platform.machine()
    deb_dir = f"build/{APP_NAME}_{VERSION}_{arch}"

    os.makedirs(f"{deb_dir}/DEBIAN", exist_ok=True)
    os.makedirs(f"{deb_dir}/usr/bin", exist_ok=True)
    os.makedirs(f"{deb_dir}/usr/share/applications", exist_ok=True)
    os.makedirs(f"{deb_dir}/usr/share/icons/hicolor/256x256/apps", exist_ok=True)

    # Copy binary
    shutil.copy(f"dist/{APP_NAME}", f"{deb_dir}/usr/bin/")
    os.chmod(f"{deb_dir}/usr/bin/{APP_NAME}", 0o755)

    # Control file
    with open(f"{deb_dir}/DEBIAN/control", "w") as f:
        f.write(f"""Package: {APP_NAME}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: {arch}
Depends: xdotool, xclip, libportaudio2
Maintainer: Speaky
Description: Voice input tool with hotkey activation
 A voice input tool with hotkey activation, supporting
 multiple speech recognition engines.
""")

    # Desktop entry
    with open(f"{deb_dir}/usr/share/applications/{APP_NAME}.desktop", "w") as f:
        f.write(f"""[Desktop Entry]
Name=Speaky
Comment=Voice Input Tool
Exec={APP_NAME}
Icon={APP_NAME}
Terminal=false
Type=Application
Categories=Utility;Accessibility;
Keywords=voice;speech;input;
""")

    # Copy icon
    if os.path.exists("resources/icon.png"):
        shutil.copy("resources/icon.png",
                    f"{deb_dir}/usr/share/icons/hicolor/256x256/apps/{APP_NAME}.png")

    # Build deb
    deb_file = f"dist/{APP_NAME}_{VERSION}_{arch}.deb"
    subprocess.run(["dpkg-deb", "--build", deb_dir, deb_file], check=True)
    print(f"Created: {deb_file}")

def package_macos(arch=None):
    """Create .app bundle and .dmg for macOS

    Args:
        arch: Architecture name for the output file (x86_64, arm64, or universal2)
    """
    app_dir = f"dist/{APP_NAME}.app"

    if not arch:
        arch = get_macos_arch()

    # PyInstaller already creates .app bundle with --windowed on macOS
    if os.path.isdir(app_dir):
        # Create DMG with architecture in filename
        dmg_file = f"dist/{APP_NAME}_{VERSION}_macos_{arch}.dmg"
        try:
            subprocess.run([
                "hdiutil", "create", "-volname", "Speaky",
                "-srcfolder", app_dir,
                "-ov", "-format", "UDZO",
                dmg_file
            ], check=True)
            print(f"Created: {dmg_file}")
        except FileNotFoundError:
            print("hdiutil not found, skipping DMG creation")
            print(f"App bundle: {app_dir}")

def package_windows():
    """Package for Windows (executable is already standalone)"""
    exe_file = f"dist/{APP_NAME}.exe"
    if os.path.exists(exe_file):
        # Rename with version
        versioned = f"dist/{APP_NAME}_{VERSION}_windows.exe"
        shutil.copy(exe_file, versioned)
        print(f"Created: {versioned}")

        # Optional: Create installer with NSIS if available
        if shutil.which("makensis"):
            create_nsis_installer()

def create_nsis_installer():
    """Create Windows installer using NSIS"""
    nsi_content = f"""
!include "MUI2.nsh"

Name "Speaky"
OutFile "dist\\{APP_NAME}_{VERSION}_setup.exe"
InstallDir "$PROGRAMFILES\\Speaky"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetOutPath $INSTDIR
    File "dist\\{APP_NAME}.exe"
    CreateShortcut "$DESKTOP\\Speaky.lnk" "$INSTDIR\\{APP_NAME}.exe"
    CreateShortcut "$SMPROGRAMS\\Speaky.lnk" "$INSTDIR\\{APP_NAME}.exe"
    WriteUninstaller "$INSTDIR\\uninstall.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\\{APP_NAME}.exe"
    Delete "$INSTDIR\\uninstall.exe"
    Delete "$DESKTOP\\Speaky.lnk"
    Delete "$SMPROGRAMS\\Speaky.lnk"
    RMDir "$INSTDIR"
SectionEnd
"""
    with open("installer.nsi", "w") as f:
        f.write(nsi_content)

    subprocess.run(["makensis", "installer.nsi"], check=True)
    os.remove("installer.nsi")
    print(f"Created: dist/{APP_NAME}_{VERSION}_setup.exe")

def build_macos_universal():
    """Build universal binary for macOS (both Intel and Apple Silicon)"""
    print("Building universal binary for macOS...")
    print("This requires building separately for each architecture.\n")

    # Build for x86_64
    print("=== Building for Intel (x86_64) ===")
    clean()
    install_deps()
    build_executable(target_arch="x86_64")
    # Save the x86_64 app
    if os.path.isdir(f"dist/{APP_NAME}.app"):
        shutil.move(f"dist/{APP_NAME}.app", f"dist/{APP_NAME}_x86_64.app")
    package_macos(arch="x86_64")

    # Build for arm64
    print("\n=== Building for Apple Silicon (arm64) ===")
    clean()
    build_executable(target_arch="arm64")
    # Save the arm64 app
    if os.path.isdir(f"dist/{APP_NAME}.app"):
        shutil.move(f"dist/{APP_NAME}.app", f"dist/{APP_NAME}_arm64.app")
    package_macos(arch="arm64")

    print("\n=== macOS builds complete ===")
    print("Created:")
    print(f"  - dist/{APP_NAME}_{VERSION}_macos_x86_64.dmg (Intel)")
    print(f"  - dist/{APP_NAME}_{VERSION}_macos_arm64.dmg (Apple Silicon)")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build Speaky for distribution")
    parser.add_argument("--universal", action="store_true",
                        help="Build universal binary for macOS (both Intel and Apple Silicon)")
    parser.add_argument("--arch", choices=["x86_64", "arm64"],
                        help="Target architecture for macOS build")
    args = parser.parse_args()

    os.chdir(Path(__file__).parent)

    plat = get_platform()
    print(f"=== Building Speaky v{VERSION} for {plat} ===\n")

    # Check system dependencies
    if not check_system_deps():
        print("\nPlease install missing dependencies and try again.")
        sys.exit(1)

    if plat == "macos" and args.universal:
        # Build for both architectures
        build_macos_universal()
    else:
        clean()
        install_deps()

        if plat == "macos":
            build_executable(target_arch=args.arch)
        else:
            build_executable()

        if plat == "linux":
            if shutil.which("dpkg-deb"):
                package_linux()
            else:
                print("dpkg-deb not found, skipping .deb creation")
                print(f"Standalone binary: dist/{APP_NAME}")
        elif plat == "macos":
            package_macos(arch=args.arch)
        elif plat == "windows":
            package_windows()

    print("\n=== Build complete ===")
    print(f"Output directory: dist/")

    # Print runtime dependencies info
    deps = SYSTEM_DEPS.get(plat, [])
    if deps:
        print(f"\nNote: Users need to install system dependencies:")
        if plat == "linux":
            print(f"  sudo apt install {' '.join(deps)}")
        elif plat == "macos":
            print(f"  brew install {' '.join(deps)}")

if __name__ == "__main__":
    main()
