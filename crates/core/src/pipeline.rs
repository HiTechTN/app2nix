use crate::types::*;
use crate::error::Result;

pub trait Detector: Send + Sync {
    fn detect(&self, path: &str) -> Result<PackageInfo>;
}

pub trait Extractor: Send + Sync {
    fn extract(&self, package: &PackageInfo, dest: &str) -> Result<Vec<ExtractedFile>>;
}

pub trait Analyzer: Send + Sync {
    fn analyze(&self, package: &PackageInfo, files: &[ExtractedFile]) -> Result<AnalysisResult>;
    fn resolve_deps(&self, needed: &[String]) -> Result<Vec<ResolvedDependency>>;
}

pub trait Patcher: Send + Sync {
    fn patch_binaries(
        &self,
        target_dir: &str,
        analysis: &AnalysisResult,
        resolved_deps: &[ResolvedDependency],
    ) -> Result<()>;
}

pub trait NixGenerator: Send + Sync {
    fn generate(&self, opts: &GenerateOptions, output_dir: &str) -> Result<String>;
}

pub trait Installer: Send + Sync {
    fn build(&self, derivation_path: &str, output_dir: &str) -> Result<String>;
    fn install(&self, store_path: &str, name: &str) -> Result<String>;
    fn uninstall(&self, name: &str) -> Result<()>;
    fn list_installed(&self) -> Result<Vec<AppEntry>>;
}

pub trait DesktopIntegrator: Send + Sync {
    fn register(
        &self,
        app_name: &str,
        exec_path: &str,
        entries: &[DetectedDesktopEntry],
        icons: &[DetectedIcon],
    ) -> Result<Vec<String>>;
    fn unregister(&self, app_name: &str) -> Result<()>;
}

pub trait Plugin: Send + Sync {
    fn name(&self) -> &'static str;
    fn detect_format(&self, path: &str) -> Option<PackageFormat>;
    fn analyze(&self, path: &str) -> Result<Option<AnalysisResult>>;
}

pub struct Pipeline {
    pub detector: Box<dyn Detector>,
    pub extractor: Box<dyn Extractor>,
    pub analyzer: Box<dyn Analyzer>,
    pub patcher: Box<dyn Patcher>,
    pub generator: Box<dyn NixGenerator>,
    pub installer: Box<dyn Installer>,
    pub desktop: Box<dyn DesktopIntegrator>,
}

impl Pipeline {
    pub fn new(
        detector: Box<dyn Detector>,
        extractor: Box<dyn Extractor>,
        analyzer: Box<dyn Analyzer>,
        patcher: Box<dyn Patcher>,
        generator: Box<dyn NixGenerator>,
        installer: Box<dyn Installer>,
        desktop: Box<dyn DesktopIntegrator>,
    ) -> Self {
        Self {
            detector,
            extractor,
            analyzer,
            patcher,
            generator,
            installer,
            desktop,
        }
    }

    pub fn run(&self, source_path: &str, work_dir: &str) -> Result<InstallResult> {
        let package = self.detector.detect(source_path)?;
        let extracted = self.extractor.extract(&package, work_dir)?;
        let analysis = self.analyzer.analyze(&package, &extracted)?;

        let opts = GenerateOptions {
            app_name: package.name.clone(),
            version: package.version.clone().unwrap_or_else(|| "1.0.0".into()),
            description: package.description.clone().unwrap_or_default(),
            format: package.format,
            main_binary: analysis.main_binary.clone(),
            build_inputs: analysis
                .resolved_deps
                .iter()
                .filter_map(|d| d.nix_attr.clone())
                .collect(),
            native_build_inputs: vec!["autoPatchelfHook".into()],
            elf_binaries: analysis.elf_binaries.clone(),
            all_files: analysis.extracted_files.clone(),
            desktop_entries: analysis.desktop_entries.clone(),
            icons: analysis.icons.clone(),
            app_type_hints: analysis.app_type_hints.clone(),
            env_vars: std::collections::HashMap::new(),
            use_fhs: false,
            extra_phases: Vec::new(),
        };

        self.patcher
            .patch_binaries(work_dir, &analysis, &analysis.resolved_deps)?;

        let derivation_path = self.generator.generate(&opts, work_dir)?;

        let store_path = self.installer.build(&derivation_path, work_dir)?;
        let profile_name = self.installer.install(&store_path, &package.name)?;

        let desktop_files = self.desktop.register(
            &package.name,
            &store_path,
            &analysis.desktop_entries,
            &analysis.icons,
        )?;

        Ok(InstallResult {
            app_name: package.name,
            version: package.version.unwrap_or_else(|| "1.0.0".into()),
            derivation_path,
            output_path: Some(store_path.clone()),
            store_paths: vec![store_path],
            desktop_files,
            installed: true,
            profile_name: Some(profile_name),
        })
    }
}
