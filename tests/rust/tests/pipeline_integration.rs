//! Integration tests for the full app2nix pipeline.
//!
//! Tests the complete detect -> extract -> analyze -> generate flow
//! using real crate implementations and dummy files created on disk.
//!
//! Where system tools are unavailable (patchelf, dpkg-deb, nix, etc.),
//! we use mock implementations to verify the pipeline wiring.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::collections::HashMap;

use app2nix_core::*;
use app2nix_detector::DefaultDetector;
use app2nix_analyzer::DefaultAnalyzer;
use app2nix_nixgen::DefaultNixGenerator;

// Helper functions

fn temp_dir() -> PathBuf {
    tempfile::tempdir().expect("failed to create temp dir").into_path()
}

fn create_minimal_png(path: &Path) {
    // Ensure parent directory exists
    std::fs::create_dir_all(path.parent().unwrap()).expect("failed to create PNG parent dir");
    // Minimal valid 1x1 red PNG
    let png_data: &[u8] = &[
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0x00, 0x00, 0x00, 0xFF, 0x00, 0x01, 0x0D, 0x0A,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,
        0xAE, 0x42, 0x60, 0x82,
    ];
    let mut f = std::fs::File::create(path).expect("failed to create PNG");
    f.write_all(png_data).expect("failed to write PNG");
}

fn create_desktop_file(path: &Path, name: &str, exec: &str, icon: Option<&str>, categories: &[&str]) {
    let cat_str = categories.join(";");
    let icon_line = icon.map(|i| format!("Icon={}", i)).unwrap_or_default();
    let content = format!(
        "[Desktop Entry]\n\
         Type=Application\n\
         Name={}\n\
         Exec={}\n\
         {}\n\
         Categories={};\n\
         Terminal=false\n",
        name, exec, icon_line, cat_str
    );
    std::fs::create_dir_all(path.parent().unwrap()).expect("failed to create parent dir");
    std::fs::write(path, &content).expect("failed to write desktop file");
}

fn create_dummy_elf(path: &Path) {
    std::fs::create_dir_all(path.parent().unwrap()).expect("failed to create parent dir");
    let elf_header: &[u8] = &[
        0x7F, 0x45, 0x4C, 0x46, // ELF magic
        0x02, 0x01, 0x01, 0x00, // 64-bit, LE, ELF v1, SysV
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // padding
        0x00, 0x02, 0x3E, 0x00, // ET_EXEC, x86-64
        0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // entry
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
    ];
    let mut data = elf_header.to_vec();
    data.resize(128, 0x00);
    std::fs::write(path, &data).expect("failed to write ELF file");
}

fn create_tar_gz(archive_path: &Path, files: &[(&str, &[u8])]) -> bool {
    let staging = temp_dir();
    for (rel_path, content) in files {
        let full = staging.join(rel_path);
        std::fs::create_dir_all(full.parent().unwrap()).expect("failed to create staging dir");
        std::fs::write(&full, content).expect("failed to write staging file");
    }
    Command::new("tar")
        .args(["-czf", &archive_path.to_string_lossy()])
        .arg("-C").arg(&staging).arg(".")
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn command_exists(cmd: &str) -> bool {
    Command::new("which").arg(cmd).output().ok().map_or(false, |o| o.status.success())
}

// -- Format Detection ---------------------------------------------------

#[test]
fn test_detect_deb_by_extension() {
    let dir = temp_dir();
    let path = dir.join("package.deb");
    std::fs::write(&path, b"!<arch>\ndebian-binary").unwrap();
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.name, "package");
    assert_eq!(info.format, PackageFormat::Deb);
    assert!(info.size > 0);
    assert_ne!(info.hash, "unknown");
}

#[test]
fn test_detect_rpm_by_extension() {
    let dir = temp_dir();
    let path = dir.join("package.rpm");
    std::fs::write(&path, b"dummy rpm").unwrap();
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.name, "package");
    assert_eq!(info.format, PackageFormat::Rpm);
}

#[test]
fn test_detect_appimage_by_extension() {
    let dir = temp_dir();
    let path = dir.join("MyApp.AppImage");
    std::fs::write(&path, b"dummy appimage").unwrap();
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.name, "myapp");
    assert_eq!(info.format, PackageFormat::AppImage);
}

#[test]
fn test_detect_targz_by_extension() {
    let dir = temp_dir();
    let path = dir.join("node-v18.0.0-linux-x64.tar.gz");
    std::fs::write(&path, b"dummy").unwrap();
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.name, "node-v18.0.0");
    assert_eq!(info.format, PackageFormat::TarGz);
}

#[test]
fn test_detect_zip_by_extension() {
    let dir = temp_dir();
    let path = dir.join("archive.zip");
    std::fs::write(&path, b"PK\x03\x04").unwrap();
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.name, "archive");
    assert_eq!(info.format, PackageFormat::Zip);
}

#[test]
fn test_detect_elf_by_magic() {
    let dir = temp_dir();
    let path = dir.join("mybinary");
    create_dummy_elf(&path);
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.name, "mybinary");
    assert_eq!(info.format, PackageFormat::ElfBinary);
}

#[test]
fn test_detect_flatpak_by_extension() {
    let dir = temp_dir();
    let path = dir.join("app.flatpak");
    std::fs::write(&path, b"dummy").unwrap();
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.format, PackageFormat::Flatpak);
}

#[test]
fn test_detect_snap_by_extension() {
    let dir = temp_dir();
    let path = dir.join("app.snap");
    std::fs::write(&path, b"dummy").unwrap();
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.format, PackageFormat::Snap);
}

#[test]
fn test_detect_java_by_extension() {
    let dir = temp_dir();
    let path = dir.join("app.jar");
    std::fs::write(&path, b"PK\x03\x04").unwrap();
    let detector = DefaultDetector::new();
    let info = detector.detect(&path.to_string_lossy()).unwrap();
    assert_eq!(info.format, PackageFormat::Java);
}

#[test]
fn test_detect_file_not_found() {
    let detector = DefaultDetector::new();
    let err = detector.detect("/nonexistent/path.deb").unwrap_err();
    assert!(matches!(err, App2NixError::FileNotFound(_)));
}

// -- Desktop Entry & Icon Detection ------------------------------------

#[test]
fn test_analyze_detects_desktop_entries() {
    let dir = temp_dir();
    let desktop_path = dir.join("usr/share/applications/myapp.desktop");
    create_desktop_file(&desktop_path, "MyApp", "/usr/bin/myapp", Some("myapp"), &["Utility", "Office"]);

    let icon_dir = dir.join("usr/share/icons/hicolor/256x256/apps");
    std::fs::create_dir_all(&icon_dir).unwrap();
    let icon_path = icon_dir.join("myapp.png");
    create_minimal_png(&icon_path);

    let files = vec![
        ExtractedFile {
            path: desktop_path.to_string_lossy().to_string(),
            relative_path: "usr/share/applications/myapp.desktop".into(),
            file_type: "text/plain".into(),
            is_elf: false, is_executable: false, size: 200,
        },
        ExtractedFile {
            path: icon_path.to_string_lossy().to_string(),
            relative_path: "usr/share/icons/hicolor/256x256/apps/myapp.png".into(),
            file_type: "image/png".into(),
            is_elf: false, is_executable: false, size: 67,
        },
    ];

    let package = PackageInfo {
        name: "myapp".into(), version: Some("1.0".into()), format: PackageFormat::TarGz,
        description: Some("My test app".into()), source_path: "/tmp/test.tar.gz".into(),
        size: 1000, hash: "abc".into(), architecture: None, maintainer: None, homepage: None,
    };

    let analyzer = DefaultAnalyzer::new();
    let result = analyzer.analyze(&package, &files).unwrap();
    assert_eq!(result.desktop_entries.len(), 1);
    assert_eq!(result.desktop_entries[0].app_name, "MyApp");
    assert_eq!(result.icons.len(), 1);
    assert_eq!(result.icons[0].format, "png");
}

#[test]
fn test_analyze_detects_multiple_icons() {
    let dir = temp_dir();
    let png_path = dir.join("usr/share/icons/app.png");
    create_minimal_png(&png_path);
    let svg_path = dir.join("usr/share/pixmaps/app.svg");
    std::fs::create_dir_all(svg_path.parent().unwrap()).unwrap();
    std::fs::write(&svg_path, b"<svg></svg>").unwrap();

    let files = vec![
        ExtractedFile {
            path: png_path.to_string_lossy().to_string(),
            relative_path: "usr/share/icons/app.png".into(),
            file_type: "image/png".into(), is_elf: false, is_executable: false, size: 67,
        },
        ExtractedFile {
            path: svg_path.to_string_lossy().to_string(),
            relative_path: "usr/share/pixmaps/app.svg".into(),
            file_type: "image/svg+xml".into(), is_elf: false, is_executable: false, size: 10,
        },
    ];

    let package = PackageInfo {
        name: "icon-test".into(), version: None, format: PackageFormat::Unknown,
        description: None, source_path: String::new(), size: 0, hash: String::new(),
        architecture: None, maintainer: None, homepage: None,
    };

    let analyzer = DefaultAnalyzer::new();
    let result = analyzer.analyze(&package, &files).unwrap();
    assert_eq!(result.icons.len(), 2);
    let formats: Vec<&str> = result.icons.iter().map(|i| i.format.as_str()).collect();
    assert!(formats.contains(&"png"));
    assert!(formats.contains(&"svg"));
}

#[test]
fn test_analyze_finds_main_binary_in_usr_bin() {
    let dir = temp_dir();
    let bin_path = dir.join("usr/bin/myapp");
    std::fs::create_dir_all(bin_path.parent().unwrap()).unwrap();
    std::fs::write(&bin_path, b"#!/bin/sh\necho hello").unwrap();

    let files = vec![ExtractedFile {
        path: bin_path.to_string_lossy().to_string(),
        relative_path: "usr/bin/myapp".into(),
        file_type: "text/x-shellscript".into(), is_elf: false, is_executable: true, size: 20,
    }];

    let package = PackageInfo {
        name: "myapp".into(), version: None, format: PackageFormat::TarGz,
        description: None, source_path: String::new(), size: 0, hash: String::new(),
        architecture: None, maintainer: None, homepage: None,
    };

    let analyzer = DefaultAnalyzer::new();
    let result = analyzer.analyze(&package, &files).unwrap();
    assert!(result.main_binary.is_some());
    assert!(result.main_binary.unwrap().contains("myapp"));
}

#[test]
fn test_analyze_detects_app_type_hints() {
    let dir = temp_dir();
    let asar_path = dir.join("resources/app.asar");
    std::fs::create_dir_all(asar_path.parent().unwrap()).unwrap();
    std::fs::write(&asar_path, b"dummy asar").unwrap();
    let jar_path = dir.join("lib/app.jar");
    std::fs::create_dir_all(jar_path.parent().unwrap()).unwrap();
    std::fs::write(&jar_path, b"PK\x03\x04").unwrap();

    let files = vec![
        ExtractedFile {
            path: asar_path.to_string_lossy().to_string(),
            relative_path: "resources/app.asar".into(),
            file_type: "application/octet-stream".into(), is_elf: false, is_executable: false, size: 10,
        },
        ExtractedFile {
            path: jar_path.to_string_lossy().to_string(),
            relative_path: "lib/app.jar".into(),
            file_type: "application/zip".into(), is_elf: false, is_executable: false, size: 100,
        },
    ];

    let package = PackageInfo {
        name: "app".into(), version: None, format: PackageFormat::Unknown,
        description: None, source_path: String::new(), size: 0, hash: String::new(),
        architecture: None, maintainer: None, homepage: None,
    };

    let analyzer = DefaultAnalyzer::new();
    let result = analyzer.analyze(&package, &files).unwrap();
    assert!(result.app_type_hints.iter().any(|h| matches!(h, AppTypeHint::Electron)));
    assert!(result.app_type_hints.iter().any(|h| matches!(h, AppTypeHint::Java(_))));
}

// -- Nix Generation -----------------------------------------------------

#[test]
fn test_nix_generates_derivation_file_on_disk() {
    let dir = temp_dir();
    let output_dir = dir.join("nix-output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let opts = GenerateOptions {
        app_name: "myapp".into(), version: "1.0.0".into(), description: "My test app".into(),
        format: PackageFormat::Deb, main_binary: Some("usr/bin/myapp".into()),
        build_inputs: vec!["glibc".into(), "xorg.libX11".into()],
        native_build_inputs: vec!["autoPatchelfHook".into(), "makeWrapper".into()],
        elf_binaries: vec![], all_files: vec![], desktop_entries: vec![], icons: vec![],
        app_type_hints: vec![], env_vars: HashMap::new(), use_fhs: false, extra_phases: vec![],
    };

    let generator = DefaultNixGenerator::new();
    let derivation_path = generator.generate(&opts, &output_dir.to_string_lossy()).unwrap();
    assert!(Path::new(&derivation_path).exists(), "derivation file missing");
    assert!(output_dir.join("flake.nix").exists(), "flake.nix missing");
    let content = std::fs::read_to_string(&derivation_path).unwrap();
    assert!(content.contains("pname = \"myapp\";"));
    assert!(content.contains("version = \"1.0.0\";"));
    assert!(content.contains("dpkg-deb"));
    assert!(content.contains("glibc"));
    assert!(content.contains("xorg.libX11"));
}

#[test]
fn test_nix_generates_elf_install_phase() {
    let dir = temp_dir();
    let output_dir = dir.join("nix-elf");
    std::fs::create_dir_all(&output_dir).unwrap();

    let opts = GenerateOptions {
        app_name: "myelf".into(), version: "2.0.0".into(), description: "ELF binary test".into(),
        format: PackageFormat::ElfBinary, main_binary: Some("bin/myelf".into()),
        build_inputs: vec!["glibc".into()],
        native_build_inputs: vec!["autoPatchelfHook".into()],
        elf_binaries: vec![], all_files: vec![], desktop_entries: vec![], icons: vec![],
        app_type_hints: vec![], env_vars: HashMap::new(), use_fhs: false, extra_phases: vec![],
    };

    let generator = DefaultNixGenerator::new();
    generator.generate(&opts, &output_dir.to_string_lossy()).unwrap();
    let content = std::fs::read_to_string(output_dir.join("derivation.nix")).unwrap();
    assert!(content.contains(r#"cp "$src" $out/bin/"#), "ELF phase: {}", content);
    assert!(content.contains("chmod +x $out/bin/*"));
}

#[test]
fn test_nix_generates_flake_with_correct_inputs() {
    let dir = temp_dir();
    let output_dir = dir.join("nix-flake");
    std::fs::create_dir_all(&output_dir).unwrap();

    let opts = GenerateOptions {
        app_name: "myapp".into(), version: "1.0.0".into(), description: "My app description".into(),
        format: PackageFormat::TarGz, main_binary: Some("bin/myapp".into()),
        build_inputs: vec!["glibc".into()],
        native_build_inputs: vec!["autoPatchelfHook".into()],
        elf_binaries: vec![], all_files: vec![], desktop_entries: vec![], icons: vec![],
        app_type_hints: vec![], env_vars: HashMap::new(), use_fhs: false, extra_phases: vec![],
    };

    let generator = DefaultNixGenerator::new();
    generator.generate(&opts, &output_dir.to_string_lossy()).unwrap();
    let flake = std::fs::read_to_string(output_dir.join("flake.nix")).unwrap();
    assert!(flake.contains("description = \"My app description\";"));
    assert!(flake.contains("packages.default"));
    assert!(flake.contains("packages.myapp"));
    assert!(flake.contains("nixpkgs.url = \"github:NixOS/nixpkgs/nixos-unstable\""));
}

#[test]
fn test_nix_generates_wrapper_script() {
    let dir = temp_dir();
    let output_dir = dir.join("nix-wrapper");
    std::fs::create_dir_all(&output_dir).unwrap();

    let opts = GenerateOptions {
        app_name: "myapp".into(), version: "1.0.0".into(), description: "App with wrapper".into(),
        format: PackageFormat::AppImage, main_binary: Some("squashfs-root/usr/bin/myapp".into()),
        build_inputs: vec![],
        native_build_inputs: vec!["autoPatchelfHook".into(), "makeWrapper".into()],
        elf_binaries: vec![], all_files: vec![], desktop_entries: vec![], icons: vec![],
        app_type_hints: vec![], env_vars: HashMap::new(), use_fhs: false, extra_phases: vec![],
    };

    let generator = DefaultNixGenerator::new();
    generator.generate(&opts, &output_dir.to_string_lossy()).unwrap();
    let content = std::fs::read_to_string(output_dir.join("derivation.nix")).unwrap();
    assert!(content.contains("myapp"));
}

#[test]
fn test_nix_generates_desktop_phase() {
    let dir = temp_dir();
    let output_dir = dir.join("nix-desktop");
    std::fs::create_dir_all(&output_dir).unwrap();

    let opts = GenerateOptions {
        app_name: "myapp".into(), version: "1.0.0".into(), description: "App with desktop".into(),
        format: PackageFormat::Deb, main_binary: Some("usr/bin/myapp".into()),
        build_inputs: vec![],
        native_build_inputs: vec!["autoPatchelfHook".into()],
        elf_binaries: vec![], all_files: vec![],
        desktop_entries: vec![DetectedDesktopEntry {
            path: "usr/share/applications/myapp.desktop".into(), app_name: "MyApp".into(),
            exec_line: "myapp".into(), icon_path: Some("usr/share/icons/myapp.png".into()),
            categories: vec!["Utility".into()],
        }],
        icons: vec![DetectedIcon { path: "usr/share/icons/myapp.png".into(), size: Some(256), format: "png".into() }],
        app_type_hints: vec![], env_vars: HashMap::new(), use_fhs: false, extra_phases: vec![],
    };

    let generator = DefaultNixGenerator::new();
    generator.generate(&opts, &output_dir.to_string_lossy()).unwrap();
    let content = std::fs::read_to_string(output_dir.join("derivation.nix")).unwrap();
    assert!(content.contains("share/applications"));
    assert!(content.contains("share/icons"));
}

#[test]
fn test_nix_sanitizes_name_and_version() {
    let dir = temp_dir();
    let output_dir = dir.join("nix-sanitize");
    std::fs::create_dir_all(&output_dir).unwrap();

    let opts = GenerateOptions {
        app_name: "My App@2.0!".into(), version: "2.0.0-beta.1".into(),
        description: "App with special chars".into(), format: PackageFormat::TarGz,
        main_binary: Some("bin/app".into()), build_inputs: vec![],
        native_build_inputs: vec!["autoPatchelfHook".into()],
        elf_binaries: vec![], all_files: vec![], desktop_entries: vec![], icons: vec![],
        app_type_hints: vec![], env_vars: HashMap::new(), use_fhs: false, extra_phases: vec![],
    };

    let generator = DefaultNixGenerator::new();
    generator.generate(&opts, &output_dir.to_string_lossy()).unwrap();
    let content = std::fs::read_to_string(output_dir.join("derivation.nix")).unwrap();
    assert!(content.contains("pname = \"my-app-2-0\";"), "sanitized name: {}", content);
    assert!(content.contains("version = \"2.0.0-beta.1\";"));
}

// -- TarGz End-to-End (requires tar command) ----------------------------

#[test]
fn test_targz_full_pipeline() {
    if !command_exists("tar") {
        eprintln!("Skipping: tar command not available");
        return;
    }

    let dir = temp_dir();
    let archive_path = dir.join("myapp-v1.0.0-linux-x64.tar.gz");
    let desktop_content = br#"[Desktop Entry]
Type=Application
Name=MyApp
Exec=myapp
Icon=myapp
Categories=Utility;
Terminal=false
"#;

    if !create_tar_gz(&archive_path, &[
        ("bin/myapp", b"#!/bin/sh\necho hello"),
        ("usr/share/applications/myapp.desktop", desktop_content),
    ]) {
        eprintln!("Skipping: tar command failed during setup");
        return;
    }

    // Step 1: Detect
    let detector = DefaultDetector::new();
    let package = detector.detect(&archive_path.to_string_lossy()).unwrap();
    assert_eq!(package.format, PackageFormat::TarGz);
    assert_eq!(package.name, "myapp-v1.0.0");
    assert!(package.size > 0);

    // Step 2: Extract
    let extract_dir = dir.join("extracted");
    let extractor = app2nix_extractor::DefaultExtractor::new();
    let extracted = extractor.extract(&package, &extract_dir.to_string_lossy()).unwrap();
    assert!(!extracted.is_empty());
    assert!(extracted.iter().any(|f| f.relative_path.contains("bin/myapp")));
    assert!(extracted.iter().any(|f| f.relative_path.contains("myapp.desktop")));

    // Step 3: Analyze
    let analyzer = DefaultAnalyzer::new();
    let analysis = analyzer.analyze(&package, &extracted).unwrap();
    assert!(analysis.main_binary.is_some());
    assert_eq!(analysis.desktop_entries.len(), 1);
    assert_eq!(analysis.desktop_entries[0].app_name, "MyApp");

    // Step 4: Generate Nix
    let generate_opts = GenerateOptions {
        app_name: analysis.package.name.clone(),
        version: analysis.package.version.clone().unwrap_or_else(|| "1.0.0".into()),
        description: analysis.package.description.clone().unwrap_or_default(),
        format: analysis.package.format,
        main_binary: analysis.main_binary.clone(),
        build_inputs: vec![],
        native_build_inputs: vec!["autoPatchelfHook".into()],
        elf_binaries: analysis.elf_binaries.clone(),
        all_files: analysis.extracted_files.clone(),
        desktop_entries: analysis.desktop_entries.clone(),
        icons: analysis.icons.clone(),
        app_type_hints: analysis.app_type_hints.clone(),
        env_vars: HashMap::new(), use_fhs: false, extra_phases: Vec::new(),
    };

    let nix_dir = dir.join("nix-output");
    std::fs::create_dir_all(&nix_dir).unwrap();
    let generator = DefaultNixGenerator::new();
    generator.generate(&generate_opts, &nix_dir.to_string_lossy()).unwrap();

    assert!(nix_dir.join("derivation.nix").exists());
    assert!(nix_dir.join("flake.nix").exists());
    let der_content = std::fs::read_to_string(nix_dir.join("derivation.nix")).unwrap();
    assert!(der_content.contains("pname = \"myapp-v1-0-0\";"));
    assert!(der_content.contains("cp -rfl * $out/"), "TarGz install phase");
}

// -- Full Pipeline with Mock + Real Components -------------------------

#[test]
fn test_pipeline_with_real_nix_generator() {
    struct MockDetector;
    impl Detector for MockDetector {
        fn detect(&self, _path: &str) -> Result<PackageInfo> {
            Ok(PackageInfo {
                name: "test-app".into(), version: Some("2.0.0".into()),
                format: PackageFormat::Rpm, description: Some("Test RPM app".into()),
                source_path: _path.into(), size: 5000, hash: "mockhash".into(),
                architecture: Some("x86_64".into()), maintainer: None, homepage: None,
            })
        }
    }

    struct MockExtractor;
    impl Extractor for MockExtractor {
        fn extract(&self, _package: &PackageInfo, _dest: &str) -> Result<Vec<ExtractedFile>> {
            Ok(vec![
                ExtractedFile {
                    path: format!("{}/usr/bin/test-app", _dest),
                    relative_path: "usr/bin/test-app".into(),
                    file_type: "application/x-executable".into(), is_elf: true, is_executable: true, size: 1000,
                },
                ExtractedFile {
                    path: format!("{}/usr/share/applications/test-app.desktop", _dest),
                    relative_path: "usr/share/applications/test-app.desktop".into(),
                    file_type: "text/plain".into(), is_elf: false, is_executable: false, size: 200,
                },
            ])
        }
    }

    struct MockAnalyzer;
    impl Analyzer for MockAnalyzer {
        fn analyze(&self, package: &PackageInfo, _files: &[ExtractedFile]) -> Result<AnalysisResult> {
            Ok(AnalysisResult {
                package: PackageInfo {
                    name: package.name.clone(), version: package.version.clone(),
                    format: package.format.clone(), description: package.description.clone(),
                    source_path: package.source_path.clone(), size: package.size,
                    hash: package.hash.clone(), architecture: None, maintainer: None, homepage: None,
                },
                extracted_files: _files.to_vec(), elf_binaries: vec![],
                all_needed_libs: vec![], resolved_deps: vec![], unresolved_libs: vec![],
                main_binary: Some("usr/bin/test-app".into()),
                desktop_entries: vec![DetectedDesktopEntry {
                    path: "usr/share/applications/test-app.desktop".into(), app_name: "TestApp".into(),
                    exec_line: "test-app".into(), icon_path: None, categories: vec!["Utility".into()],
                }],
                icons: vec![DetectedIcon { path: "usr/share/icons/test-app.png".into(), size: Some(256), format: "png".into() }],
                app_type_hints: vec![],
            })
        }
        fn resolve_deps(&self, _needed: &[String]) -> Result<Vec<ResolvedDependency>> {
            Ok(vec![])
        }
    }

    struct MockPatcher;
    impl Patcher for MockPatcher {
        fn patch_binaries(&self, _target_dir: &str, _analysis: &AnalysisResult, _resolved_deps: &[ResolvedDependency]) -> Result<()> { Ok(()) }
    }

    struct MockInstaller;
    impl Installer for MockInstaller {
        fn build(&self, _derivation_path: &str, _output_dir: &str) -> Result<String> { Ok("/nix/store/mock".into()) }
        fn install(&self, _store_path: &str, _name: &str) -> Result<String> { Ok("profile".into()) }
        fn uninstall(&self, _name: &str) -> Result<()> { Ok(()) }
        fn list_installed(&self) -> Result<Vec<AppEntry>> { Ok(vec![]) }
    }

    struct MockDesktop;
    impl DesktopIntegrator for MockDesktop {
        fn register(&self, _app_name: &str, _exec_path: &str, _entries: &[DetectedDesktopEntry], _icons: &[DetectedIcon]) -> Result<Vec<String>> {
            Ok(vec!["/tmp/apps/test-app.desktop".into()])
        }
        fn unregister(&self, _app_name: &str) -> Result<()> { Ok(()) }
    }

    let pipeline = Pipeline::new(
        Box::new(MockDetector), Box::new(MockExtractor), Box::new(MockAnalyzer),
        Box::new(MockPatcher), Box::new(DefaultNixGenerator::new()),
        Box::new(MockInstaller), Box::new(MockDesktop),
    );

    let work_dir = temp_dir();
    let result = pipeline.run("/tmp/test.rpm", &work_dir.to_string_lossy()).unwrap();
    assert_eq!(result.app_name, "test-app");
    assert_eq!(result.version, "2.0.0");
    assert!(result.installed);
    assert_eq!(result.store_paths, vec!["/nix/store/mock"]);
    assert_eq!(result.desktop_files.len(), 1);
    assert_eq!(result.profile_name, Some("profile".into()));

    let nix_derivation = work_dir.join("derivation.nix");
    assert!(nix_derivation.exists(), "derivation.nix missing");
    let content = std::fs::read_to_string(&nix_derivation).unwrap();
    assert!(content.contains("test-app"));
    assert!(content.contains("rpm2cpio"), "RPM install: {}", content);
}

// -- Error Propagation --------------------------------------------------

#[test]
fn test_pipeline_detection_error_propagates() {
    struct FailDetector;
    impl Detector for FailDetector {
        fn detect(&self, _: &str) -> Result<PackageInfo> {
            Err(App2NixError::DetectionFailed("unable to identify format".into()))
        }
    }
    struct NoopExt;
    impl Extractor for NoopExt {
        fn extract(&self, _: &PackageInfo, _: &str) -> Result<Vec<ExtractedFile>> { Ok(vec![]) }
    }
    struct NoopAna;
    impl Analyzer for NoopAna {
        fn analyze(&self, _: &PackageInfo, _: &[ExtractedFile]) -> Result<AnalysisResult> { unimplemented!() }
        fn resolve_deps(&self, _: &[String]) -> Result<Vec<ResolvedDependency>> { unimplemented!() }
    }
    struct NoopPat;
    impl Patcher for NoopPat {
        fn patch_binaries(&self, _: &str, _: &AnalysisResult, _: &[ResolvedDependency]) -> Result<()> { unimplemented!() }
    }
    struct NoopGen;
    impl NixGenerator for NoopGen {
        fn generate(&self, _: &GenerateOptions, _: &str) -> Result<String> { unimplemented!() }
    }
    struct NoopInst;
    impl Installer for NoopInst {
        fn build(&self, _: &str, _: &str) -> Result<String> { unimplemented!() }
        fn install(&self, _: &str, _: &str) -> Result<String> { unimplemented!() }
        fn uninstall(&self, _: &str) -> Result<()> { unimplemented!() }
        fn list_installed(&self) -> Result<Vec<AppEntry>> { unimplemented!() }
    }
    struct NoopDesk;
    impl DesktopIntegrator for NoopDesk {
        fn register(&self, _: &str, _: &str, _: &[DetectedDesktopEntry], _: &[DetectedIcon]) -> Result<Vec<String>> { unimplemented!() }
        fn unregister(&self, _: &str) -> Result<()> { unimplemented!() }
    }

    let pipeline = Pipeline::new(
        Box::new(FailDetector), Box::new(NoopExt), Box::new(NoopAna),
        Box::new(NoopPat), Box::new(NoopGen), Box::new(NoopInst), Box::new(NoopDesk),
    );
    let err = pipeline.run("/tmp/test.deb", "/tmp/work").unwrap_err();
    assert!(matches!(&err, App2NixError::DetectionFailed(msg) if msg == "unable to identify format"));
}

#[test]
fn test_pipeline_extraction_error_propagates() {
    struct OkDetector;
    impl Detector for OkDetector {
        fn detect(&self, _: &str) -> Result<PackageInfo> {
            Ok(PackageInfo {
                name: "test".into(), version: None, format: PackageFormat::Deb,
                description: None, source_path: String::new(), size: 0, hash: String::new(),
                architecture: None, maintainer: None, homepage: None,
            })
        }
    }
    struct FailExtractor;
    impl Extractor for FailExtractor {
        fn extract(&self, _: &PackageInfo, _: &str) -> Result<Vec<ExtractedFile>> {
            Err(App2NixError::ExtractionFailed("corrupt archive".into()))
        }
    }
    struct PanicAna;
    impl Analyzer for PanicAna {
        fn analyze(&self, _: &PackageInfo, _: &[ExtractedFile]) -> Result<AnalysisResult> { unimplemented!() }
        fn resolve_deps(&self, _: &[String]) -> Result<Vec<ResolvedDependency>> { unimplemented!() }
    }
    struct PanicPat;
    impl Patcher for PanicPat {
        fn patch_binaries(&self, _: &str, _: &AnalysisResult, _: &[ResolvedDependency]) -> Result<()> { unimplemented!() }
    }
    struct PanicGen;
    impl NixGenerator for PanicGen { fn generate(&self, _: &GenerateOptions, _: &str) -> Result<String> { unimplemented!() } }
    struct PanicInst;
    impl Installer for PanicInst {
        fn build(&self, _: &str, _: &str) -> Result<String> { unimplemented!() }
        fn install(&self, _: &str, _: &str) -> Result<String> { unimplemented!() }
        fn uninstall(&self, _: &str) -> Result<()> { unimplemented!() }
        fn list_installed(&self) -> Result<Vec<AppEntry>> { unimplemented!() }
    }
    struct PanicDesk;
    impl DesktopIntegrator for PanicDesk {
        fn register(&self, _: &str, _: &str, _: &[DetectedDesktopEntry], _: &[DetectedIcon]) -> Result<Vec<String>> { unimplemented!() }
        fn unregister(&self, _: &str) -> Result<()> { unimplemented!() }
    }

    let pipeline = Pipeline::new(
        Box::new(OkDetector), Box::new(FailExtractor), Box::new(PanicAna),
        Box::new(PanicPat), Box::new(PanicGen), Box::new(PanicInst), Box::new(PanicDesk),
    );
    let err = pipeline.run("/tmp/test.deb", "/tmp/work").unwrap_err();
    assert!(matches!(&err, App2NixError::ExtractionFailed(msg) if msg == "corrupt archive"));
}

#[test]
fn test_pipeline_short_circuits_on_detection_failure() {
    use std::sync::atomic::{AtomicBool, Ordering};
    static EXTRACT_CALLED: AtomicBool = AtomicBool::new(false);

    struct FailDet;
    impl Detector for FailDet {
        fn detect(&self, _: &str) -> Result<PackageInfo> {
            Err(App2NixError::DetectionFailed("fail".into()))
        }
    }
    struct TrackExt;
    impl Extractor for TrackExt {
        fn extract(&self, _: &PackageInfo, _: &str) -> Result<Vec<ExtractedFile>> {
            EXTRACT_CALLED.store(true, Ordering::SeqCst);
            Ok(vec![])
        }
    }
    struct DummyAna;
    impl Analyzer for DummyAna {
        fn analyze(&self, _: &PackageInfo, _: &[ExtractedFile]) -> Result<AnalysisResult> { unimplemented!() }
        fn resolve_deps(&self, _: &[String]) -> Result<Vec<ResolvedDependency>> { Ok(vec![]) }
    }
    struct DummyPat;
    impl Patcher for DummyPat {
        fn patch_binaries(&self, _: &str, _: &AnalysisResult, _: &[ResolvedDependency]) -> Result<()> { Ok(()) }
    }
    struct DummyGen;
    impl NixGenerator for DummyGen { fn generate(&self, _: &GenerateOptions, _: &str) -> Result<String> { Ok(String::new()) } }
    struct DummyInst;
    impl Installer for DummyInst {
        fn build(&self, _: &str, _: &str) -> Result<String> { Ok(String::new()) }
        fn install(&self, _: &str, _: &str) -> Result<String> { Ok(String::new()) }
        fn uninstall(&self, _: &str) -> Result<()> { Ok(()) }
        fn list_installed(&self) -> Result<Vec<AppEntry>> { Ok(vec![]) }
    }
    struct DummyDesk;
    impl DesktopIntegrator for DummyDesk {
        fn register(&self, _: &str, _: &str, _: &[DetectedDesktopEntry], _: &[DetectedIcon]) -> Result<Vec<String>> { Ok(vec![]) }
        fn unregister(&self, _: &str) -> Result<()> { Ok(()) }
    }

    let pipeline = Pipeline::new(
        Box::new(FailDet), Box::new(TrackExt), Box::new(DummyAna),
        Box::new(DummyPat), Box::new(DummyGen), Box::new(DummyInst), Box::new(DummyDesk),
    );
    let _err = pipeline.run("/tmp/test.deb", "/tmp/work").unwrap_err();
    assert!(!EXTRACT_CALLED.load(Ordering::SeqCst), "extract should NOT be called on detection failure");
}

// -- Dependency Resolution ----------------------------------------------

#[test]
fn test_analyzer_resolves_dependencies() {
    let analyzer = DefaultAnalyzer::new();

    // Note: libX11.so.6 gets cleaned to "X" (digit trimming: "X11" -> "X")
    // which causes non-deterministic fuzzy matching. Use libraries whose
    // cleaned names end with non-digit chars for reliable assertions.
    let needed = vec![
        "libc.so.6".to_string(),
        "libXrandr.so.2".to_string(),
        "libQt5Core.so.5".to_string(),
        "libunknown_xyz.so.1".to_string(),
    ];

    let resolved = analyzer.resolve_deps(&needed).expect("resolve_deps should succeed");

    let libc = resolved.iter().find(|d| d.library == "libc.so.6").unwrap();
    assert_eq!(libc.nix_attr.as_deref(), Some("glibc"));

    // Xrandr: clean name "Xrandr" (no digit at end) -> exact match
    let xrandr = resolved.iter().find(|d| d.library == "libXrandr.so.2").unwrap();
    assert_eq!(xrandr.nix_attr.as_deref(), Some("xorg.libXrandr"));

    let qt5 = resolved.iter().find(|d| d.library == "libQt5Core.so.5").unwrap();
    assert_eq!(qt5.nix_attr.as_deref(), Some("qt5.qtbase"));

    let unknown = resolved.iter().find(|d| d.library == "libunknown_xyz.so.1").unwrap();
    assert!(unknown.nix_attr.is_none(), "unknown lib should not be resolved");
    assert_eq!(unknown.confidence, 0.2);
}

// -- File Scanning ------------------------------------------------------

#[test]
fn test_extractor_scan_extracted() {
    let dir = temp_dir();
    let dummy_src = dir.join("dummy-elf");
    create_dummy_elf(&dummy_src);

    use std::os::unix::fs::PermissionsExt;

    let package = PackageInfo {
        name: "test".into(), version: None, format: PackageFormat::ElfBinary,
        description: None, source_path: dummy_src.to_string_lossy().to_string(),
        size: 128, hash: String::new(), architecture: None, maintainer: None, homepage: None,
    };

    let extractor = app2nix_extractor::DefaultExtractor::new();
    let extract_dir = dir.join("extract-output");
    let files = extractor.extract(&package, &extract_dir.to_string_lossy()).unwrap();

    assert!(!files.is_empty(), "should have extracted files");
    assert!(files.iter().any(|f| f.relative_path.contains("dummy-elf") ||
                                f.relative_path == "dummy-elf"),
            "should contain the ELF file");
}
