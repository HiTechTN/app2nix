use crate::DefaultExtractor;
use std::fs;
use std::os::unix::fs::PermissionsExt;

#[test]
fn test_check_elf_true() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_check_elf");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("test_elf");
    fs::write(&path, &[0x7f, 0x45, 0x4c, 0x46, 0x02, 0x01, 0x01, 0x00]).unwrap();
    assert!(DefaultExtractor::check_elf(&path.to_string_lossy()));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_check_elf_false_for_text() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_check_not_elf");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("test.txt");
    fs::write(&path, b"not an elf file").unwrap();
    assert!(!DefaultExtractor::check_elf(&path.to_string_lossy()));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_check_elf_short_file() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_check_short");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("short.bin");
    fs::write(&path, b"ab").unwrap();
    assert!(!DefaultExtractor::check_elf(&path.to_string_lossy()));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_check_elf_nonexistent_file() {
    assert!(!DefaultExtractor::check_elf("/nonexistent/path"));
}

#[test]
fn test_check_executable_true() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_check_exec");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("exec.sh");
    fs::write(&path, b"#!/bin/bash").unwrap();
    let mut perms = fs::metadata(&path).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&path, perms).unwrap();
    assert!(DefaultExtractor::check_executable(&path.to_string_lossy()));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_check_executable_false() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_check_noexec");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("readme.txt");
    fs::write(&path, b"hello").unwrap();
    let mut perms = fs::metadata(&path).unwrap().permissions();
    perms.set_mode(0o644);
    fs::set_permissions(&path, perms).unwrap();
    assert!(!DefaultExtractor::check_executable(&path.to_string_lossy()));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_check_executable_nonexistent() {
    assert!(!DefaultExtractor::check_executable("/nonexistent/path"));
}

#[test]
fn test_scan_extracted_empty_dir() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_scan_empty");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let files = DefaultExtractor::scan_extracted(&dir.to_string_lossy()).unwrap();
    assert!(files.is_empty());
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_scan_extracted_with_files() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_scan_files");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("subdir")).unwrap();
    fs::write(dir.join("file1.txt"), b"hello").unwrap();
    fs::write(dir.join("subdir").join("file2.txt"), b"world").unwrap();
    let files = DefaultExtractor::scan_extracted(&dir.to_string_lossy()).unwrap();
    assert_eq!(files.len(), 2);
    let rel_paths: Vec<&str> = files.iter().map(|f| f.relative_path.as_str()).collect();
    assert!(rel_paths.contains(&"file1.txt"));
    assert!(rel_paths.contains(&"subdir/file2.txt"));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_scan_extracted_skips_directories() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_scan_dirs");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("emptydir")).unwrap();
    fs::write(dir.join("file.txt"), b"hello").unwrap();
    let files = DefaultExtractor::scan_extracted(&dir.to_string_lossy()).unwrap();
    assert_eq!(files.len(), 1);
    assert_eq!(files[0].relative_path, "file.txt");
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_scan_extracted_nonexistent_dir() {
    let result = DefaultExtractor::scan_extracted("/nonexistent/path");
    assert!(result.is_err() || result.unwrap().is_empty());
}

#[test]
fn test_validate_appimage_source_rejects_text_file() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_appimage_text");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("fake.AppImage");
    fs::write(&path, b"not an appimage").unwrap();

    let result = DefaultExtractor::validate_appimage_source(&path);
    assert!(result.is_err());
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_validate_appimage_source_rejects_elf_without_marker() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_appimage_elf_no_marker");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("fake.AppImage");
    fs::write(&path, &[0x7f, 0x45, 0x4c, 0x46, 0x02, 0x01, 0x01, 0x00]).unwrap();

    let result = DefaultExtractor::validate_appimage_source(&path);
    assert!(result.is_err());
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_validate_appimage_source_accepts_elf_with_marker() {
    let dir = std::env::temp_dir().join("app2nix_test_ext_appimage_marker");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("fake.AppImage");
    let mut data = vec![0x7f, 0x45, 0x4c, 0x46, 0x02, 0x01, 0x01, 0x00];
    data.extend_from_slice(b"AI\x02");
    fs::write(&path, data).unwrap();

    let result = DefaultExtractor::validate_appimage_source(&path);
    assert!(result.is_ok());
    let _ = fs::remove_dir_all(&dir);
}
