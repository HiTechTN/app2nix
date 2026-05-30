use crate::DefaultPatcher;
use app2nix_core::Patcher;
use app2nix_core::{AnalysisResult, ElfInfo, ExtractedFile, PackageFormat, PackageInfo};
use std::collections::HashMap;
use std::fs;
use std::os::unix::fs::PermissionsExt;

fn make_analysis() -> AnalysisResult {
    AnalysisResult {
        package: PackageInfo {
            name: "test-app".into(),
            version: Some("1.0".into()),
            format: PackageFormat::Deb,
            description: Some("Test".into()),
            source_path: "/tmp/test.deb".into(),
            size: 1024,
            hash: "abc123".into(),
            architecture: None,
            maintainer: None,
            homepage: None,
        },
        extracted_files: vec![],
        elf_binaries: vec![],
        all_needed_libs: vec![],
        resolved_deps: vec![],
        unresolved_libs: vec![],
        main_binary: None,
        desktop_entries: vec![],
        icons: vec![],
        app_type_hints: vec![],
    }
}

#[test]
fn test_make_executable_already_executable() {
    let dir = std::env::temp_dir().join("app2nix_test_patch_exec");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("test_exe");
    fs::write(&path, b"binary").unwrap();
    let mut perms = fs::metadata(&path).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&path, perms).unwrap();

    let patcher = DefaultPatcher::new();
    let result = patcher.make_executable(&path.to_string_lossy());
    assert!(result.is_ok());

    let meta = fs::metadata(&path).unwrap();
    assert!(
        meta.permissions().mode() & 0o111 != 0,
        "File should remain executable"
    );
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_make_executable_non_executable() {
    let dir = std::env::temp_dir().join("app2nix_test_patch_noexec");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("test_exe");
    fs::write(&path, b"binary").unwrap();
    let mut perms = fs::metadata(&path).unwrap().permissions();
    perms.set_mode(0o644);
    fs::set_permissions(&path, perms).unwrap();

    let patcher = DefaultPatcher::new();
    let result = patcher.make_executable(&path.to_string_lossy());
    assert!(result.is_ok());

    let meta = fs::metadata(&path).unwrap();
    assert!(
        meta.permissions().mode() & 0o111 != 0,
        "File should now be executable"
    );
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_make_executable_nonexistent() {
    let patcher = DefaultPatcher::new();
    let result = patcher.make_executable("/nonexistent/path");
    assert!(result.is_err());
}

#[test]
fn test_generate_wrapper_creates_file() {
    let dir = std::env::temp_dir().join("app2nix_test_patch_wrapper");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();

    // Create a mock binary
    let bin_dir = dir.join("bin");
    fs::create_dir_all(&bin_dir).unwrap();
    let bin_path = bin_dir.join("testapp");
    fs::write(&bin_path, b"binary").unwrap();
    let mut perms = fs::metadata(&bin_path).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&bin_path, perms).unwrap();

    let patcher = DefaultPatcher::new();
    let result = patcher.generate_wrapper(
        &bin_path.to_string_lossy(),
        &dir.to_string_lossy(),
        "test-app",
    );
    assert!(result.is_ok());

    let wrapper_path = result.unwrap();
    assert!(
        wrapper_path.contains(".test-app_wrapper"),
        "Wrapper file should have correct name"
    );

    let content = fs::read_to_string(&wrapper_path).unwrap();
    assert!(content.contains("#!/usr/bin/env bash"));
    assert!(content.contains("test-app"));
    assert!(content.contains("exec"));

    let meta = fs::metadata(&wrapper_path).unwrap();
    assert!(
        meta.permissions().mode() & 0o111 != 0,
        "Wrapper should be executable"
    );

    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_generate_wrapper_includes_path_and_env() {
    let dir = std::env::temp_dir().join("app2nix_test_patch_wrapper2");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("bin")).unwrap();
    let bin_path = dir.join("bin").join("app");
    fs::write(&bin_path, b"binary").unwrap();
    fs::set_permissions(&bin_path, fs::Permissions::from_mode(0o755)).unwrap();

    let patcher = DefaultPatcher::new();
    let result = patcher
        .generate_wrapper(
            &bin_path.to_string_lossy(),
            &dir.to_string_lossy(),
            "my-app",
        )
        .unwrap();

    let content = fs::read_to_string(&result).unwrap();
    assert!(content.contains("PATH="));
    assert!(content.contains("LD_LIBRARY_PATH"));
    assert!(content.contains("APP2NIX_APP=\"my-app\""));
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_patch_binaries_no_elf() {
    let dir = std::env::temp_dir().join("app2nix_test_patch_noelf");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let patcher = DefaultPatcher::new();
    let analysis = make_analysis();
    let result = patcher.patch_binaries(&dir.to_string_lossy(), &analysis, &[]);
    assert!(result.is_ok(), "Should succeed with no ELF binaries");
    let _ = fs::remove_dir_all(&dir);
}
