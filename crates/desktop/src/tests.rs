use crate::sanitize_desktop_name;

#[test]
fn test_sanitize_desktop_name_lowercase() {
    assert_eq!(sanitize_desktop_name("Firefox"), "firefox");
}

#[test]
fn test_sanitize_desktop_name_replaces_spaces() {
    assert_eq!(sanitize_desktop_name("VS Code"), "vs-code");
}

#[test]
fn test_sanitize_desktop_name_replaces_special_chars() {
    assert_eq!(sanitize_desktop_name("App@2.0!"), "app-2-0");
}

#[test]
fn test_sanitize_desktop_name_allows_hyphens() {
    assert_eq!(sanitize_desktop_name("my-app-name"), "my-app-name");
}

#[test]
fn test_sanitize_desktop_name_trims_dashes() {
    assert_eq!(sanitize_desktop_name("-my-app-"), "my-app");
}

#[test]
fn test_sanitize_desktop_name_empty() {
    assert_eq!(sanitize_desktop_name(""), "");
}

#[test]
fn test_sanitize_desktop_name_only_special() {
    assert_eq!(sanitize_desktop_name("@#$%"), "");
}

#[test]
fn test_sanitize_desktop_name_keeps_alphanumeric() {
    assert_eq!(sanitize_desktop_name("App123"), "app123");
}
