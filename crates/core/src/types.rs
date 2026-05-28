use std::collections::HashMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum PackageFormat {
    Deb,
    Rpm,
    AppImage,
    TarGz,
    Zip,
    Flatpak,
    Snap,
    ElfBinary,
    Electron,
    Java,
    NodeJs,
    Unknown,
}

impl std::fmt::Display for PackageFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PackageFormat::Deb => write!(f, "deb"),
            PackageFormat::Rpm => write!(f, "rpm"),
            PackageFormat::AppImage => write!(f, "appimage"),
            PackageFormat::TarGz => write!(f, "targz"),
            PackageFormat::Zip => write!(f, "zip"),
            PackageFormat::Flatpak => write!(f, "flatpak"),
            PackageFormat::Snap => write!(f, "snap"),
            PackageFormat::ElfBinary => write!(f, "elf"),
            PackageFormat::Electron => write!(f, "electron"),
            PackageFormat::Java => write!(f, "java"),
            PackageFormat::NodeJs => write!(f, "nodejs"),
            PackageFormat::Unknown => write!(f, "unknown"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackageInfo {
    pub name: String,
    pub version: Option<String>,
    pub format: PackageFormat,
    pub description: Option<String>,
    pub source_path: String,
    pub size: u64,
    pub hash: String,
    pub architecture: Option<String>,
    pub maintainer: Option<String>,
    pub homepage: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedFile {
    pub path: String,
    pub relative_path: String,
    pub file_type: String,
    pub is_elf: bool,
    pub is_executable: bool,
    pub size: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ElfInfo {
    pub path: String,
    pub arch: String,
    pub interpreter: Option<String>,
    pub needed_libs: Vec<String>,
    pub rpath: Vec<String>,
    pub is_dynamic: bool,
    pub is_executable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResolvedDependency {
    pub library: String,
    pub nix_attr: Option<String>,
    pub nix_package: Option<String>,
    pub confidence: f64,
    pub system_lib: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisResult {
    pub package: PackageInfo,
    pub extracted_files: Vec<ExtractedFile>,
    pub elf_binaries: Vec<ElfInfo>,
    pub all_needed_libs: Vec<String>,
    pub resolved_deps: Vec<ResolvedDependency>,
    pub unresolved_libs: Vec<String>,
    pub main_binary: Option<String>,
    pub desktop_entries: Vec<DetectedDesktopEntry>,
    pub icons: Vec<DetectedIcon>,
    pub app_type_hints: Vec<AppTypeHint>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectedDesktopEntry {
    pub path: String,
    pub app_name: String,
    pub exec_line: String,
    pub icon_path: Option<String>,
    pub categories: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectedIcon {
    pub path: String,
    pub size: Option<u32>,
    pub format: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AppTypeHint {
    Electron,
    Java(JvmInfo),
    NodeJs(NodeInfo),
    Python(PythonInfo),
    Qt,
    Gtk,
    Mono,
    Wine,
    Script(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JvmInfo {
    pub main_class: Option<String>,
    pub jar_files: Vec<String>,
    pub jvm_version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeInfo {
    pub entry_point: Option<String>,
    pub has_node_modules: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PythonInfo {
    pub entry_point: Option<String>,
    pub requirements: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenerateOptions {
    pub app_name: String,
    pub version: String,
    pub description: String,
    pub format: PackageFormat,
    pub main_binary: Option<String>,
    pub build_inputs: Vec<String>,
    pub native_build_inputs: Vec<String>,
    pub elf_binaries: Vec<ElfInfo>,
    pub all_files: Vec<ExtractedFile>,
    pub desktop_entries: Vec<DetectedDesktopEntry>,
    pub icons: Vec<DetectedIcon>,
    pub app_type_hints: Vec<AppTypeHint>,
    pub env_vars: HashMap<String, String>,
    pub use_fhs: bool,
    pub extra_phases: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstallResult {
    pub app_name: String,
    pub version: String,
    pub derivation_path: String,
    pub output_path: Option<String>,
    pub store_paths: Vec<String>,
    pub desktop_files: Vec<String>,
    pub installed: bool,
    pub profile_name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppEntry {
    pub name: String,
    pub version: String,
    pub format: PackageFormat,
    pub install_path: String,
    pub store_path: Option<String>,
    pub desktop_file: Option<String>,
    pub profile: String,
    pub installed_at: String,
    pub size: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppRegistry {
    pub apps: Vec<AppEntry>,
}
