use crate::{DependencyResolver, levenshtein_distance};

#[test]
fn test_levenshtein_identical() {
    assert_eq!(levenshtein_distance("hello", "hello"), 0);
}

#[test]
fn test_levenshtein_empty_strings() {
    assert_eq!(levenshtein_distance("", ""), 0);
}

#[test]
fn test_levenshtein_one_empty() {
    assert_eq!(levenshtein_distance("abc", ""), 3);
    assert_eq!(levenshtein_distance("", "xyz"), 3);
}

#[test]
fn test_levenshtein_one_substitution() {
    assert_eq!(levenshtein_distance("cat", "car"), 1);
}

#[test]
fn test_levenshtein_one_insertion() {
    assert_eq!(levenshtein_distance("cat", "cats"), 1);
}

#[test]
fn test_levenshtein_one_deletion() {
    assert_eq!(levenshtein_distance("cats", "cat"), 1);
}

#[test]
fn test_levenshtein_completely_different() {
    assert_eq!(levenshtein_distance("abc", "xyz"), 3);
}

#[test]
fn test_clean_lib_name_removes_lib_prefix() {
    assert_eq!(DependencyResolver::clean_lib_name("libfoo.so.1"), "foo");
}

#[test]
fn test_clean_lib_name_removes_version_suffix() {
    // '3' is part of the library name "ssl3" (OpenSSL 3.x), not a version suffix
    assert_eq!(DependencyResolver::clean_lib_name("libssl3.so"), "ssl3");
}

#[test]
fn test_clean_lib_name_removes_so_suffix() {
    assert_eq!(DependencyResolver::clean_lib_name("libz.so"), "z");
}

#[test]
fn test_clean_lib_name_dot_and_dash_cleaned() {
    let cleaned = DependencyResolver::clean_lib_name("libdbus-1.so.3");
    assert_eq!(cleaned, "dbus", "Should strip lib-, -1, .so, .3 -> 'dbus'");
}

#[test]
fn test_clean_lib_name_lowercased() {
    assert_eq!(DependencyResolver::clean_lib_name("libGL.so.1"), "gl");
}

#[test]
fn test_clean_lib_name_no_prefix() {
    assert_eq!(DependencyResolver::clean_lib_name("X11.so.6"), "x11");
}

#[test]
fn test_resolve_known_lib() {
    let resolver = DependencyResolver::new();
    let result = resolver.resolve("libz.so.1");
    assert_eq!(result, Some(("zlib".to_string(), "zlib".to_string())));
}

#[test]
fn test_resolve_glibc_lib() {
    let resolver = DependencyResolver::new();
    assert_eq!(resolver.resolve("libpthread.so.0"), Some(("glibc".to_string(), "glibc".to_string())));
    assert_eq!(resolver.resolve("libm.so.6"), Some(("glibc".to_string(), "glibc".to_string())));
    assert_eq!(resolver.resolve("libdl.so.2"), Some(("glibc".to_string(), "glibc".to_string())));
}

#[test]
fn test_resolve_unknown_lib() {
    let resolver = DependencyResolver::new();
    let result = resolver.resolve("libtotally_unknown_lib.so.1");
    assert_eq!(result, None);
}

#[test]
fn test_resolve_x11() {
    let resolver = DependencyResolver::new();
    assert_eq!(resolver.resolve("libX11.so.6"), Some(("xorg.libX11".to_string(), "libX11".to_string())));
}

#[test]
fn test_resolve_qt5() {
    let resolver = DependencyResolver::new();
    assert_eq!(resolver.resolve("libQt5Core.so.5"), Some(("qt5.qtbase".to_string(), "qt5".to_string())));
}

#[test]
fn test_resolve_qt6() {
    let resolver = DependencyResolver::new();
    assert_eq!(resolver.resolve("libQt6Widgets.so.6"), Some(("qt6.qtbase".to_string(), "qt6".to_string())));
}

#[test]
fn test_resolve_all_mixed() {
    let resolver = DependencyResolver::new();
    let libs = vec!["libz.so.1".to_string(), "libQt5Core.so.5".to_string(), "libunknown_xyz.so".to_string()];
    let results = resolver.resolve_all(&libs);
    assert_eq!(results.len(), 3);
    assert!(results[0].system_lib);
    assert_eq!(results[0].nix_attr.as_deref(), Some("zlib"));
    assert!(results[2].nix_attr.is_none());
    assert_eq!(results[2].confidence, 0.2);
    assert!(!results[2].system_lib);
}

#[test]
fn test_resolve_caches_fuzzy_result() {
    let resolver = DependencyResolver::new();
    let _ = resolver.resolve("libsndfille.so.1"); // close to "sndfile"
    let result = resolver.resolve("libsndfille.so.1");
    assert_eq!(result, Some(("libsndfile".to_string(), "libsndfile".to_string())));
}

#[test]
fn test_build_dep_map_has_essential_entries() {
    use std::collections::HashMap;
    let m = crate::build_dep_map();
    assert!(m.contains_key("c"));
    assert!(m.contains_key("z"));
    assert!(m.contains_key("gl"));
    assert!(m.contains_key("ssl"));
    assert!(m.contains_key("pthread"));
    assert!(m.contains_key("gtk"));
    assert_eq!(m.get("c").unwrap(), &("glibc".to_string(), "glibc".to_string()));
    assert_eq!(m.get("z").unwrap(), &("zlib".to_string(), "zlib".to_string()));
}

#[test]
fn test_dep_map_size_is_reasonable() {
    let m = crate::build_dep_map();
    assert!(m.len() > 50, "Should have at least 50 known library mappings");
    assert!(m.len() < 200, "Should not have more than 200 entries");
}
