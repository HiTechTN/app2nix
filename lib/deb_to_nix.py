#!/usr/bin/env python3
"""
Translation dictionary: Debian library names -> Nixpkgs package names.
"""

DEB_TO_NIX = {
    # Graphics
    "drm": "libdrm",
    "gbm": "mesa",
    "vulkan": "vulkan-loader",
    "gtk-3": "gtk3",
    "gdk-3": "gtk3",
    "pango-1": "pango",
    "cairo": "cairo",
    "freetype": "freetype",
    "fontconfig": "fontconfig",

    # System
    "expat": "expat",
    "dbus-1": "dbus",
    "glib": "glib",
    "gobject-2": "glib",
    "nss": "nss",
    "nspr": "nspr",

    # Compression
    "z": "zlib",
    "zstd": "zstd",
    "bz2": "bzip2",
    "lzma": "lzma",
    "xz": "xz",

    # Crypto
    "gcrypt": "libgcrypt",
    "gpg-error": "libgcrypt",
    "gnutls": "gnutls",
    "nettle": "nettle",
    "ssl": "openssl",
    "crypto": "openssl",

    # Hardware/OpenGL
    "vulkan": "vulkan-loader",
    "OpenGL": "mesa",
    "GL": "mesa",
    "GLU": "glu",
    "glut": "freeglut",
    "glew": "glew",
    "glfw": "glfw",

    # X11/Wayland
    "xcb": "xcb-util",
    "xkbcommon": "xkbcommon",
    "X11": "libX11",
    "Xext": "libXext",
    "Xrandr": "libXrandr",
    "Xi": "libXi",
    "Xinerama": "libXinerama",
    "Xcursor": "libXcursor",
    "Xdamage": "libXdamage",
    "wayland-client": "wayland",

    # Audio
    "asound": "alsa-lib",
    "pulse": "libpulse",
    "jack": "jack2",
    "opus": "opus",
    "vorbis": "libvorbis",
    "sndfile": "libsndfile",

    # Multimedia/FFmpeg
    "avcodec": "ffmpeg",
    "avformat": "ffmpeg",
    "avutil": "ffmpeg",
    "swscale": "ffmpeg",

    # Qt
    "Qt5Core": "qt5.qtbase",
    "Qt5Widgets": "qt5.qtbase",
    "Qt5Gui": "qt5.qtbase",
    "Qt5Xml": "qt5.qtxmlpatterns",
    "Qt5Sql": "qt5.qtbase",
    "Qt5Network": "qt5.qtbase",
    "Qt5OpenGL": "qt5.qtbase",
    "Qt5Quick": "qt5.qtdeclarative",
    "Qt5Qml": "qt5.qtdeclarative",
    "Qt5WebEngine": "qt5.qtwebengine",

    # Image
    "png": "libpng",
    "jpeg": "libjpeg",
    "tiff": "tiff",
    "webp": "libwebp",

    # Database
    "sqlite3": "sqlite",
    "pq": "postgresql",

    # Network
    "curl": "curl",
    "ssh": "libssh",
    "nghttp2": "nghttp2",
    "ldap": "openldap",

    # Python
    "python3.11": "python311",
    "python3.12": "python312",
    "python3": "python3",
    "python3Full": "python3",

    # Boost
    "boost_system": "boost",
    "boost_filesystem": "boost",
    "boost_regex": "boost",
    "boost_python3": "boost",

    # Misc
    "uuid": "uuid",
    "blkid": "util-linux",
    "selinux": "libselinux",
    "sepol": "libsepol",
    "audit": "libcap_audit",
    "cap": "libcap",
    "acl": "acl",
    "attr": "attr",
    "pcre": "pcre",
    "pcre2": "pcre2",
    "json-glib-1": "json-glib",
    "archive": "libarchive",
    "usb-1": "libusb",
    "udev": "systemd",
    "systemd": "systemd",
    "cups": "cups",

    # GTK/GNOME
    "gtk-3": "gtk3",
    "gtk2": "gtk2",
    "gdk-3": "gtk3",
    "gdk-x11-3": "gtk3",
    "gtk-x11-2": "gtk2",
    "gtkgl": "gtkglext",
    "champlain": "libchamplain",
    "clutter": "clutter",
    "gdl": "gdl",
    "keybinder": "keybinder",
    "appindicator": "libappindicator",
    "notify": "libnotify",

    # GStreamer
    "gstreamer-1": "gstreamer",
    "gstbase-1": "gst-plugins-base",
    "gstvideo-1": "gst-plugins-base",
    "gstaudio-1": "gst-plugins-base",
    "gsttag-1": "gst-plugins-base",

    # Fonts
    "harfbuzz": "harfbuzz",
    "icuuc": "icu",
    "graphite2": "graphite2",

    # Input
    "evdev": "libevdev",
    "input": "libinput",

    # Security
    "paludis": "linux-pam",
    "pam": "linux-pam",
    "apparmor": "apparmor",
    "seccomp": "libseccomp",
    "yara": "yara",

    # Config
    "yaml": "yaml",
    "toml": "toml",

    # Docs
    "poppler": "poppler",
    "pixman": "pixman",
}


def translate(lib_name: str) -> str | None:
    """Translate Debian library name to Nixpkgs package name."""
    lib_base = lib_name.split(".so")[0]
    if lib_base.startswith("lib"):
        lib_base = lib_base[3:]

    return DEB_TO_NIX.get(lib_base)


def translate_all(lib_names: list) -> list:
    """Translate list of Debian library names to Nixpkgs package names."""
    result = set()
    for lib in lib_names:
        if lib:
            nix_pkg = translate(lib)
            if nix_pkg:
                result.add(nix_pkg)
    return sorted(result)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for lib in sys.argv[1:]:
            result = translate(lib)
            if result:
                print(f"{lib} -> {result}")
            else:
                print(f"{lib} -> NOT_FOUND")
    else:
        print("Usage: deb_to_nix.py <library-name>")
