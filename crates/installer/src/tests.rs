use crate::DefaultInstaller;
use app2nix_core::{AppRegistry, AppEntry, PackageFormat, Installer};
use std::fs;

#[test]
fn test_load_registry_empty_when_no_file() {
    let dir = std::env::temp_dir().join("app2nix_test_installer_reg");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let reg_path = dir.join("registry.json");
    let installer = DefaultInstaller::new("nix", true, &reg_path.to_string_lossy());
    let registry = installer.load_registry();
    assert!(registry.apps.is_empty());
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_save_and_load_registry() {
    let dir = std::env::temp_dir().join("app2nix_test_installer_save");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let reg_path = dir.join("registry.json");

    let installer = DefaultInstaller::new("nix", true, &reg_path.to_string_lossy());
    let mut registry = AppRegistry { apps: vec![] };
    registry.apps.push(AppEntry {
        name: "test-app".into(),
        version: "1.0".into(),
        format: PackageFormat::Deb,
        install_path: "/nix/store/xxx".into(),
        store_path: Some("/nix/store/xxx".into()),
        desktop_file: Some("test-app.desktop".into()),
        profile: "app2nix-test-app".into(),
        installed_at: "2024-01-01T00:00:00Z".into(),
        size: 1024,
    });
    installer.save_registry(&registry).unwrap();
    assert!(reg_path.exists(), "Registry file should exist");

    let loaded = installer.load_registry();
    assert_eq!(loaded.apps.len(), 1);
    assert_eq!(loaded.apps[0].name, "test-app");
    assert_eq!(loaded.apps[0].version, "1.0");
    assert_eq!(loaded.apps[0].format, PackageFormat::Deb);
    assert_eq!(loaded.apps[0].profile, "app2nix-test-app");

    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_save_registry_creates_parent_dirs() {
    let dir = std::env::temp_dir().join("app2nix_test_installer_parent");
    let _ = fs::remove_dir_all(&dir);
    // Don't create the parent dir - should be created by save
    let nested_dir = dir.join("deep").join("nested");
    let reg_path = nested_dir.join("registry.json");
    let installer = DefaultInstaller::new("nix", true, &reg_path.to_string_lossy());
    let registry = AppRegistry { apps: vec![] };
    installer.save_registry(&registry).unwrap();
    assert!(reg_path.exists(), "Registry file should be created with parent dirs");
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_load_registry_empty_json() {
    let dir = std::env::temp_dir().join("app2nix_test_installer_empty");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let reg_path = dir.join("registry.json");
    fs::write(&reg_path, r#"{"apps": []}"#).unwrap();
    let installer = DefaultInstaller::new("nix", true, &reg_path.to_string_lossy());
    let registry = installer.load_registry();
    assert!(registry.apps.is_empty());
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_load_registry_invalid_json() {
    let dir = std::env::temp_dir().join("app2nix_test_installer_badjson");
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let reg_path = dir.join("registry.json");
    fs::write(&reg_path, "not valid json").unwrap();
    let installer = DefaultInstaller::new("nix", true, &reg_path.to_string_lossy());
    let registry = installer.load_registry();
    assert!(registry.apps.is_empty(), "Should return empty registry on parse error");
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn test_installer_new_stores_params() {
    let installer = DefaultInstaller::new("/custom/nix", false, "/tmp/reg.json");
    // We can't directly access the fields (they're private),
    // but we can verify the type constructs
    assert!(installer.list_installed().is_ok());
}
