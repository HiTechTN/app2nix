use crate::DefaultDetector;
use app2nix_core::{PackageFormat, Detector};

#[test]
fn test_detect_by_extension_deb() {
    let fmt = DefaultDetector::detect_by_extension("package.deb");
    assert_eq!(fmt, Some(PackageFormat::Deb));
}

#[test]
fn test_detect_by_extension_rpm() {
    let fmt = DefaultDetector::detect_by_extension("package.rpm");
    assert_eq!(fmt, Some(PackageFormat::Rpm));
}

#[test]
fn test_detect_by_extension_appimage() {
    let fmt = DefaultDetector::detect_by_extension("App.AppImage");
    assert_eq!(fmt, Some(PackageFormat::AppImage));
}

#[test]
fn test_detect_by_extension_appimage_lowercase() {
    let fmt = DefaultDetector::detect_by_extension("app.appimage");
    assert_eq!(fmt, Some(PackageFormat::AppImage));
}

#[test]
fn test_detect_by_extension_targz() {
    let fmt = DefaultDetector::detect_by_extension("archive.tar.gz");
    assert_eq!(fmt, Some(PackageFormat::TarGz));
}

#[test]
fn test_detect_by_extension_zip() {
    let fmt = DefaultDetector::detect_by_extension("archive.zip");
    assert_eq!(fmt, Some(PackageFormat::Zip));
}

#[test]
fn test_detect_by_extension_flatpak() {
    let fmt = DefaultDetector::detect_by_extension("app.flatpak");
    assert_eq!(fmt, Some(PackageFormat::Flatpak));
}

#[test]
fn test_detect_by_extension_snap() {
    let fmt = DefaultDetector::detect_by_extension("app.snap");
    assert_eq!(fmt, Some(PackageFormat::Snap));
}

#[test]
fn test_detect_by_extension_jar() {
    let fmt = DefaultDetector::detect_by_extension("app.jar");
    assert_eq!(fmt, Some(PackageFormat::Java));
}

#[test]
fn test_detect_by_extension_gz_only() {
    let fmt = DefaultDetector::detect_by_extension("file.gz");
    assert_eq!(fmt, None);
}

#[test]
fn test_detect_by_extension_no_extension() {
    let fmt = DefaultDetector::detect_by_extension("Makefile");
    assert_eq!(fmt, None);
}

#[test]
fn test_infer_name_simple() {
    let name = DefaultDetector::infer_name("firefox.deb");
    assert_eq!(name, "firefox");
}

#[test]
fn test_infer_name_strips_arch() {
    let name = DefaultDetector::infer_name("code_1.80_amd64.deb");
    assert_eq!(name, "code_1.80");
}

#[test]
fn test_infer_name_strips_x86_64() {
    let name = DefaultDetector::infer_name("discord-0.0.71-x86_64.rpm");
    assert_eq!(name, "discord-0.0.71");
}

#[test]
fn test_infer_name_strips_linux() {
    let name = DefaultDetector::infer_name("teamviewer_15.50_linux.deb");
    assert_eq!(name, "teamviewer_15.50");
}

#[test]
fn test_infer_name_strips_tar_gz() {
    let name = DefaultDetector::infer_name("node-v18.0.0-linux-x64.tar.gz");
    assert_eq!(name, "node-v18.0.0");
}

#[test]
fn test_infer_name_lowercase() {
    let name = DefaultDetector::infer_name("MyApp-1.0.AppImage");
    assert_eq!(name, "myapp-1.0");
}

#[test]
fn test_infer_name_no_stem() {
    let name = DefaultDetector::infer_name("/");
    assert_eq!(name, "unknown");
}

#[test]
fn test_compute_hash_empty_file() {
    let dir = std::env::temp_dir().join("app2nix_test_detector_hash");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("empty.bin");
    std::fs::write(&path, b"").unwrap();
    let hash = DefaultDetector::compute_hash(&path.to_string_lossy());
    assert_eq!(hash.len(), 64, "SHA256 should be 64 hex chars");
    assert_eq!(hash, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn test_compute_hash_known_content() {
    let dir = std::env::temp_dir().join("app2nix_test_detector_hash2");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("hello.bin");
    std::fs::write(&path, b"hello").unwrap();
    let hash = DefaultDetector::compute_hash(&path.to_string_lossy());
    assert_eq!(hash, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn test_compute_hash_file_not_found() {
    let hash = DefaultDetector::compute_hash("/nonexistent/path");
    assert_eq!(hash, "unknown");
}

#[test]
fn test_detect_file_not_found_error() {
    let detector = DefaultDetector::new();
    let result = detector.detect("/tmp/does_not_exist_12345.deb");
    assert!(result.is_err());
    let err = result.unwrap_err();
    let err_str = err.to_string();
    assert!(err_str.contains("File not found") || err_str.contains("No such file"));
}

#[test]
fn test_detect_by_magic_elf() {
    let dir = std::env::temp_dir().join("app2nix_test_magic_elf");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("test_elf");
    let mut elf_bytes = vec![0x7f, 0x45, 0x4c, 0x46, 0x02, 0x01, 0x01, 0x00];
    elf_bytes.resize(32, 0x00);
    std::fs::write(&path, &elf_bytes).unwrap();
    let fmt = DefaultDetector::detect_by_magic(&path.to_string_lossy());
    assert_eq!(fmt, Some(PackageFormat::ElfBinary));
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn test_detect_by_magic_targz() {
    let dir = std::env::temp_dir().join("app2nix_test_magic_targz");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("test.tar.gz");
    // gzip magic: 1f 8b 08
    let mut gz_bytes = vec![0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00];
    gz_bytes.resize(32, 0x00);
    std::fs::write(&path, &gz_bytes).unwrap();
    let fmt = DefaultDetector::detect_by_magic(&path.to_string_lossy());
    assert_eq!(fmt, Some(PackageFormat::TarGz));
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn test_detect_by_magic_zip() {
    let dir = std::env::temp_dir().join("app2nix_test_magic_zip");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("test.zip");
    let mut zip_bytes = vec![0x50, 0x4b, 0x03, 0x04];
    zip_bytes.resize(32, 0x00);
    std::fs::write(&path, &zip_bytes).unwrap();
    let fmt = DefaultDetector::detect_by_magic(&path.to_string_lossy());
    assert_eq!(fmt, Some(PackageFormat::Zip));
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn test_detect_by_magic_too_short() {
    let dir = std::env::temp_dir().join("app2nix_test_magic_short");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("short.bin");
    std::fs::write(&path, b"ab").unwrap();
    let fmt = DefaultDetector::detect_by_magic(&path.to_string_lossy());
    assert_eq!(fmt, None);
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn test_detect_by_magic_rpm() {
    let dir = std::env::temp_dir().join("app2nix_test_magic_rpm");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("test.rpm");
    // RPM magic: ed ab ee db
    let mut rpm_bytes = vec![0xed, 0xab, 0xee, 0xdb];
    rpm_bytes.resize(32, 0x00);
    std::fs::write(&path, &rpm_bytes).unwrap();
    let fmt = DefaultDetector::detect_by_magic(&path.to_string_lossy());
    assert_eq!(fmt, Some(PackageFormat::Rpm));
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn test_detect_by_magic_shebang() {
    let dir = std::env::temp_dir().join("app2nix_test_magic_shebang");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("script.sh");
    std::fs::write(&path, b"#!/bin/bash\necho hello").unwrap();
    let fmt = DefaultDetector::detect_by_magic(&path.to_string_lossy());
    assert_eq!(fmt, Some(PackageFormat::Unknown));
    let _ = std::fs::remove_dir_all(&dir);
}
