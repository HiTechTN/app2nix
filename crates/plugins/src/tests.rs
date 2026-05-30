use crate::{PipelineBuilder, PluginManager};
use app2nix_core::{
    pipeline::Pipeline, AnalysisResult, Analyzer, App2NixError, AppTypeHint, DesktopIntegrator,
    DetectedDesktopEntry, DetectedIcon, Detector, ElfInfo, ExtractedFile, Extractor,
    GenerateOptions, Installer, NixGenerator, PackageFormat, PackageInfo, Patcher, Plugin,
    ResolvedDependency, Result,
};
use std::collections::HashMap;

/// A mock Plugin for testing
struct MockPlugin;

impl Plugin for MockPlugin {
    fn name(&self) -> &'static str {
        "mock-plugin"
    }
    fn detect_format(&self, path: &str) -> Option<PackageFormat> {
        if path.ends_with(".mock") {
            Some(PackageFormat::Unknown)
        } else {
            None
        }
    }
    fn analyze(&self, _path: &str) -> Result<Option<AnalysisResult>> {
        Ok(None)
    }
}

/// Another mock plugin for testing multiple plugins
struct MockAppImagePlugin;

impl Plugin for MockAppImagePlugin {
    fn name(&self) -> &'static str {
        "appimage-plugin"
    }
    fn detect_format(&self, path: &str) -> Option<PackageFormat> {
        if path.ends_with(".AppImage") {
            Some(PackageFormat::AppImage)
        } else {
            None
        }
    }
    fn analyze(&self, _path: &str) -> Result<Option<AnalysisResult>> {
        Ok(None)
    }
}

struct MockDetector;
impl Detector for MockDetector {
    fn detect(&self, _path: &str) -> Result<PackageInfo> {
        Ok(PackageInfo {
            name: "mock".into(),
            version: Some("1.0".into()),
            format: PackageFormat::Deb,
            description: None,
            source_path: "/mock.deb".into(),
            size: 0,
            hash: "hash".into(),
            architecture: None,
            maintainer: None,
            homepage: None,
        })
    }
}

struct MockExtractor;
impl Extractor for MockExtractor {
    fn extract(&self, _package: &PackageInfo, _dest: &str) -> Result<Vec<ExtractedFile>> {
        Ok(vec![])
    }
}

struct MockAnalyzer;
impl Analyzer for MockAnalyzer {
    fn analyze(&self, _package: &PackageInfo, _files: &[ExtractedFile]) -> Result<AnalysisResult> {
        Ok(AnalysisResult {
            package: PackageInfo {
                name: "mock".into(),
                version: Some("1.0".into()),
                format: PackageFormat::Deb,
                description: Some("mock".into()),
                source_path: "/mock.deb".into(),
                size: 0,
                hash: "hash".into(),
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
        })
    }
    fn resolve_deps(&self, _needed: &[String]) -> Result<Vec<ResolvedDependency>> {
        Ok(vec![])
    }
}

struct MockPatcher;
impl Patcher for MockPatcher {
    fn patch_binaries(
        &self,
        _target_dir: &str,
        _analysis: &AnalysisResult,
        _resolved_deps: &[ResolvedDependency],
    ) -> Result<()> {
        Ok(())
    }
}

struct MockNixGenerator;
impl NixGenerator for MockNixGenerator {
    fn generate(&self, _opts: &GenerateOptions, _output_dir: &str) -> Result<String> {
        Ok("/tmp/derivation.nix".into())
    }
}

struct MockInstaller;
impl Installer for MockInstaller {
    fn build(&self, _derivation_path: &str, _output_dir: &str) -> Result<String> {
        Ok("/nix/store/xxx".into())
    }
    fn install(&self, _store_path: &str, _name: &str) -> Result<String> {
        Ok("app2nix-mock".into())
    }
    fn uninstall(&self, _name: &str) -> Result<()> {
        Ok(())
    }
    fn list_installed(&self) -> Result<Vec<app2nix_core::AppEntry>> {
        Ok(vec![])
    }
}

struct MockDesktopIntegrator;
impl DesktopIntegrator for MockDesktopIntegrator {
    fn register(
        &self,
        _app_name: &str,
        _exec_path: &str,
        _entries: &[DetectedDesktopEntry],
        _icons: &[DetectedIcon],
    ) -> Result<Vec<String>> {
        Ok(vec!["/tmp/mock.desktop".into()])
    }
    fn unregister(&self, _app_name: &str) -> Result<()> {
        Ok(())
    }
}

#[test]
fn test_plugin_manager_new() {
    let pm = PluginManager::new();
    assert_eq!(pm.plugin_count(), 0);
    assert!(pm.list_plugins().is_empty());
}

#[test]
fn test_plugin_manager_register_and_count() {
    let mut pm = PluginManager::new();
    pm.register(Box::new(MockPlugin));
    assert_eq!(pm.plugin_count(), 1);
    pm.register(Box::new(MockAppImagePlugin));
    assert_eq!(pm.plugin_count(), 2);
}

#[test]
fn test_plugin_manager_list_plugins() {
    let mut pm = PluginManager::new();
    pm.register(Box::new(MockPlugin));
    pm.register(Box::new(MockAppImagePlugin));
    let plugins = pm.list_plugins();
    assert_eq!(plugins.len(), 2);
    assert!(plugins.contains(&"mock-plugin"));
    assert!(plugins.contains(&"appimage-plugin"));
}

#[test]
fn test_plugin_manager_detect_format() {
    let mut pm = PluginManager::new();
    pm.register(Box::new(MockPlugin));
    assert_eq!(pm.detect_format("file.mock"), Some(PackageFormat::Unknown));
    assert_eq!(pm.detect_format("file.deb"), None);
}

#[test]
fn test_plugin_manager_detect_format_multiple_plugins() {
    let mut pm = PluginManager::new();
    pm.register(Box::new(MockPlugin));
    pm.register(Box::new(MockAppImagePlugin));
    assert_eq!(
        pm.detect_format("test.AppImage"),
        Some(PackageFormat::AppImage)
    );
    assert_eq!(pm.detect_format("test.mock"), Some(PackageFormat::Unknown));
}

#[test]
fn test_plugin_manager_analyze_returns_none() {
    let mut pm = PluginManager::new();
    pm.register(Box::new(MockPlugin));
    let result = pm.analyze("test.file").unwrap();
    assert!(result.is_none());
}

#[test]
fn test_pipeline_builder_new() {
    let builder = PipelineBuilder::new();
    // Just verify it constructs
}

#[test]
fn test_pipeline_builder_build_with_all_components() {
    let pipeline = PipelineBuilder::new()
        .with_detector(Box::new(MockDetector))
        .with_extractor(Box::new(MockExtractor))
        .with_analyzer(Box::new(MockAnalyzer))
        .with_patcher(Box::new(MockPatcher))
        .with_generator(Box::new(MockNixGenerator))
        .with_installer(Box::new(MockInstaller))
        .with_desktop(Box::new(MockDesktopIntegrator))
        .build();
    assert!(
        pipeline.is_ok(),
        "PipelineBuilder should build with all components"
    );
}

#[test]
fn test_pipeline_builder_build_missing_detector() {
    let result = PipelineBuilder::new()
        .with_extractor(Box::new(MockExtractor))
        .with_analyzer(Box::new(MockAnalyzer))
        .with_patcher(Box::new(MockPatcher))
        .with_generator(Box::new(MockNixGenerator))
        .with_installer(Box::new(MockInstaller))
        .with_desktop(Box::new(MockDesktopIntegrator))
        .build();
    assert!(result.is_err(), "Should fail when detector is missing");
}

#[test]
fn test_pipeline_builder_register_plugin() {
    let mut builder = PipelineBuilder::new();
    builder.register_plugin(Box::new(MockPlugin));
    // Just verify it doesn't panic
}

#[test]
fn test_pipeline_mock_run() {
    let pipeline = PipelineBuilder::new()
        .with_detector(Box::new(MockDetector))
        .with_extractor(Box::new(MockExtractor))
        .with_analyzer(Box::new(MockAnalyzer))
        .with_patcher(Box::new(MockPatcher))
        .with_generator(Box::new(MockNixGenerator))
        .with_installer(Box::new(MockInstaller))
        .with_desktop(Box::new(MockDesktopIntegrator))
        .build()
        .unwrap();

    let result = pipeline.run("/mock.deb", "/tmp/work");
    assert!(result.is_ok(), "Mock pipeline run should succeed");
    let install = result.unwrap();
    assert_eq!(install.app_name, "mock");
    assert_eq!(install.version, "1.0");
    assert!(install.installed);
    assert_eq!(install.desktop_files, vec!["/tmp/mock.desktop"]);
}
