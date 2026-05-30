use crate::config::App2NixConfig;
use crate::error::*;
use crate::pipeline::*;
use crate::progress::*;
use crate::types::*;
use std::collections::HashMap;

// ── PackageFormat ──────────────────────────────────────────────────────

#[test]
fn test_package_format_display() {
    assert_eq!(PackageFormat::Deb.to_string(), "deb");
    assert_eq!(PackageFormat::Rpm.to_string(), "rpm");
    assert_eq!(PackageFormat::AppImage.to_string(), "appimage");
    assert_eq!(PackageFormat::TarGz.to_string(), "targz");
    assert_eq!(PackageFormat::Zip.to_string(), "zip");
    assert_eq!(PackageFormat::Flatpak.to_string(), "flatpak");
    assert_eq!(PackageFormat::Snap.to_string(), "snap");
    assert_eq!(PackageFormat::ElfBinary.to_string(), "elf");
    assert_eq!(PackageFormat::Electron.to_string(), "electron");
    assert_eq!(PackageFormat::Java.to_string(), "java");
    assert_eq!(PackageFormat::NodeJs.to_string(), "nodejs");
    assert_eq!(PackageFormat::Unknown.to_string(), "unknown");
}

#[test]
fn test_package_format_equality() {
    assert_eq!(PackageFormat::Deb, PackageFormat::Deb);
    assert_ne!(PackageFormat::Deb, PackageFormat::Rpm);
    assert_eq!(PackageFormat::Unknown, PackageFormat::Unknown);
}

#[test]
fn test_package_format_serde_roundtrip() {
    let formats = vec![
        PackageFormat::Deb,
        PackageFormat::Rpm,
        PackageFormat::AppImage,
        PackageFormat::Flatpak,
        PackageFormat::Snap,
        PackageFormat::Unknown,
    ];
    for fmt in formats {
        let json = serde_json::to_string(&fmt).unwrap();
        let deserialized: PackageFormat = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized, fmt);
    }
}

// ── PackageInfo ────────────────────────────────────────────────────────

#[test]
fn test_package_info_construction() {
    let info = PackageInfo {
        name: "test-pkg".into(),
        version: Some("1.0.0".into()),
        format: PackageFormat::Deb,
        description: Some("A test package".into()),
        source_path: "/tmp/test.deb".into(),
        size: 1024,
        hash: "abc123".into(),
        architecture: Some("amd64".into()),
        maintainer: Some("author@test.com".into()),
        homepage: Some("https://test.com".into()),
    };

    assert_eq!(info.name, "test-pkg");
    assert_eq!(info.version.as_deref(), Some("1.0.0"));
    assert_eq!(info.format, PackageFormat::Deb);
    assert_eq!(info.description.as_deref(), Some("A test package"));
    assert_eq!(info.source_path, "/tmp/test.deb");
    assert_eq!(info.size, 1024);
    assert_eq!(info.hash, "abc123");
    assert_eq!(info.architecture.as_deref(), Some("amd64"));
    assert_eq!(info.maintainer.as_deref(), Some("author@test.com"));
    assert_eq!(info.homepage.as_deref(), Some("https://test.com"));
}

#[test]
fn test_package_info_minimal() {
    let info = PackageInfo {
        name: "minimal".into(),
        version: None,
        format: PackageFormat::Unknown,
        description: None,
        source_path: "".into(),
        size: 0,
        hash: "".into(),
        architecture: None,
        maintainer: None,
        homepage: None,
    };
    assert_eq!(info.name, "minimal");
    assert_eq!(info.version, None);
    assert_eq!(info.format, PackageFormat::Unknown);
    assert_eq!(info.size, 0);
}

#[test]
fn test_package_info_serde_roundtrip() {
    let info = PackageInfo {
        name: "serde-test".into(),
        version: Some("2.0.0".into()),
        format: PackageFormat::AppImage,
        description: Some("Serde roundtrip".into()),
        source_path: "/tmp/test.AppImage".into(),
        size: 9999,
        hash: "deadbeef".into(),
        architecture: Some("x86_64".into()),
        maintainer: None,
        homepage: Some("https://example.com".into()),
    };

    let json = serde_json::to_string(&info).unwrap();
    let deserialized: PackageInfo = serde_json::from_str(&json).unwrap();
    assert_eq!(deserialized.name, info.name);
    assert_eq!(deserialized.version, info.version);
    assert_eq!(deserialized.format, info.format);
    assert_eq!(deserialized.size, info.size);
    assert_eq!(deserialized.hash, info.hash);
}

// ── ExtractedFile ──────────────────────────────────────────────────────

#[test]
fn test_extracted_file() {
    let f = ExtractedFile {
        path: "/tmp/extract/bin/app".into(),
        relative_path: "bin/app".into(),
        file_type: "ELF 64-bit".into(),
        is_elf: true,
        is_executable: true,
        size: 50000,
    };
    assert!(f.is_elf);
    assert!(f.is_executable);
    assert_eq!(f.size, 50000);
    assert_eq!(f.relative_path, "bin/app");
}

// ── ElfInfo ────────────────────────────────────────────────────────────

#[test]
fn test_elf_info() {
    let elf = ElfInfo {
        path: "bin/app".into(),
        arch: "x86_64".into(),
        interpreter: Some("/lib64/ld-linux-x86-64.so.2".into()),
        needed_libs: vec!["libc.so.6".into(), "libpthread.so.0".into()],
        rpath: vec!["$ORIGIN/../lib".into()],
        is_dynamic: true,
        is_executable: true,
    };
    assert_eq!(elf.arch, "x86_64");
    assert!(elf.is_dynamic);
    assert_eq!(elf.needed_libs.len(), 2);
    assert!(elf.needed_libs.contains(&"libc.so.6".into()));
}

#[test]
fn test_elf_info_static() {
    let elf = ElfInfo {
        path: "bin/static-app".into(),
        arch: "aarch64".into(),
        interpreter: None,
        needed_libs: vec![],
        rpath: vec![],
        is_dynamic: false,
        is_executable: true,
    };
    assert!(!elf.is_dynamic);
    assert!(elf.needed_libs.is_empty());
    assert_eq!(elf.interpreter, None);
}

// ── ResolvedDependency ─────────────────────────────────────────────────

#[test]
fn test_resolved_dependency() {
    let dep = ResolvedDependency {
        library: "libc.so.6".into(),
        nix_attr: Some("glibc".into()),
        nix_package: Some("glibc".into()),
        confidence: 1.0,
        system_lib: true,
    };
    assert_eq!(dep.nix_attr.as_deref(), Some("glibc"));
    assert!(dep.system_lib);
    assert_eq!(dep.confidence, 1.0);
}

#[test]
fn test_resolved_dependency_unresolved() {
    let dep = ResolvedDependency {
        library: "libfoo.so.1".into(),
        nix_attr: None,
        nix_package: None,
        confidence: 0.0,
        system_lib: false,
    };
    assert!(dep.nix_attr.is_none());
    assert_eq!(dep.confidence, 0.0);
}

// ── AnalysisResult ─────────────────────────────────────────────────────

#[test]
fn test_analysis_result() {
    let package = PackageInfo {
        name: "test".into(),
        version: Some("1.0".into()),
        format: PackageFormat::Deb,
        description: None,
        source_path: "/tmp/test.deb".into(),
        size: 0,
        hash: "hash".into(),
        architecture: None,
        maintainer: None,
        homepage: None,
    };

    let result = AnalysisResult {
        package,
        extracted_files: vec![],
        elf_binaries: vec![],
        all_needed_libs: vec!["libc.so.6".into()],
        resolved_deps: vec![],
        unresolved_libs: vec!["libc.so.6".into()],
        main_binary: Some("bin/app".into()),
        desktop_entries: vec![],
        icons: vec![],
        app_type_hints: vec![],
    };

    assert_eq!(result.all_needed_libs.len(), 1);
    assert_eq!(result.unresolved_libs.len(), 1);
    assert_eq!(result.main_binary.as_deref(), Some("bin/app"));
}

// ── DetectedDesktopEntry ───────────────────────────────────────────────

#[test]
fn test_desktop_entry() {
    let entry = DetectedDesktopEntry {
        path: "usr/share/applications/app.desktop".into(),
        app_name: "TestApp".into(),
        exec_line: "/usr/bin/testapp".into(),
        icon_path: Some("usr/share/icons/app.png".into()),
        categories: vec!["Utility".into(), "Office".into()],
    };
    assert_eq!(entry.app_name, "TestApp");
    assert_eq!(entry.categories.len(), 2);
    assert!(entry.icon_path.is_some());
}

// ── DetectedIcon ───────────────────────────────────────────────────────

#[test]
fn test_detected_icon() {
    let icon = DetectedIcon {
        path: "usr/share/icons/app.png".into(),
        size: Some(256),
        format: "png".into(),
    };
    assert_eq!(icon.size, Some(256));
    assert_eq!(icon.format, "png");
}

#[test]
fn test_detected_icon_no_size() {
    let icon = DetectedIcon {
        path: "usr/share/icons/app.svg".into(),
        size: None,
        format: "svg".into(),
    };
    assert_eq!(icon.size, None);
}

// ── AppTypeHint ────────────────────────────────────────────────────────

#[test]
fn test_app_type_hints() {
    let hints = vec![
        AppTypeHint::Electron,
        AppTypeHint::Java(JvmInfo {
            main_class: Some("org.test.Main".into()),
            jar_files: vec!["app.jar".into()],
            jvm_version: Some("17".into()),
        }),
        AppTypeHint::NodeJs(NodeInfo {
            entry_point: Some("index.js".into()),
            has_node_modules: true,
        }),
        AppTypeHint::Python(PythonInfo {
            entry_point: Some("main.py".into()),
            requirements: vec!["requests".into()],
        }),
        AppTypeHint::Qt,
        AppTypeHint::Gtk,
        AppTypeHint::Mono,
        AppTypeHint::Wine,
        AppTypeHint::Script("python3".into()),
    ];

    assert_eq!(hints.len(), 9);
    assert!(matches!(hints[0], AppTypeHint::Electron));
    assert!(matches!(hints[1], AppTypeHint::Java(_)));
    assert!(matches!(hints[8], AppTypeHint::Script(ref s) if s == "python3"));
}

// ── GenerateOptions ────────────────────────────────────────────────────

#[test]
fn test_generate_options() {
    let opts = GenerateOptions {
        app_name: "myapp".into(),
        version: "1.0.0".into(),
        description: "My app".into(),
        format: PackageFormat::AppImage,
        main_binary: Some("myapp".into()),
        build_inputs: vec!["glibc".into()],
        native_build_inputs: vec!["autoPatchelfHook".into()],
        elf_binaries: vec![],
        all_files: vec![],
        desktop_entries: vec![],
        icons: vec![],
        app_type_hints: vec![],
        env_vars: HashMap::new(),
        use_fhs: false,
        extra_phases: vec![],
    };

    assert_eq!(opts.app_name, "myapp");
    assert_eq!(opts.version, "1.0.0");
    assert_eq!(opts.format, PackageFormat::AppImage);
    assert!(!opts.use_fhs);
    assert!(opts.build_inputs.contains(&"glibc".into()));
}

// ── InstallResult ──────────────────────────────────────────────────────

#[test]
fn test_install_result() {
    let result = InstallResult {
        app_name: "myapp".into(),
        version: "1.0.0".into(),
        derivation_path: "/nix/store/xxx.drv".into(),
        output_path: Some("/nix/store/xxx".into()),
        store_paths: vec!["/nix/store/xxx".into()],
        desktop_files: vec!["myapp.desktop".into()],
        installed: true,
        profile_name: Some("profile".into()),
    };

    assert!(result.installed);
    assert_eq!(result.store_paths.len(), 1);
    assert!(result.profile_name.is_some());
    assert!(!result.desktop_files.is_empty());
}

// ── AppEntry / AppRegistry ─────────────────────────────────────────────

#[test]
fn test_app_entry() {
    let entry = AppEntry {
        name: "myapp".into(),
        version: "1.0.0".into(),
        format: PackageFormat::Deb,
        install_path: "/nix/store/xxx".into(),
        store_path: Some("/nix/store/xxx".into()),
        desktop_file: Some("myapp.desktop".into()),
        profile: "user".into(),
        installed_at: "2025-01-01T00:00:00Z".into(),
        size: 50000000,
    };
    assert_eq!(entry.name, "myapp");
    assert_eq!(entry.format, PackageFormat::Deb);
}

#[test]
fn test_app_registry() {
    let registry = AppRegistry {
        apps: vec![
            AppEntry {
                name: "app1".into(),
                version: "1.0".into(),
                format: PackageFormat::Deb,
                install_path: "/path1".into(),
                store_path: None,
                desktop_file: None,
                profile: "user".into(),
                installed_at: "now".into(),
                size: 100,
            },
            AppEntry {
                name: "app2".into(),
                version: "2.0".into(),
                format: PackageFormat::AppImage,
                install_path: "/path2".into(),
                store_path: None,
                desktop_file: None,
                profile: "system".into(),
                installed_at: "now".into(),
                size: 200,
            },
        ],
    };
    assert_eq!(registry.apps.len(), 2);
}

// ── App2NixError ───────────────────────────────────────────────────────

#[test]
fn test_error_unsupported_format() {
    let err = App2NixError::UnsupportedFormat("snap".into());
    assert_eq!(err.to_string(), "Unsupported package format: snap");
}

#[test]
fn test_error_detection_failed() {
    let err = App2NixError::DetectionFailed("no magic bytes".into());
    assert_eq!(err.to_string(), "Detection failed: no magic bytes");
}

#[test]
fn test_error_extraction_failed() {
    let err = App2NixError::ExtractionFailed("corrupt archive".into());
    assert_eq!(err.to_string(), "Extraction failed: corrupt archive");
}

#[test]
fn test_error_analysis_failed() {
    let err = App2NixError::AnalysisFailed("unexpected format".into());
    assert_eq!(err.to_string(), "Analysis failed: unexpected format");
}

#[test]
fn test_error_resolution_failed() {
    let err = App2NixError::ResolutionFailed {
        count: 3,
        libs: "libfoo.so.1, libbar.so.2, libbaz.so.3".into(),
    };
    let msg = err.to_string();
    assert!(msg.contains("3 libraries"), "msg: {}", msg);
    assert!(msg.contains("libfoo.so.1"), "msg: {}", msg);
}

#[test]
fn test_error_patching_failed() {
    let err = App2NixError::PatchingFailed("rpath error".into());
    assert_eq!(err.to_string(), "Patching failed: rpath error");
}

#[test]
fn test_error_generation_failed() {
    let err = App2NixError::GenerationFailed("template error".into());
    assert_eq!(err.to_string(), "Nix generation failed: template error");
}

#[test]
fn test_error_build_failed() {
    let err = App2NixError::BuildFailed("nix build error".into());
    assert_eq!(err.to_string(), "Build failed: nix build error");
}

#[test]
fn test_error_install_failed() {
    let err = App2NixError::InstallFailed("profile error".into());
    assert_eq!(err.to_string(), "Installation failed: profile error");
}

#[test]
fn test_error_desktop_failed() {
    let err = App2NixError::DesktopFailed("xdg error".into());
    assert_eq!(err.to_string(), "Desktop integration failed: xdg error");
}

#[test]
fn test_error_sandbox() {
    let err = App2NixError::SandboxError("bwrap error".into());
    assert_eq!(err.to_string(), "Sandbox error: bwrap error");
}

#[test]
fn test_error_fhs() {
    let err = App2NixError::FhsError("symlink error".into());
    assert_eq!(err.to_string(), "FHS error: symlink error");
}

#[test]
fn test_error_plugin() {
    let err = App2NixError::PluginError("plugin crash".into());
    assert_eq!(err.to_string(), "Plugin error: plugin crash");
}

#[test]
fn test_error_io_conversion() {
    let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "file not found");
    let app_err: App2NixError = io_err.into();
    assert!(app_err.to_string().contains("IO error"));
    assert!(app_err.to_string().contains("file not found"));
}

#[test]
fn test_error_nix_not_found() {
    let err = App2NixError::NixNotFound("nix binary missing".into());
    assert_eq!(err.to_string(), "Nix not found: nix binary missing");
}

#[test]
fn test_error_file_not_found() {
    let err = App2NixError::FileNotFound("/tmp/test.deb".into());
    assert_eq!(err.to_string(), "File not found: /tmp/test.deb");
}

#[test]
fn test_error_invalid_input() {
    let err = App2NixError::InvalidInput("bad version string".into());
    assert_eq!(err.to_string(), "Invalid input: bad version string");
}

#[test]
fn test_error_other() {
    let err = App2NixError::Other("something went wrong".into());
    assert_eq!(err.to_string(), "something went wrong");
}

#[test]
fn test_result_type_alias() {
    let ok: Result<i32> = Ok(42);
    assert_eq!(ok.unwrap(), 42);

    let err: Result<i32> = Err(App2NixError::Other("fail".into()));
    assert!(err.is_err());
}

// ── App2NixConfig ──────────────────────────────────────────────────────

#[test]
fn test_config_default() {
    let cfg = App2NixConfig::default();
    assert_eq!(cfg.nix_binary, "nix");
    assert!(cfg.use_flakes);
    assert!(cfg.auto_install);
    assert!(cfg.auto_desktop);
    assert!(!cfg.keep_build);
    assert!(!cfg.verbose);
    assert_eq!(cfg.max_parallel, 4);
    assert_eq!(cfg.timeout_seconds, 600);
}

#[test]
fn test_config_builder_verbose() {
    let cfg = App2NixConfig::default().with_verbose(true);
    assert!(cfg.verbose);
}

#[test]
fn test_config_builder_keep_build() {
    let cfg = App2NixConfig::default().with_keep_build(true);
    assert!(cfg.keep_build);
}

#[test]
fn test_config_builder_no_install() {
    let cfg = App2NixConfig::default().with_no_install();
    assert!(!cfg.auto_install);
}

#[test]
fn test_config_builder_chaining() {
    let cfg = App2NixConfig::default()
        .with_verbose(true)
        .with_keep_build(true)
        .with_no_install();
    assert!(cfg.verbose);
    assert!(cfg.keep_build);
    assert!(!cfg.auto_install);
}

#[test]
fn test_config_paths() {
    let cfg = App2NixConfig::default();
    assert!(cfg
        .cache_db_path()
        .to_string_lossy()
        .ends_with("resolver.db"));
    assert!(cfg
        .registry_path()
        .to_string_lossy()
        .ends_with("registry.json"));
    assert!(cfg.builds_dir().to_string_lossy().contains("app2nix-build"));
}

// ── ProgressTracker ────────────────────────────────────────────────────

#[test]
fn test_progress_construction() {
    let tracker = ProgressTracker::new(vec!["Detect", "Extract", "Analyze", "Generate"]);
    assert_eq!(tracker.total_steps, 4);
    assert_eq!(tracker.steps.len(), 4);
    assert_eq!(
        tracker
            .current_step
            .load(std::sync::atomic::Ordering::SeqCst),
        0
    );
}

#[test]
fn test_progress_advance() {
    let mut tracker = ProgressTracker::new(vec!["Step1", "Step2"]);
    let idx1 = tracker.advance();
    assert_eq!(idx1, 0);
    let idx2 = tracker.advance();
    assert_eq!(idx2, 1);
    // Advancing beyond should not panic
    let idx3 = tracker.advance();
    assert!(idx3 > 1);
}

#[test]
fn test_progress_complete_step() {
    let mut tracker = ProgressTracker::new(vec!["Step1"]);
    let idx = tracker.advance();
    tracker.complete_step(idx);
    assert!(matches!(tracker.steps[idx].status, StepStatus::Completed));
}

#[test]
fn test_progress_fail_step() {
    let mut tracker = ProgressTracker::new(vec!["Step1"]);
    let idx = tracker.advance();
    tracker.fail_step(idx, "Something went wrong".into());
    assert!(
        matches!(&tracker.steps[idx].status, StepStatus::Failed(msg) if msg == "Something went wrong")
    );
}

#[test]
fn test_progress_complete_out_of_range() {
    let mut tracker = ProgressTracker::new(vec!["Step1"]);
    // Should not panic
    tracker.complete_step(99);
    tracker.fail_step(99, "msg".into());
}

#[test]
fn test_progress_empty_steps() {
    let mut tracker = ProgressTracker::new(vec![]);
    assert_eq!(tracker.total_steps, 0);
    let idx = tracker.advance();
    tracker.complete_step(idx);
}

// ── Pipeline ───────────────────────────────────────────────────────────

/// Minimal mock detector for testing Pipeline construction.
struct MockDetector;
impl Detector for MockDetector {
    fn detect(&self, _path: &str) -> Result<PackageInfo> {
        Ok(PackageInfo {
            name: "mock".into(),
            version: Some("1.0".into()),
            format: PackageFormat::Deb,
            description: None,
            source_path: _path.into(),
            size: 0,
            hash: "mock".into(),
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
                description: None,
                source_path: String::new(),
                size: 0,
                hash: String::new(),
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

struct MockGenerator;
impl NixGenerator for MockGenerator {
    fn generate(&self, _opts: &GenerateOptions, _output_dir: &str) -> Result<String> {
        Ok("/nix/store/mock.drv".into())
    }
}

struct MockInstaller;
impl Installer for MockInstaller {
    fn build(&self, _derivation_path: &str, _output_dir: &str) -> Result<String> {
        Ok("/nix/store/mock".into())
    }
    fn install(&self, _store_path: &str, _name: &str) -> Result<String> {
        Ok("profile".into())
    }
    fn uninstall(&self, _name: &str) -> Result<()> {
        Ok(())
    }
    fn list_installed(&self) -> Result<Vec<AppEntry>> {
        Ok(vec![])
    }
}

struct MockDesktop;
impl DesktopIntegrator for MockDesktop {
    fn register(
        &self,
        _app_name: &str,
        _exec_path: &str,
        _entries: &[DetectedDesktopEntry],
        _icons: &[DetectedIcon],
    ) -> Result<Vec<String>> {
        Ok(vec![])
    }
    fn unregister(&self, _app_name: &str) -> Result<()> {
        Ok(())
    }
}

#[test]
fn test_pipeline_construction() {
    let _pipeline = Pipeline::new(
        Box::new(MockDetector),
        Box::new(MockExtractor),
        Box::new(MockAnalyzer),
        Box::new(MockPatcher),
        Box::new(MockGenerator),
        Box::new(MockInstaller),
        Box::new(MockDesktop),
    );
}

#[test]
fn test_pipeline_run_with_mocks() {
    let pipeline = Pipeline::new(
        Box::new(MockDetector),
        Box::new(MockExtractor),
        Box::new(MockAnalyzer),
        Box::new(MockPatcher),
        Box::new(MockGenerator),
        Box::new(MockInstaller),
        Box::new(MockDesktop),
    );

    let result = pipeline.run("/tmp/test.deb", "/tmp/work").unwrap();
    assert_eq!(result.app_name, "mock");
    assert_eq!(result.version, "1.0");
    assert!(result.installed);
    assert_eq!(result.derivation_path, "/nix/store/mock.drv");
}

#[test]
fn test_pipeline_run_error_propagation() {
    struct FailingDetector;
    impl Detector for FailingDetector {
        fn detect(&self, _path: &str) -> Result<PackageInfo> {
            Err(App2NixError::DetectionFailed("mock failure".into()))
        }
    }

    let pipeline = Pipeline::new(
        Box::new(FailingDetector),
        Box::new(MockExtractor),
        Box::new(MockAnalyzer),
        Box::new(MockPatcher),
        Box::new(MockGenerator),
        Box::new(MockInstaller),
        Box::new(MockDesktop),
    );

    let err = pipeline.run("/tmp/test.deb", "/tmp/work").unwrap_err();
    assert!(matches!(err, App2NixError::DetectionFailed(ref msg) if msg == "mock failure"));
}
