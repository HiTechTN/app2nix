use crate::DefaultAnalyzer;
use app2nix_core::{
    AppTypeHint, DetectedDesktopEntry, DetectedIcon, ElfInfo, ExtractedFile, PackageFormat,
    PackageInfo,
};

fn make_file(relative_path: &str, is_elf: bool, is_exec: bool) -> ExtractedFile {
    ExtractedFile {
        path: format!("/tmp/test/{}", relative_path),
        relative_path: relative_path.to_string(),
        file_type: if is_elf {
            "application/x-executable".into()
        } else {
            "text/plain".into()
        },
        is_elf,
        is_executable: is_exec,
        size: 1024,
    }
}

#[test]
fn test_find_main_binary_usr_bin() {
    let files = vec![
        make_file("usr/bin/firefox", true, true),
        make_file("usr/share/doc/readme", false, false),
    ];
    let elf_binaries = Vec::new();
    let main = DefaultAnalyzer::find_main_binary(&files, &elf_binaries);
    assert_eq!(main, Some("/tmp/test/usr/bin/firefox".to_string()));
}

#[test]
fn test_find_main_binary_prefers_usr_bin_over_opt() {
    let files = vec![
        make_file("opt/app/bin/foo", true, true),
        make_file("usr/bin/bar", true, true),
    ];
    let elf_binaries = Vec::new();
    let main = DefaultAnalyzer::find_main_binary(&files, &elf_binaries);
    assert_eq!(main, Some("/tmp/test/usr/bin/bar".to_string()));
}

#[test]
fn test_find_main_binary_falls_back_to_elf() {
    let files = vec![
        make_file("usr/share/doc/readme", false, false),
        make_file("opt/app/bin/main", true, true),
    ];
    let elf_binaries = vec![ElfInfo {
        path: "/tmp/test/opt/app/bin/main".into(),
        arch: "x86_64".into(),
        interpreter: Some("/lib64/ld-linux-x86-64.so.2".into()),
        needed_libs: vec!["libc.so.6".into()],
        rpath: vec![],
        is_dynamic: true,
        is_executable: true,
    }];
    let main = DefaultAnalyzer::find_main_binary(&files, &elf_binaries);
    assert_eq!(main, Some("/tmp/test/opt/app/bin/main".to_string()));
}

#[test]
fn test_find_main_binary_no_match() {
    let files = vec![make_file("usr/share/doc/readme", false, false)];
    let main = DefaultAnalyzer::find_main_binary(&files, &[]);
    assert_eq!(main, None);
}

#[test]
fn test_detect_desktop_entries_parses_content() {
    let dir = std::env::temp_dir().join("app2nix_test_desktop");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("usr/share/applications")).unwrap();
    let desktop_path = dir.join("usr/share/applications/app.desktop");
    std::fs::write(
        &desktop_path,
        r#"[Desktop Entry]
Name=TestApp
Exec=/usr/bin/testapp
Icon=testapp
Categories=Utility;Development;
Terminal=false
"#,
    )
    .unwrap();

    let files = vec![make_file(
        "usr/share/applications/app.desktop",
        false,
        false,
    )];
    // We need to override the path to match our temp dir
    let files = vec![ExtractedFile {
        path: desktop_path.to_string_lossy().to_string(),
        relative_path: "usr/share/applications/app.desktop".to_string(),
        file_type: "text/plain".into(),
        is_elf: false,
        is_executable: false,
        size: 100,
    }];

    let entries = DefaultAnalyzer::detect_desktop_entries(&files);
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].app_name, "TestApp");
    assert_eq!(entries[0].exec_line, "/usr/bin/testapp");
    assert_eq!(entries[0].icon_path, Some("testapp".to_string()));
    assert_eq!(
        entries[0].categories,
        vec!["Utility".to_string(), "Development".to_string()]
    );

    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn test_detect_desktop_entries_skips_invalid() {
    let dir = std::env::temp_dir().join("app2nix_test_desktop2");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("bad.desktop");
    std::fs::write(&path, "invalid content without Name=").unwrap();

    let files = vec![ExtractedFile {
        path: path.to_string_lossy().to_string(),
        relative_path: "usr/share/applications/bad.desktop".to_string(),
        file_type: "text/plain".into(),
        is_elf: false,
        is_executable: false,
        size: 50,
    }];
    let entries = DefaultAnalyzer::detect_desktop_entries(&files);
    assert!(entries.is_empty());

    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn test_detect_icons_png() {
    let files = vec![make_file(
        "usr/share/icons/hicolor/48x48/apps/app.png",
        false,
        false,
    )];
    let icons = DefaultAnalyzer::detect_icons(&files);
    assert_eq!(icons.len(), 1);
    assert_eq!(icons[0].format, "png");
}

#[test]
fn test_detect_icons_svg() {
    let files = vec![make_file(
        "usr/share/icons/hicolor/scalable/apps/app.svg",
        false,
        false,
    )];
    let icons = DefaultAnalyzer::detect_icons(&files);
    assert_eq!(icons.len(), 1);
    assert_eq!(icons[0].format, "svg");
}

#[test]
fn test_detect_icons_pixmaps() {
    let files = vec![make_file("usr/share/pixmaps/app.xpm", false, false)];
    let icons = DefaultAnalyzer::detect_icons(&files);
    assert_eq!(icons.len(), 1);
    assert_eq!(icons[0].format, "xpm");
}

#[test]
fn test_detect_icons_png_by_extension() {
    let files = vec![make_file("opt/app/icon.png", false, false)];
    let icons = DefaultAnalyzer::detect_icons(&files);
    assert_eq!(icons.len(), 1);
}

#[test]
fn test_detect_icons_skips_non_icons() {
    let files = vec![make_file("usr/share/doc/readme.txt", false, false)];
    let icons = DefaultAnalyzer::detect_icons(&files);
    assert!(icons.is_empty());
}

#[test]
fn test_detect_app_type_electron() {
    let files = vec![make_file(
        "usr/share/electron/resources/app.asar",
        false,
        false,
    )];
    let hints = DefaultAnalyzer::detect_app_type(&files);
    assert!(hints.iter().any(|h| matches!(h, AppTypeHint::Electron)));
}

#[test]
fn test_detect_app_type_java() {
    let files = vec![
        make_file("opt/app/lib/main.jar", false, false),
        make_file("opt/app/lib/helper.jar", false, false),
    ];
    let hints = DefaultAnalyzer::detect_app_type(&files);
    assert!(hints.iter().any(|h| matches!(h, AppTypeHint::Java(_))));
    if let Some(AppTypeHint::Java(jvm)) = hints.iter().find(|h| matches!(h, AppTypeHint::Java(_))) {
        assert_eq!(jvm.jar_files.len(), 2);
    }
}

#[test]
fn test_detect_app_type_nodejs() {
    let files = vec![
        make_file("opt/app/node_modules/express/index.js", false, false),
        make_file("opt/app/package.json", false, false),
    ];
    let hints = DefaultAnalyzer::detect_app_type(&files);
    assert!(hints.iter().any(|h| matches!(h, AppTypeHint::NodeJs(_))));
}

#[test]
fn test_detect_app_type_multiple() {
    let files = vec![
        make_file("usr/share/electron/resources/app.asar", false, false),
        make_file("opt/app/lib/main.jar", false, false),
        make_file("opt/app/node_modules/express/index.js", false, false),
    ];
    let hints = DefaultAnalyzer::detect_app_type(&files);
    assert_eq!(hints.len(), 3);
}

#[test]
fn test_detect_app_type_none() {
    let files = vec![make_file("usr/share/doc/readme.txt", false, false)];
    let hints = DefaultAnalyzer::detect_app_type(&files);
    assert!(hints.is_empty());
}

#[test]
fn test_dependency_map_has_core_libs() {
    let map = crate::dependency_map();
    assert!(map.contains_key("c"), "Should have libc");
    assert!(map.contains_key("z"), "Should have zlib");
    assert!(map.contains_key("GL"), "Should have libGL");
    assert!(map.contains_key("ssl"), "Should have openssl");
    assert!(map.contains_key("Qt5Core"), "Should have Qt5");
    assert!(map.contains_key("Qt6Core"), "Should have Qt6");
    assert!(map.contains_key("xkbcommon"), "Should have libxkbcommon");
    assert!(map.contains_key("dbus-1"), "Should have dbus");
}

#[test]
fn test_dependency_map_size() {
    let map = crate::dependency_map();
    assert!(map.len() > 80, "Should have at least 80 library mappings");
}

#[test]
fn test_dependency_map_dedup() {
    let map = crate::dependency_map();
    // pthread appears twice in the macro - last value wins
    assert_eq!(
        map.get("pthread"),
        Some(&("glibc".to_string(), "glibc".to_string()))
    );
    // xcb appears as "xorg.libxcb"
    assert_eq!(
        map.get("xcb"),
        Some(&("xorg.libxcb".to_string(), "libxcb".to_string()))
    );
}

#[test]
fn test_fuzzy_match_exact_contains() {
    let mut map = std::collections::HashMap::new();
    map.insert(
        "sndfile".to_string(),
        ("libsndfile".to_string(), "libsndfile".to_string()),
    );
    let result = crate::fuzzy_match("sndfile", &map);
    assert_eq!(
        result,
        Some(("libsndfile".to_string(), "libsndfile".to_string()))
    );
}

#[test]
fn test_fuzzy_match_substring_key_contains_lib() {
    let mut map = std::collections::HashMap::new();
    map.insert(
        "sndfile".to_string(),
        ("libsndfile".to_string(), "libsndfile".to_string()),
    );
    let result = crate::fuzzy_match("file", &map);
    assert_eq!(
        result,
        Some(("libsndfile".to_string(), "libsndfile".to_string()))
    );
}

#[test]
fn test_fuzzy_match_substring_lib_contains_key() {
    let mut map = std::collections::HashMap::new();
    map.insert(
        "sndfile".to_string(),
        ("libsndfile".to_string(), "libsndfile".to_string()),
    );
    let result = crate::fuzzy_match("libsndfile-extra", &map);
    assert_eq!(
        result,
        Some(("libsndfile".to_string(), "libsndfile".to_string()))
    );
}

#[test]
fn test_fuzzy_match_no_match() {
    let map = std::collections::HashMap::new();
    let result = crate::fuzzy_match("completely_unknown_lib_xyz", &map);
    assert_eq!(result, None);
}

#[test]
fn test_fuzzy_match_multiple_map() {
    let mut map = std::collections::HashMap::new();
    map.insert(
        "sndfile".to_string(),
        ("libsndfile".to_string(), "libsndfile".to_string()),
    );
    map.insert(
        "uuid".to_string(),
        ("util-linux".to_string(), "util-linux".to_string()),
    );
    let result = crate::fuzzy_match("uuid", &map);
    assert_eq!(
        result,
        Some(("util-linux".to_string(), "util-linux".to_string()))
    );
}

#[test]
fn test_generate_resolved_deps_known_libs() {
    let analyzer = DefaultAnalyzer::new();
    let needed = vec!["libz.so.1".to_string(), "libc.so.6".to_string()];
    let deps = analyzer.generate_resolved_deps(&needed).unwrap();
    assert_eq!(deps.len(), 2);
    assert!(deps.iter().all(|d| d.system_lib));
    assert!(deps.iter().all(|d| d.confidence > 0.5));
}

#[test]
fn test_generate_resolved_deps_mixed() {
    let analyzer = DefaultAnalyzer::new();
    let needed = vec!["libz.so.1".to_string(), "libQQQQ.so".to_string()];
    let deps = analyzer.generate_resolved_deps(&needed).unwrap();
    assert_eq!(deps.len(), 2);
    assert!(deps[0].system_lib);
    assert!(!deps[1].system_lib);
    assert_eq!(deps[1].confidence, 0.2);
}
