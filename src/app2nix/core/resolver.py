import difflib
import sqlite3
from pathlib import Path

from app2nix.models import ResolvedDependency

DEP_MAP = {
    "webkit2gtk-4.1": "webkitgtk_4_1",
    "webkit2gtk-4.0": "webkitgtk_4_0",
    "webkit2gtk-6.0": "webkitgtk_6_0",
    "javascriptcoregtk-4.1": "webkitgtk_4_1",
    "javascriptcoregtk-4.0": "webkitgtk_4_0",
    "javascriptcoregtk-6.0": "webkitgtk_6_0",
    "soup-3.0": "libsoup_3",
    "soup-2.4": "libsoup_2_4",
    "secret-1": "libsecret",
    "drm": "libdrm",
    "gbm": "mesa",
    "vulkan": "vulkan-loader",
    "gtk-3": "gtk3",
    "gdk-3": "gtk3",
    "pango-1": "pango",
    "cairo": "cairo",
    "freetype": "freetype",
    "fontconfig": "fontconfig",
    "expat": "expat",
    "dbus-1": "dbus",
    "glib": "glib",
    "gobject-2": "glib",
    "nss": "nss",
    "nspr": "nspr",
    "z": "zlib",
    "zstd": "zstd",
    "bz2": "bzip2",
    "lzma": "xz",
    "xz": "xz",
    "gcrypt": "libgcrypt",
    "gpg-error": "libgcrypt",
    "gnutls": "gnutls",
    "nettle": "nettle",
    "ssl": "openssl",
    "crypto": "openssl",
    "OpenGL": "mesa",
    "GL": "mesa",
    "GLU": "glu",
    "glut": "freeglut",
    "glew": "glew",
    "glfw": "glfw",
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
    "asound": "alsa-lib",
    "pulse": "libpulse",
    "jack": "jack2",
    "opus": "opus",
    "vorbis": "libvorbis",
    "sndfile": "libsndfile",
    "avcodec": "ffmpeg",
    "avformat": "ffmpeg",
    "avutil": "ffmpeg",
    "swscale": "ffmpeg",
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
    "png": "libpng",
    "jpeg": "libjpeg",
    "tiff": "tiff",
    "webp": "libwebp",
    "sqlite3": "sqlite",
    "pq": "postgresql",
    "curl": "curl",
    "ssh": "libssh",
    "nghttp2": "nghttp2",
    "ldap": "openldap",
    "python3.11": "python311",
    "python3.12": "python312",
    "python3": "python3",
    "python3Full": "python3",
    "boost_system": "boost",
    "boost_filesystem": "boost",
    "boost_regex": "boost",
    "boost_python3": "boost",
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
    "gtk2": "gtk2",
    "gdk-x11-3": "gtk3",
    "gtk-x11-2": "gtk2",
    "gtkgl": "gtkglext",
    "champlain": "libchamplain",
    "clutter": "clutter",
    "gdl": "gdl",
    "keybinder": "keybinder",
    "appindicator": "libappindicator",
    "notify": "libnotify",
    "gstreamer-1": "gstreamer",
    "gstbase-1": "gst-plugins-base",
    "gstvideo-1": "gst-plugins-base",
    "gstaudio-1": "gst-plugins-base",
    "gsttag-1": "gst-plugins-base",
    "harfbuzz": "harfbuzz",
    "icuuc": "icu",
    "graphite2": "graphite2",
    "evdev": "libevdev",
    "input": "libinput",
    "paludis": "linux-pam",
    "pam": "linux-pam",
    "apparmor": "apparmor",
    "seccomp": "libseccomp",
    "yara": "yara",
    "yaml": "yaml",
    "toml": "toml",
    "poppler": "poppler",
    "pixman": "pixman",
}


class DependencyResolver:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self._init_cache()

    def _init_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(self.cache_path) as db:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS resolved (
                        lib_name TEXT PRIMARY KEY,
                        nixpkg TEXT,
                        source TEXT,
                        confidence REAL,
                        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        except Exception:
            pass

    def resolve_sync(self, lib_name: str) -> ResolvedDependency:
        lib_base = lib_name.split(".so")[0]
        if lib_base.startswith("lib"):
            lib_base = lib_base[3:]

        if lib_base in DEP_MAP:
            return ResolvedDependency(
                original=lib_name, nixpkg=DEP_MAP[lib_base],
                confidence=1.0, source="dict",
            )

        close = difflib.get_close_matches(lib_base, DEP_MAP.keys(), n=1, cutoff=0.8)
        if close:
            return ResolvedDependency(
                original=lib_name, nixpkg=DEP_MAP[close[0]],
                confidence=0.8, source="fuzzy",
            )

        return ResolvedDependency(
            original=lib_name, nixpkg=None,
            confidence=0.0, source="unknown",
        )

    async def resolve_async(self, lib_name: str) -> ResolvedDependency:
        sync_result = self.resolve_sync(lib_name)
        if sync_result.nixpkg:
            return sync_result

        import json

        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                body = json.dumps({
                    "query": {
                        "multi_match": {
                            "query": f"lib{lib_name}",
                            "fields": ["package_attr_name^9", "package_pname^6"],
                        }
                    },
                    "size": 1,
                })
                resp = await client.request(
                    "GET",
                    "https://search.nixos.org/backend/latest-42-nixos-24.05/_search",
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    hits = resp.json().get("hits", {}).get("hits", [])
                    if hits:
                        pkg = hits[0]["_source"]["package_attr_name"]
                        return ResolvedDependency(
                            original=lib_name, nixpkg=pkg,
                            confidence=0.6, source="api",
                        )
        except Exception:
            pass

        return sync_result

    def resolve_all(self, libs: list[str]) -> tuple[list[str], list[str]]:
        resolved, unresolved = [], []
        for lib in libs:
            r = self.resolve_sync(lib)
            if r.nixpkg:
                resolved.append(r.nixpkg)
            else:
                unresolved.append(lib)
        return resolved, unresolved
