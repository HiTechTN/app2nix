use crate::{sanitize_name, sanitize_version};
use app2nix_core::{
    DetectedDesktopEntry, DetectedIcon, ElfInfo, ExtractedFile, GenerateOptions, PackageFormat,
};
use std::collections::HashMap;

#[test]
fn test_sanitize_name_lowercase() {
    assert_eq!(sanitize_name("Firefox"), "firefox");
}

#[test]
fn test_sanitize_name_replaces_spaces() {
    assert_eq!(sanitize_name("VS Code"), "vs-code");
}

#[test]
fn test_sanitize_name_replaces_special_chars() {
    assert_eq!(sanitize_name("App@2.0#"), "app-2-0");
}

#[test]
fn test_sanitize_name_trims_dashes() {
    assert_eq!(sanitize_name("-app-"), "app");
}

#[test]
fn test_sanitize_name_allows_hyphens_and_underscores() {
    assert_eq!(sanitize_name("my_app-name"), "my_app-name");
}

#[test]
fn test_sanitize_name_empty() {
    assert_eq!(sanitize_name(""), "");
}

#[test]
fn test_sanitize_name_only_special_chars() {
    assert_eq!(sanitize_name("@#$%"), "");
}

#[test]
fn test_sanitize_version_keeps_alpha_num_dot_dash_underscore() {
    assert_eq!(sanitize_version("1.2.3-beta_1"), "1.2.3-beta_1");
}

#[test]
fn test_sanitize_version_strips_other_chars() {
    assert_eq!(sanitize_version("1.0@alpha#2"), "1.0alpha2");
}

#[test]
fn test_sanitize_version_empty() {
    assert_eq!(sanitize_version(""), "");
}

#[test]
fn test_sanitize_version_only_special() {
    assert_eq!(sanitize_version("!@#$%"), "");
}

#[test]
fn test_format_nix_list_empty() {
    let result = crate::DefaultNixGenerator::new();
    assert_eq!(result.format_nix_list(&[]), "");
}

#[test]
fn test_format_nix_list_dedup() {
    let result = crate::DefaultNixGenerator::new();
    let items = vec!["zlib".into(), "glibc".into(), "zlib".into()];
    let formatted = result.format_nix_list(&items);
    assert_eq!(formatted.matches("zlib").count(), 1);
    assert_eq!(formatted.matches("glibc").count(), 1);
}

#[test]
fn test_sanitize_name_static_functions() {
    // Test standalone functions
    assert_eq!(sanitize_name(" MyApp_123 "), "myapp_123");
    assert_eq!(sanitize_version("1.0.0"), "1.0.0");
}

fn make_opts() -> GenerateOptions {
    GenerateOptions {
        app_name: "test-app".into(),
        version: "1.0.0".into(),
        description: "Test application".into(),
        format: PackageFormat::Deb,
        main_binary: Some("usr/bin/testapp".into()),
        build_inputs: vec!["zlib".into(), "glibc".into()],
        native_build_inputs: vec!["autoPatchelfHook".into()],
        elf_binaries: vec![ElfInfo {
            path: "/build/usr/bin/testapp".into(),
            arch: "x86_64".into(),
            interpreter: Some("/lib64/ld-linux-x86-64.so.2".into()),
            needed_libs: vec!["libc.so.6".into()],
            rpath: vec![],
            is_dynamic: true,
            is_executable: true,
        }],
        all_files: vec![ExtractedFile {
            path: "/build/usr/bin/testapp".into(),
            relative_path: "usr/bin/testapp".into(),
            file_type: "application/x-executable".into(),
            is_elf: true,
            is_executable: true,
            size: 1024,
        }],
        desktop_entries: vec![DetectedDesktopEntry {
            path: "/build/usr/share/applications/testapp.desktop".into(),
            app_name: "TestApp".into(),
            exec_line: "testapp".into(),
            icon_path: Some("testapp".into()),
            categories: vec!["Utility".into()],
        }],
        icons: vec![DetectedIcon {
            path: "/build/usr/share/icons/testapp.png".into(),
            size: Some(48),
            format: "png".into(),
        }],
        app_type_hints: vec![],
        env_vars: HashMap::new(),
        use_fhs: false,
        extra_phases: vec![],
    }
}

#[test]
fn test_generate_install_phase_deb() {
    let gen = crate::DefaultNixGenerator::new();
    let opts = make_opts();
    let phase = gen.generate_install_phase(&opts);
    assert!(
        phase.contains("dpkg-deb"),
        "Deb install phase should use dpkg-deb"
    );
}

#[test]
fn test_generate_install_phase_rpm() {
    let gen = crate::DefaultNixGenerator::new();
    let mut opts = make_opts();
    opts.format = PackageFormat::Rpm;
    let phase = gen.generate_install_phase(&opts);
    assert!(
        phase.contains("rpm2cpio"),
        "RPM install phase should use rpm2cpio"
    );
}

#[test]
fn test_generate_install_phase_appimage() {
    let gen = crate::DefaultNixGenerator::new();
    let mut opts = make_opts();
    opts.format = PackageFormat::AppImage;
    let phase = gen.generate_install_phase(&opts);
    assert!(
        phase.contains("--appimage-extract"),
        "AppImage phase should use --appimage-extract"
    );
}

#[test]
fn test_generate_install_phase_targz() {
    let gen = crate::DefaultNixGenerator::new();
    let mut opts = make_opts();
    opts.format = PackageFormat::TarGz;
    let phase = gen.generate_install_phase(&opts);
    assert!(phase.contains("cp"), "TarGz install phase should use cp");
}

#[test]
fn test_generate_install_phase_elf() {
    let gen = crate::DefaultNixGenerator::new();
    let mut opts = make_opts();
    opts.format = PackageFormat::ElfBinary;
    let phase = gen.generate_install_phase(&opts);
    assert!(phase.contains("cp"), "ELF install phase should use cp");
}

#[test]
fn test_generate_desktop_phase_with_entries() {
    let gen = crate::DefaultNixGenerator::new();
    let opts = make_opts();
    let phase = gen.generate_desktop_phase(&opts);
    assert!(
        phase.contains("share/applications"),
        "Desktop phase should install .desktop files"
    );
    assert!(
        phase.contains("share/icons"),
        "Desktop phase should install icons"
    );
}

#[test]
fn test_generate_desktop_phase_empty() {
    let gen = crate::DefaultNixGenerator::new();
    let mut opts = make_opts();
    opts.desktop_entries = vec![];
    opts.icons = vec![];
    let phase = gen.generate_desktop_phase(&opts);
    assert!(phase.is_empty(), "No desktop entries = no phase");
}

#[test]
fn test_generate_env_vars_empty() {
    let gen = crate::DefaultNixGenerator::new();
    let opts = make_opts();
    let vars = gen.generate_env_vars(&opts);
    assert!(vars.is_empty());
}

#[test]
fn test_generate_env_vars_with_values() {
    let gen = crate::DefaultNixGenerator::new();
    let mut opts = make_opts();
    let mut env = HashMap::new();
    env.insert("FOO".to_string(), "bar".to_string());
    opts.env_vars = env;
    let vars = gen.generate_env_vars(&opts);
    assert!(vars.contains("FOO=$'bar'"));
}

#[test]
fn test_generate_env_vars_escapes_nix_and_shell_injection() {
    let gen = crate::DefaultNixGenerator::new();
    let mut opts = make_opts();
    let mut env = HashMap::new();
    env.insert(
        "BAD-KEY".to_string(),
        "x''\n    export INJECTED=true\n${pkgs.bash}".to_string(),
    );
    opts.env_vars = env;
    let vars = gen.generate_env_vars(&opts);
    assert!(vars.contains("export BAD_KEY="));
    assert!(vars.contains("\\${pkgs.bash}"));
    assert!(!vars.contains("export INJECTED=true\n"));
    assert!(!vars.contains("export BAD-KEY"));
}

#[test]
fn test_generate_wrapper_script_contains_bin_name() {
    let gen = crate::DefaultNixGenerator::new();
    let opts = make_opts();
    let script = gen.generate_wrapper_script(&opts);
    assert!(
        script.contains("test-app"),
        "Wrapper should contain app name"
    );
    assert!(
        script.contains("#!/usr/bin/env bash"),
        "Wrapper should be bash script"
    );
}

#[test]
fn test_generate_derivation_creates_valid_nix() {
    let gen = crate::DefaultNixGenerator::new();
    let opts = make_opts();
    let derivation = gen.generate_derivation(&opts).unwrap();
    assert!(
        derivation.contains("stdenv.mkDerivation"),
        "Should be a mkDerivation"
    );
    assert!(
        derivation.contains("pname = \"test-app\""),
        "Should have app name"
    );
    assert!(
        derivation.contains("version = \"1.0.0\""),
        "Should have version"
    );
    assert!(
        derivation.contains("autoPatchelfHook"),
        "Should have autoPatchelfHook"
    );
}

#[test]
fn test_generate_flake_contains_app_name() {
    let gen = crate::DefaultNixGenerator::new();
    let opts = make_opts();
    let flake = gen.generate_flake(&opts).unwrap();
    assert!(flake.contains("test-app"), "Should contain app name");
    assert!(
        flake.contains("nixos-unstable"),
        "Should use nixos-unstable"
    );
    assert!(flake.contains("flake-utils"), "Should use flake-utils");
}
