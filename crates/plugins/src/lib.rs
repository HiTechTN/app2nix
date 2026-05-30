#[cfg(test)]
mod tests;

use app2nix_core::{
    AnalysisResult, Analyzer, App2NixError, DesktopIntegrator, Detector, Extractor, Installer,
    NixGenerator, PackageFormat, Patcher, Plugin, Result,
};

#[derive(Default)]
pub struct PluginManager {
    plugins: Vec<Box<dyn Plugin>>,
}

impl PluginManager {
    /// Create an empty `PluginManager`.
    ///
    /// # Examples
    ///
    /// ```
    /// use app2nix_plugins::PluginManager;
    ///
    /// let mgr = PluginManager::new();
    /// assert_eq!(mgr.plugin_count(), 0);
    /// ```
    pub fn new() -> Self {
        Self {
            plugins: Vec::new(),
        }
    }

    /// Register a plugin.
    ///
    /// # Examples
    ///
    /// ```
    /// use app2nix_plugins::PluginManager;
    /// use app2nix_core::{Plugin, PackageFormat, AnalysisResult, Result};
    ///
    /// struct MyPlugin;
    /// impl Plugin for MyPlugin {
    ///     fn name(&self) -> &'static str { "my-plugin" }
    ///     fn detect_format(&self, _path: &str) -> Option<PackageFormat> { None }
    ///     fn analyze(&self, _path: &str) -> Result<Option<AnalysisResult>> { Ok(None) }
    /// }
    ///
    /// let mut mgr = PluginManager::new();
    /// mgr.register(Box::new(MyPlugin));
    /// assert_eq!(mgr.plugin_count(), 1);
    /// ```
    pub fn register(&mut self, plugin: Box<dyn Plugin>) {
        self.plugins.push(plugin);
    }

    pub fn detect_format(&self, path: &str) -> Option<PackageFormat> {
        for plugin in &self.plugins {
            if let Some(format) = plugin.detect_format(path) {
                return Some(format);
            }
        }
        None
    }

    pub fn analyze(&self, path: &str) -> Result<Option<AnalysisResult>> {
        for plugin in &self.plugins {
            if let Some(result) = plugin.analyze(path)? {
                return Ok(Some(result));
            }
        }
        Ok(None)
    }

    pub fn list_plugins(&self) -> Vec<&'static str> {
        self.plugins.iter().map(|p| p.name()).collect()
    }

    /// Return the number of registered plugins.
    ///
    /// # Examples
    ///
    /// ```
    /// use app2nix_plugins::PluginManager;
    ///
    /// let mgr = PluginManager::new();
    /// assert_eq!(mgr.plugin_count(), 0);
    /// ```
    pub fn plugin_count(&self) -> usize {
        self.plugins.len()
    }
}

#[derive(Default)]
pub struct PipelineBuilder {
    detector: Option<Box<dyn Detector>>,
    extractor: Option<Box<dyn Extractor>>,
    analyzer: Option<Box<dyn Analyzer>>,
    patcher: Option<Box<dyn Patcher>>,
    generator: Option<Box<dyn NixGenerator>>,
    installer: Option<Box<dyn Installer>>,
    desktop: Option<Box<dyn DesktopIntegrator>>,
    plugin_manager: PluginManager,
}

impl PipelineBuilder {
    pub fn new() -> Self {
        Self {
            detector: None,
            extractor: None,
            analyzer: None,
            patcher: None,
            generator: None,
            installer: None,
            desktop: None,
            plugin_manager: PluginManager::new(),
        }
    }

    pub fn with_detector(mut self, d: Box<dyn Detector>) -> Self {
        self.detector = Some(d);
        self
    }

    pub fn with_extractor(mut self, e: Box<dyn Extractor>) -> Self {
        self.extractor = Some(e);
        self
    }

    pub fn with_analyzer(mut self, a: Box<dyn Analyzer>) -> Self {
        self.analyzer = Some(a);
        self
    }

    pub fn with_patcher(mut self, p: Box<dyn Patcher>) -> Self {
        self.patcher = Some(p);
        self
    }

    pub fn with_generator(mut self, g: Box<dyn NixGenerator>) -> Self {
        self.generator = Some(g);
        self
    }

    pub fn with_installer(mut self, i: Box<dyn Installer>) -> Self {
        self.installer = Some(i);
        self
    }

    pub fn with_desktop(mut self, d: Box<dyn DesktopIntegrator>) -> Self {
        self.desktop = Some(d);
        self
    }

    pub fn register_plugin(&mut self, plugin: Box<dyn Plugin>) {
        self.plugin_manager.register(plugin);
    }

    pub fn build(self) -> Result<Pipeline> {
        Ok(Pipeline::new(
            self.detector
                .ok_or_else(|| App2NixError::PluginError("Detector not set".into()))?,
            self.extractor
                .ok_or_else(|| App2NixError::PluginError("Extractor not set".into()))?,
            self.analyzer
                .ok_or_else(|| App2NixError::PluginError("Analyzer not set".into()))?,
            self.patcher
                .ok_or_else(|| App2NixError::PluginError("Patcher not set".into()))?,
            self.generator
                .ok_or_else(|| App2NixError::PluginError("Generator not set".into()))?,
            self.installer
                .ok_or_else(|| App2NixError::PluginError("Installer not set".into()))?,
            self.desktop
                .ok_or_else(|| App2NixError::PluginError("Desktop integrator not set".into()))?,
        ))
    }
}

use app2nix_core::pipeline::Pipeline;
