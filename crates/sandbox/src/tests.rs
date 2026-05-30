use crate::{FhsCompat, Sandbox};

#[test]
fn test_sandbox_disabled_returns_temp_dir() {
    let sandbox = Sandbox::new(false);
    assert!(!sandbox.is_enabled());
    let path = sandbox.create_sandbox("test").unwrap();
    assert!(path.contains("app2nix-test"), "Should return a temp path");
    // When disabled, cleanup is a no-op
    assert!(sandbox.cleanup(&path).is_ok());
}

#[test]
fn test_sandbox_enabled_creates_directories() {
    let sandbox = Sandbox::new(true);
    assert!(sandbox.is_enabled());
    let path = sandbox.create_sandbox("test-dir").unwrap();
    assert!(
        path.contains("app2nix-sandbox"),
        "Should create sandbox dir"
    );

    // Verify subdirectories exist
    let sandbox_path = std::path::Path::new(&path);
    assert!(
        sandbox_path.join("build").exists(),
        "build dir should exist"
    );
    assert!(
        sandbox_path.join("cache").exists(),
        "cache dir should exist"
    );
    assert!(
        sandbox_path.join("output").exists(),
        "output dir should exist"
    );

    // Cleanup
    assert!(sandbox.cleanup(&path).is_ok());
    assert!(
        !sandbox_path.exists(),
        "Sandbox dir should be removed after cleanup"
    );
}

#[test]
fn test_sandbox_enabled_creates_multiple() {
    let sandbox = Sandbox::new(true);
    let p1 = sandbox.create_sandbox("s1").unwrap();
    let p2 = sandbox.create_sandbox("s2").unwrap();
    assert_ne!(p1, p2, "Different sandboxes should have different paths");
    assert!(std::path::Path::new(&p1).exists());
    assert!(std::path::Path::new(&p2).exists());
    let _ = sandbox.cleanup(&p1);
    let _ = sandbox.cleanup(&p2);
}

#[test]
fn test_sandbox_cleanup_nonexistent_path() {
    let sandbox = Sandbox::new(true);
    let result = sandbox.cleanup("/tmp/app2nix_nonexistent_xyz123");
    assert!(result.is_err(), "Cleanup of non-existent path should fail");
}

#[test]
fn test_sandbox_new_default_temp() {
    let sandbox = Sandbox::new(true);
    assert!(sandbox.is_enabled());
    // Just verify the constructor works
}

#[test]
fn test_sandbox_disabled_cleanup_is_noop() {
    let sandbox = Sandbox::new(false);
    let result = sandbox.cleanup("/tmp/some_path_that_doesnt_exist");
    assert!(result.is_ok(), "Cleanup should be a no-op when disabled");
}

// FHS compatibility tests

#[test]
fn test_fhs_disabled_returns_empty() {
    let fhs = FhsCompat::new(false);
    assert!(!fhs.is_enabled());
    let result = fhs
        .generate_fhs_env("test-app", &["zlib".into(), "glibc".into()], "bin/testapp")
        .unwrap();
    assert!(result.is_empty(), "Disabled FHS should return empty string");
}

#[test]
fn test_fhs_enabled_generates_env_expression() {
    let fhs = FhsCompat::new(true);
    assert!(fhs.is_enabled());
    let result = fhs
        .generate_fhs_env("my-app", &["zlib".into(), "glibc".into()], "bin/myapp")
        .unwrap();
    assert!(!result.is_empty(), "Enabled FHS should generate code");
    assert!(result.contains("my-app"), "Should contain app name");
    assert!(
        result.contains("buildFHSUserEnv"),
        "Should use buildFHSUserEnv"
    );
    assert!(result.contains("zlib"), "Should contain zlib dep");
    assert!(result.contains("glibc"), "Should contain glibc dep");
    assert!(
        result.contains("bin/myapp"),
        "Should contain main binary path"
    );
    assert!(result.contains("FHS=1"), "Should set FHS env var");
}

#[test]
fn test_fhs_generate_env_with_empty_deps() {
    let fhs = FhsCompat::new(true);
    let result = fhs
        .generate_fhs_env("test-app", &[], "bin/testapp")
        .unwrap();
    assert!(result.contains("targetPkgs"));
    assert!(result.contains("multiPkgs"));
}

#[test]
fn test_fhs_generate_build_expression() {
    let fhs = FhsCompat::new(true);
    let result = fhs
        .generate_build_fhs_expression("my-app", &["zlib".into(), "glibc".into()])
        .unwrap();
    assert!(result.contains("my-app"), "Should contain app name");
    assert!(
        result.contains("buildFHSUserEnv"),
        "Should use buildFHSUserEnv"
    );
    assert!(result.contains("makeWrapper"), "Should use makeWrapper");
    assert!(
        result.contains("stdenv.mkDerivation"),
        "Should be a mkDerivation"
    );
}

#[test]
fn test_fhs_generate_env_multiline_deps() {
    let fhs = FhsCompat::new(true);
    let deps = vec![
        "zlib".into(),
        "glibc".into(),
        "openssl".into(),
        "libX11".into(),
    ];
    let result = fhs.generate_fhs_env("app", &deps, "bin/app").unwrap();
    for dep in &deps {
        assert!(result.contains(dep), "Should contain dep {}", dep);
    }
}

#[test]
fn test_fhs_disabled_build_expression_empty() {
    let fhs = FhsCompat::new(false);
    let result = fhs.generate_build_fhs_expression("test", &[]).unwrap();
    assert!(result.is_empty() || !result.contains("buildFHSUserEnv"));
}

#[test]
fn test_fhs_build_expression_includes_profile() {
    let fhs = FhsCompat::new(true);
    let result = fhs
        .generate_fhs_env("app", &["zlib".into()], "bin/app")
        .unwrap();
    assert!(result.contains("profile"));
    assert!(result.contains("FHS=1"));
}
