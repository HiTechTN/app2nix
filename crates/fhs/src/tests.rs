use crate::FhsCompat;

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
