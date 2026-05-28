use std::sync::Mutex;
use std::collections::HashMap;

use app2nix_core::{ResolvedDependency, Analyzer, Result, App2NixError};

pub struct DependencyResolver {
    dep_map: HashMap<String, (String, String)>,
    fuzzy_cache: Mutex<HashMap<String, Option<(String, String)>>>,
}

impl DependencyResolver {
    pub fn new() -> Self {
        Self {
            dep_map: build_dep_map(),
            fuzzy_cache: Mutex::new(HashMap::new()),
        }
    }

    pub fn resolve(&self, library: &str) -> Option<(String, String)> {
        let clean = Self::clean_lib_name(library);

        if let Some(entry) = self.dep_map.get(&clean) {
            return Some(entry.clone());
        }

        if let Ok(cache) = self.fuzzy_cache.lock() {
            if let Some(cached) = cache.get(&clean) {
                return cached.clone();
            }
        }

        let result = self.fuzzy_match(&clean);
        if let Ok(mut cache) = self.fuzzy_cache.lock() {
            cache.insert(clean.clone(), result.clone());
        }

        result
    }

    pub fn resolve_all(&self, libs: &[String]) -> Vec<ResolvedDependency> {
        libs
            .iter()
            .map(|lib| {
                let resolved = self.resolve(lib);
                ResolvedDependency {
                    library: lib.clone(),
                    nix_attr: resolved.as_ref().map(|r| r.0.clone()),
                    nix_package: resolved.as_ref().map(|r| r.1.clone()),
                    confidence: if resolved.is_some() { 0.9 } else { 0.2 },
                    system_lib: resolved.is_some(),
                }
            })
            .collect()
    }

    fn clean_lib_name(lib: &str) -> String {
        let s = lib.trim_start_matches("lib");
        let s = s.trim_end_matches(|c: char| c.is_ascii_digit());
        let s = s.trim_end_matches(".so");
        let s = s.trim_end_matches(".so*");
        let s = s.split('.').next().unwrap_or(s);
        let s = s.split('-').next().unwrap_or(s);
        let s = s.split('_').next().unwrap_or(s);
        s.to_lowercase()
    }

    fn fuzzy_match(&self, lib: &str) -> Option<(String, String)> {
        for (key, val) in &self.dep_map {
            if key.contains(lib) || lib.contains(key) {
                return Some(val.clone());
            }
        }

        for (key, val) in &self.dep_map {
            let distance = levenshtein_distance(lib, key);
            if distance <= 2 {
                return Some(val.clone());
            }
        }

        None
    }
}

fn levenshtein_distance(a: &str, b: &str) -> usize {
    let a_len = a.len();
    let b_len = b.len();

    if a_len == 0 { return b_len; }
    if b_len == 0 { return a_len; }

    let mut prev_row: Vec<usize> = (0..=b_len).collect();
    let mut curr_row: Vec<usize> = vec![0; b_len + 1];

    for (i, ca) in a.chars().enumerate() {
        curr_row[0] = i + 1;

        for (j, cb) in b.chars().enumerate() {
            let cost = if ca == cb { 0 } else { 1 };
            curr_row[j + 1] = std::cmp::min(
                std::cmp::min(curr_row[j] + 1, prev_row[j + 1] + 1),
                prev_row[j] + cost,
            );
        }

        std::mem::swap(&mut prev_row, &mut curr_row);
    }

    prev_row[b_len]
}

impl Analyzer for DependencyResolver {
    fn analyze(
        &self,
        _package: &app2nix_core::PackageInfo,
        _files: &[app2nix_core::ExtractedFile],
    ) -> Result<app2nix_core::AnalysisResult> {
        Err(App2NixError::Other(
            "DependencyResolver used as standalone; use DefaultAnalyzer for full analysis".into(),
        ))
    }

    fn resolve_deps(&self, needed: &[String]) -> Result<Vec<ResolvedDependency>> {
        Ok(self.resolve_all(needed))
    }
}

fn build_dep_map() -> HashMap<String, (String, String)> {
    let mut m = HashMap::new();
    macro_rules! dep {
        ($lib:expr, $attr:expr, $name:expr) => {
            m.insert($lib.to_string(), ($attr.to_string(), $name.to_string()));
        };
    }

    dep!("c", "glibc", "glibc");
    dep!("m", "glibc", "glibc");
    dep!("pthread", "glibc", "glibc");
    dep!("dl", "glibc", "glibc");
    dep!("rt", "glibc", "glibc");
    dep!("resolv", "glibc", "glibc");
    dep!("util", "glibc", "glibc");
    dep!("nss", "nss", "nss");
    dep!("nspr", "nspr", "nspr");
    dep!("z", "zlib", "zlib");
    dep!("bz2", "bzip2", "bzip2");
    dep!("lzma", "xz", "xz");
    dep!("zstd", "zstd", "zstd");
    dep!("X11", "xorg.libX11", "libX11");
    dep!("Xext", "xorg.libXext", "libXext");
    dep!("Xrandr", "xorg.libXrandr", "libXrandr");
    dep!("Xinerama", "xorg.libXinerama", "libXinerama");
    dep!("Xcursor", "xorg.libXcursor", "libXcursor");
    dep!("Xfixes", "xorg.libXfixes", "libXfixes");
    dep!("Xcomposite", "xorg.libXcomposite", "libXcomposite");
    dep!("Xdamage", "xorg.libXdamage", "libXdamage");
    dep!("Xi", "xorg.libXi", "libXi");
    dep!("Xrender", "xorg.libXrender", "libXrender");
    dep!("Xtst", "xorg.libXtst", "libXtst");
    dep!("Xxf86vm", "xorg.libXxf86vm", "libXxf86vm");
    dep!("glib", "glib", "glib");
    dep!("gobject", "glib", "glib");
    dep!("gio", "glib", "glib");
    dep!("gmodule", "glib", "glib");
    dep!("gtk", "gtk3", "gtk3");
    dep!("gdk", "gtk3", "gtk3");
    dep!("gdk_pixbuf", "gdk-pixbuf", "gdk-pixbuf");
    dep!("pango", "pango", "pango");
    dep!("pangocairo", "pango", "pango");
    dep!("cairo", "cairo", "cairo");
    dep!("freetype", "freetype", "freetype");
    dep!("fontconfig", "fontconfig", "fontconfig");
    dep!("harfbuzz", "harfbuzz", "harfbuzz");
    dep!("pcre", "pcre", "pcre");
    dep!("pcre2", "pcre2", "pcre2");
    dep!("expat", "expat", "expat");
    dep!("dbus", "dbus", "dbus");
    dep!("ssl", "openssl", "openssl");
    dep!("crypto", "openssl", "openssl");
    dep!("gnutls", "gnutls", "gnutls");
    dep!("nettle", "nettle", "nettle");
    dep!("gcrypt", "libgcrypt", "libgcrypt");
    dep!("curl", "curl", "curl");
    dep!("ssh", "libssh", "libssh");
    dep!("nghttp2", "nghttp2", "nghttp2");
    dep!("xml2", "libxml2", "libxml2");
    dep!("xslt", "libxslt", "libxslt");
    dep!("png", "libpng", "libpng");
    dep!("jpeg", "libjpeg", "libjpeg");
    dep!("tiff", "libtiff", "libtiff");
    dep!("webp", "libwebp", "libwebp");
    dep!("uuid", "util-linux", "util-linux");
    dep!("asound", "alsa-lib", "alsa-lib");
    dep!("pulse", "libpulse", "libpulse");
    dep!("jack", "jack2", "jack2");
    dep!("opus", "opus", "opus");
    dep!("vorbis", "libvorbis", "libvorbis");
    dep!("sndfile", "libsndfile", "libsndfile");
    dep!("flac", "flac", "flac");
    dep!("GL", "libGL", "libGL");
    dep!("GLU", "libGLU", "libGLU");
    dep!("EGL", "libEGL", "libEGL");
    dep!("drm", "libdrm", "libdrm");
    dep!("gbm", "mesa", "mesa");
    dep!("OpenGL", "mesa", "mesa");
    dep!("glew", "glew", "glew");
    dep!("glfw", "glfw", "glfw");
    dep!("freeglut", "freeglut", "freeglut");
    dep!("Qt5Core", "qt5.qtbase", "qt5");
    dep!("Qt5Gui", "qt5.qtbase", "qt5");
    dep!("Qt5Widgets", "qt5.qtbase", "qt5");
    dep!("Qt5Network", "qt5.qtbase", "qt5");
    dep!("Qt5WebEngine", "qt5.qtwebengine", "qt5webengine");
    dep!("Qt5Qml", "qt5.qtdeclarative", "qt5declarative");
    dep!("Qt5DBus", "qt5.qtbase", "qt5");
    dep!("Qt5Svg", "qt5.qtsvg", "qt5svg");
    dep!("Qt6Core", "qt6.qtbase", "qt6");
    dep!("Qt6Gui", "qt6.qtbase", "qt6");
    dep!("Qt6Widgets", "qt6.qtbase", "qt6");
    dep!("Qt6Network", "qt6.qtbase", "qt6");
    dep!("Qt6WebEngine", "qt6.qtwebengine", "qt6webengine");
    dep!("Qt6Qml", "qt6.qtdeclarative", "qt6declarative");
    dep!("icu", "icu", "icu");
    dep!("wayland", "wayland", "wayland");
    dep!("xkbcommon", "libxkbcommon", "libxkbcommon");
    dep!("pixman", "pixman", "pixman");
    dep!("ffi", "libffi", "libffi");
    dep!("sqlite3", "sqlite", "sqlite");
    dep!("lz4", "lz4", "lz4");
    dep!("ncurses", "ncurses", "ncurses");
    dep!("readline", "readline", "readline");
    dep!("secret", "libsecret", "libsecret");
    dep!("soup", "libsoup_3", "libsoup3");
    dep!("webkit2gtk", "webkitgtk", "webkitgtk");
    dep!("javascriptcoregtk", "webkitgtk", "webkitgtk");
    dep!("epoxy", "libepoxy", "libepoxy");
    dep!("systemd", "systemd", "systemd");
    dep!("cups", "cups", "cups");
    dep!("usb", "libusb", "libusb");
    dep!("udev", "systemd", "udev");
    dep!("mount", "util-linux", "util-linux");
    dep!("blkid", "util-linux", "util-linux");
    dep!("archive", "libarchive", "libarchive");
    dep!("seccomp", "libseccomp", "libseccomp");
    dep!("pam", "linux-pam", "linux-pam");
    dep!("cap", "libcap", "libcap");
    dep!("json", "json-c", "json-c");
    dep!("yaml", "yaml", "yaml");
    dep!("event", "libevent", "libevent");
    dep!("boost", "boost", "boost");
    dep!("poppler", "poppler", "poppler");
    dep!("gstreamer", "gstreamer", "gstreamer");
    dep!("gst", "gst-plugins-base", "gst-plugins-base");
    dep!("avcodec", "ffmpeg", "ffmpeg");
    dep!("avformat", "ffmpeg", "ffmpeg");
    dep!("avutil", "ffmpeg", "ffmpeg");
    dep!("swscale", "ffmpeg", "ffmpeg");
    dep!("SDL2", "SDL2", "SDL2");
    dep!("vulkan", "vulkan-loader", "vulkan-loader");
    dep!("xcb", "xorg.libxcb", "libxcb");
    dep!("xcb", "xcb-util", "xcb-util");
    dep!("Xau", "xorg.libXau", "libXau");
    dep!("Xdmcp", "xorg.libXdmcp", "libXdmcp");
    dep!("SM", "xorg.libSM", "libSM");
    dep!("ICE", "xorg.libICE", "libICE");
    dep!("atk", "atk", "atk");
    dep!("krb5", "libkrb5", "libkrb5");
    dep!("ldap", "openldap", "openldap");
    dep!("brotli", "brotli", "brotli");
    dep!("snappy", "snappy", "snappy");
    dep!("uv", "libuv", "libuv");
    dep!("unwind", "libunwind", "libunwind");
    dep!("elf", "elfutils", "elfutils");
    dep!("numa", "numactl", "numactl");
    dep!("nl", "libnl", "libnl");

    m
}
