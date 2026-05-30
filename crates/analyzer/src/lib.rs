use std::collections::HashSet;
use std::fs;

#[cfg(test)]
mod tests;

use app2nix_core::{
    AnalysisResult, Analyzer, AppTypeHint, DetectedDesktopEntry, DetectedIcon, ElfInfo,
    ExtractedFile, PackageInfo, ResolvedDependency, Result,
};

#[derive(Default)]
pub struct DefaultAnalyzer;

impl DefaultAnalyzer {
    pub fn new() -> Self {
        Self
    }

    fn analyze_elf(path: &str) -> Option<ElfInfo> {
        let output = std::process::Command::new("patchelf")
            .args(["--print-interpreter", "--print-rpath", "--print-needed"])
            .arg(path)
            .output()
            .ok()?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let lines: Vec<&str> = stdout.lines().collect();

        if lines.is_empty() {
            return None;
        }

        let mut needed_libs = Vec::new();
        let mut rpath = Vec::new();
        let mut interpreter = None;

        let mut i = 0;
        while i < lines.len() {
            let line = lines[i].trim();
            if let Some(val) = line.strip_prefix("interpreter: ") {
                interpreter = Some(val.to_string());
            } else if let Some(val) = line.strip_prefix("rpath: ") {
                rpath = val.split(':').map(|s| s.to_string()).collect();
            } else if let Some(val) = line.strip_prefix("needed: ") {
                needed_libs.push(val.to_string());
            }
            i += 1;
        }

        if needed_libs.is_empty() && rpath.is_empty() && interpreter.is_none() {
            return None;
        }

        let arch_output = std::process::Command::new("file")
            .arg("-b")
            .arg(path)
            .output()
            .ok();
        let arch = arch_output
            .map(|o| String::from_utf8_lossy(&o.stdout).to_string())
            .unwrap_or_default();

        let is_dynamic = !needed_libs.is_empty() || interpreter.is_some();
        let is_exec = is_dynamic;

        Some(ElfInfo {
            path: path.to_string(),
            arch,
            interpreter,
            needed_libs,
            rpath,
            is_dynamic,
            is_executable: is_exec,
        })
    }

    fn find_main_binary(files: &[ExtractedFile], elf_binaries: &[ElfInfo]) -> Option<String> {
        let usr_bin = files.iter().find(|f| {
            f.relative_path.starts_with("usr/bin/") || f.relative_path.starts_with("usr/local/bin/")
        });
        if let Some(f) = usr_bin {
            return Some(f.path.clone());
        }

        let any_bin = files
            .iter()
            .find(|f| f.relative_path.starts_with("bin/") || f.relative_path.starts_with("opt/"));
        if let Some(f) = any_bin {
            return Some(f.path.clone());
        }

        elf_binaries.iter().map(|e| e.path.clone()).next()
    }

    fn detect_desktop_entries(files: &[ExtractedFile]) -> Vec<DetectedDesktopEntry> {
        let mut entries = Vec::new();
        for f in files {
            if !f.relative_path.starts_with("usr/share/applications/")
                && !f.relative_path.ends_with(".desktop")
            {
                continue;
            }
            let content = match fs::read_to_string(&f.path) {
                Ok(c) => c,
                Err(_) => continue,
            };

            let mut name = String::new();
            let mut exec = String::new();
            let mut icon = None;
            let mut categories = Vec::new();

            for line in content.lines() {
                if let Some(v) = line.strip_prefix("Name=") {
                    name = v.to_string();
                } else if let Some(v) = line.strip_prefix("Exec=") {
                    exec = v.to_string();
                } else if let Some(v) = line.strip_prefix("Icon=") {
                    icon = Some(v.to_string());
                } else if let Some(v) = line.strip_prefix("Categories=") {
                    categories = v
                        .split(';')
                        .filter(|s| !s.is_empty())
                        .map(|s| s.to_string())
                        .collect();
                }
            }

            if !name.is_empty() {
                entries.push(DetectedDesktopEntry {
                    path: f.path.clone(),
                    app_name: name,
                    exec_line: exec,
                    icon_path: icon,
                    categories,
                });
            }
        }
        entries
    }

    fn detect_icons(files: &[ExtractedFile]) -> Vec<DetectedIcon> {
        let mut icons = Vec::new();
        for f in files {
            let is_icon = f.relative_path.starts_with("usr/share/icons/")
                || f.relative_path.starts_with("usr/share/pixmaps/")
                || f.relative_path.ends_with(".png")
                || f.relative_path.ends_with(".svg")
                || f.relative_path.ends_with(".xpm");

            if !is_icon {
                continue;
            }

            let size = None;

            let format = if f.relative_path.ends_with(".png") {
                "png"
            } else if f.relative_path.ends_with(".svg") {
                "svg"
            } else if f.relative_path.ends_with(".xpm") {
                "xpm"
            } else {
                "unknown"
            };

            icons.push(DetectedIcon {
                path: f.path.clone(),
                size,
                format: format.to_string(),
            });
        }
        icons
    }

    fn detect_app_type(files: &[ExtractedFile]) -> Vec<AppTypeHint> {
        let mut hints = Vec::new();
        let paths: Vec<&str> = files.iter().map(|f| f.relative_path.as_str()).collect();

        if paths
            .iter()
            .any(|p| p.contains("electron") || p.ends_with("resources/app.asar"))
        {
            hints.push(AppTypeHint::Electron);
        }
        if paths.iter().any(|p| p.ends_with(".jar")) {
            let jars: Vec<String> = files
                .iter()
                .filter(|f| f.relative_path.ends_with(".jar"))
                .map(|f| f.path.clone())
                .collect();
            hints.push(AppTypeHint::Java(app2nix_core::JvmInfo {
                main_class: None,
                jar_files: jars,
                jvm_version: None,
            }));
        }
        if paths
            .iter()
            .any(|p| p.contains("node_modules") || p.ends_with("package.json"))
        {
            hints.push(AppTypeHint::NodeJs(app2nix_core::NodeInfo {
                entry_point: None,
                has_node_modules: true,
            }));
        }

        hints
    }

    fn _resolve_ldd(path: &str) -> Vec<String> {
        let output = match std::process::Command::new("ldd").arg(path).output() {
            Ok(o) => o,
            Err(_) => return Vec::new(),
        };

        let stdout = String::from_utf8_lossy(&output.stdout);
        stdout
            .lines()
            .filter_map(|line| {
                let line = line.trim();
                if line.contains("not found") {
                    let lib = line.split_whitespace().next()?;
                    Some(lib.to_string())
                } else if line.contains("=>") {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() >= 2 {
                        let lib = parts[0].to_string();
                        if parts.get(1) == Some(&"=>")
                            && parts.get(2).map(|p| p.starts_with('/')) == Some(true)
                        {
                            None
                        } else if parts.get(1) == Some(&"=>") {
                            Some(lib)
                        } else {
                            None
                        }
                    } else {
                        None
                    }
                } else {
                    None
                }
            })
            .collect()
    }

    fn generate_resolved_deps(&self, needed: &[String]) -> Result<Vec<ResolvedDependency>> {
        let hardcoded_map = dependency_map();

        let mut resolved = Vec::new();
        for lib in needed {
            let lib_clean = lib
                .trim_start_matches("lib")
                .trim_end_matches(".so*")
                .trim_end_matches(".so");
            let lib_clean = lib_clean.split('.').next().unwrap_or(lib_clean);
            let lib_clean = lib_clean.trim_end_matches(|c: char| c.is_ascii_digit());

            let (nix_attr, nix_name) = if let Some(entry) = hardcoded_map.get(lib_clean) {
                (Some(entry.0.clone()), Some(entry.1.clone()))
            } else {
                let fuzzy = fuzzy_match(lib_clean, &hardcoded_map);
                match fuzzy {
                    Some((attr, name)) => (Some(attr), Some(name)),
                    None => (None, None),
                }
            };

            let confidence = if nix_attr.is_some() { 0.9 } else { 0.2 };
            let system_lib = nix_attr.is_some();
            resolved.push(ResolvedDependency {
                library: lib.clone(),
                nix_attr,
                nix_package: nix_name,
                confidence,
                system_lib,
            });
        }

        Ok(resolved)
    }
}

fn fuzzy_match(
    lib: &str,
    map: &std::collections::HashMap<String, (String, String)>,
) -> Option<(String, String)> {
    for (key, val) in map {
        if key.len() < 2 {
            continue;
        }
        if key.contains(lib) || lib.contains(key) {
            return Some(val.clone());
        }
    }
    None
}

fn dependency_map() -> std::collections::HashMap<String, (String, String)> {
    let mut m = std::collections::HashMap::new();
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
    dep!("nss3", "nss", "nss");
    dep!("nspr4", "nspr", "nspr");
    dep!("z", "zlib", "zlib");
    dep!("bz2", "bzip2", "bzip2");
    dep!("lzma", "xz", "xz");
    dep!("zstd", "zstd", "zstd");
    dep!("pthread", "glibc", "glibc");
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
    dep!("gtk-3", "gtk3", "gtk3");
    dep!("gtk-4", "gtk4", "gtk4");
    dep!("gdk-3", "gtk3", "gtk3");
    dep!("gdk_pixbuf", "gdk-pixbuf", "gdk-pixbuf");
    dep!("pango", "pango", "pango");
    dep!("pangocairo", "pango", "pango");
    dep!("cairo", "cairo", "cairo");
    dep!("cairo-gobject", "cairo", "cairo");
    dep!("freetype", "freetype", "freetype");
    dep!("fontconfig", "fontconfig", "fontconfig");
    dep!("harfbuzz", "harfbuzz", "harfbuzz");
    dep!("pcre", "pcre", "pcre");
    dep!("pcre2", "pcre2", "pcre2");
    dep!("expat", "expat", "expat");
    dep!("dbus-1", "dbus", "dbus");
    dep!("dbus-glib", "dbus-glib", "dbus-glib");
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
    dep!("vorbisfile", "libvorbis", "libvorbis");
    dep!("sndfile", "libsndfile", "libsndfile");
    dep!("flac", "flac", "flac");
    dep!("sndio", "sndio", "sndio");
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
    dep!("Qt5X11Extras", "qt5.qtx11extras", "qt5x11extras");
    dep!("Qt5Svg", "qt5.qtsvg", "qt5svg");
    dep!("Qt6Core", "qt6.qtbase", "qt6");
    dep!("Qt6Gui", "qt6.qtbase", "qt6");
    dep!("Qt6Widgets", "qt6.qtbase", "qt6");
    dep!("Qt6Network", "qt6.qtbase", "qt6");
    dep!("Qt6WebEngine", "qt6.qtwebengine", "qt6webengine");
    dep!("Qt6Qml", "qt6.qtdeclarative", "qt6declarative");
    dep!("Qt6Sql", "qt6.qtbase", "qt6");
    dep!("Qt6OpenGL", "qt6.qtbase", "qt6");
    dep!("Qt6Quick", "qt6.qtdeclarative", "qt6declarative");
    dep!("Qt6Svg", "qt6.qtsvg", "qt6svg");
    dep!("icu", "icu", "icu");
    dep!("icui18n", "icu", "icu");
    dep!("icutu", "icu", "icu");
    dep!("icuuc", "icu", "icu");
    dep!("icudata", "icu", "icu");
    dep!("SDL2", "SDL2", "SDL2");
    dep!("tinfo", "ncurses", "ncurses");
    dep!("pcre2-8", "pcre2", "pcre2");
    dep!("xml2", "libxml2", "libxml2");
    dep!("xslt", "libxslt", "libxslt");
    dep!("wayland", "wayland", "wayland");
    dep!("xkbcommon", "libxkbcommon", "libxkbcommon");
    dep!("pixman", "pixman", "pixman");
    dep!("ffi", "libffi", "libffi");
    dep!("sqlite3", "sqlite", "sqlite");
    dep!("lz4", "lz4", "lz4");
    dep!("ncurses", "ncurses", "ncurses");
    dep!("readline", "readline", "readline");
    dep!("secret-1", "libsecret", "libsecret");
    dep!("soup-2.4", "libsoup_2_4", "libsoup");
    dep!("soup-3.0", "libsoup_3", "libsoup3");
    dep!("webkit2gtk-4.0", "webkitgtk_4_0", "webkitgtk_4_0");
    dep!("webkit2gtk-4.1", "webkitgtk_4_1", "webkitgtk_4_1");
    dep!("webkit2gtk-6.0", "webkitgtk_6_0", "webkitgtk_6_0");
    dep!("javascriptcoregtk-4.0", "webkitgtk_4_0", "webkitgtk_4_0");
    dep!("javascriptcoregtk-4.1", "webkitgtk_4_1", "webkitgtk_4_1");
    dep!("javascriptcoregtk-6.0", "webkitgtk_6_0", "webkitgtk_6_0");
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
    dep!("proc", "procps", "procps");
    dep!("json-c", "json-c", "json-c");
    dep!("yaml", "yaml", "yaml");
    dep!("event", "libevent", "libevent");
    dep!("sigcpp", "libsigcpp", "libsigcpp");
    dep!("boost", "boost", "boost");
    dep!("poppler", "poppler", "poppler");
    dep!("gstreamer", "gstreamer", "gstreamer");
    dep!("gstapp", "gst-plugins-base", "gst-plugins-base");
    dep!("gstvideo", "gst-plugins-base", "gst-plugins-base");
    dep!("gstaudio", "gst-plugins-base", "gst-plugins-base");
    dep!("gstgl", "gst-plugins-base", "gst-plugins-base");
    dep!("avcodec", "ffmpeg", "ffmpeg");
    dep!("avformat", "ffmpeg", "ffmpeg");
    dep!("avutil", "ffmpeg", "ffmpeg");
    dep!("swscale", "ffmpeg", "ffmpeg");
    dep!("swresample", "ffmpeg", "ffmpeg");
    dep!("postproc", "ffmpeg", "ffmpeg");
    dep!("SDL2", "SDL2", "SDL2");
    dep!("SDL2-", "SDL2", "SDL2");
    dep!("vulkan", "vulkan-loader", "vulkan-loader");
    dep!("xcb", "xorg.libxcb", "libxcb");
    dep!("xcb-util", "xcb-util", "xcb-util");
    dep!("Xau", "xorg.libXau", "libXau");
    dep!("Xdmcp", "xorg.libXdmcp", "libXdmcp");
    dep!("SM", "xorg.libSM", "libSM");
    dep!("ICE", "xorg.libICE", "libICE");
    dep!("atk-1", "atk", "atk");
    dep!("atk-bridge", "at-spi2-atk", "at-spi2-atk");
    dep!("dbusmenu-glib", "libdbusmenu-glib", "libdbusmenu-glib");
    dep!("indicator3", "libindicator", "libindicator");
    dep!("appindicator3", "libappindicator", "libappindicator");
    dep!("keyutils", "keyutils", "keyutils");
    dep!("krb5", "libkrb5", "libkrb5");
    dep!("gssapi", "libkrb5", "libkrb5");
    dep!("sasl2", "cyrus_sasl", "cyrus-sasl");
    dep!("ldap", "openldap", "openldap");
    dep!("p11", "p11-kit", "p11-kit");
    dep!("tss2", "tpm2-tss", "tpm2-tss");
    dep!("fido2", "libfido2", "libfido2");
    dep!("brotli", "brotli", "brotli");
    dep!("snappy", "snappy", "snappy");
    dep!("double", "double-conversion", "double-conversion");
    dep!("md4c", "md4c", "md4c");
    dep!("uv", "libuv", "libuv");
    dep!("unwind", "libunwind", "libunwind");
    dep!("dwarf", "libdwarf", "libdwarf");
    dep!("elf", "elfutils", "elfutils");
    dep!("dw", "elfutils", "elfutils");
    dep!("numa", "numactl", "numactl");
    dep!("iptables", "iptables", "iptables");
    dep!("nl-3", "libnl", "libnl");
    dep!("nl-genl", "libnl", "libnl");
    dep!("nl-route", "libnl", "libnl");

    m
}

impl Analyzer for DefaultAnalyzer {
    fn analyze(&self, _package: &PackageInfo, files: &[ExtractedFile]) -> Result<AnalysisResult> {
        let mut elf_binaries = Vec::new();
        let mut all_needed = HashSet::new();

        for f in files {
            if f.is_elf {
                if let Some(info) = Self::analyze_elf(&f.path) {
                    for lib in &info.needed_libs {
                        all_needed.insert(lib.clone());
                    }
                    elf_binaries.push(info);
                }
            }
        }

        let main_binary = Self::find_main_binary(files, &elf_binaries);
        let desktop_entries = Self::detect_desktop_entries(files);
        let icons = Self::detect_icons(files);
        let app_type_hints = Self::detect_app_type(files);

        let needed_vec: Vec<String> = all_needed.into_iter().collect();
        let resolved_deps = self.generate_resolved_deps(&needed_vec)?;

        let unresolved: Vec<String> = resolved_deps
            .iter()
            .filter(|d| d.nix_attr.is_none())
            .map(|d| d.library.clone())
            .collect();

        Ok(AnalysisResult {
            package: PackageInfo {
                name: _package.name.clone(),
                version: _package.version.clone(),
                format: _package.format.clone(),
                description: _package.description.clone(),
                source_path: _package.source_path.clone(),
                size: _package.size,
                hash: _package.hash.clone(),
                architecture: None,
                maintainer: None,
                homepage: None,
            },
            extracted_files: files.to_vec(),
            elf_binaries,
            all_needed_libs: needed_vec.clone(),
            resolved_deps,
            unresolved_libs: unresolved,
            main_binary,
            desktop_entries,
            icons,
            app_type_hints,
        })
    }

    fn resolve_deps(&self, needed: &[String]) -> Result<Vec<ResolvedDependency>> {
        self.generate_resolved_deps(needed)
    }
}
