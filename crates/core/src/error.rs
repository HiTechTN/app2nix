use thiserror::Error;

#[derive(Error, Debug)]
pub enum App2NixError {
    #[error("Unsupported package format: {0}")]
    UnsupportedFormat(String),

    #[error("Detection failed: {0}")]
    DetectionFailed(String),

    #[error("Extraction failed: {0}")]
    ExtractionFailed(String),

    #[error("Analysis failed: {0}")]
    AnalysisFailed(String),

    #[error("Resolution failed for {count} libraries: {libs}")]
    ResolutionFailed { count: usize, libs: String },

    #[error("Patching failed: {0}")]
    PatchingFailed(String),

    #[error("Nix generation failed: {0}")]
    GenerationFailed(String),

    #[error("Build failed: {0}")]
    BuildFailed(String),

    #[error("Installation failed: {0}")]
    InstallFailed(String),

    #[error("Desktop integration failed: {0}")]
    DesktopFailed(String),

    #[error("Sandbox error: {0}")]
    SandboxError(String),

    #[error("FHS error: {0}")]
    FhsError(String),

    #[error("Plugin error: {0}")]
    PluginError(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Nix not found: {0}")]
    NixNotFound(String),

    #[error("File not found: {0}")]
    FileNotFound(String),

    #[error("Invalid input: {0}")]
    InvalidInput(String),

    #[error("{0}")]
    Other(String),
}

pub type Result<T> = std::result::Result<T, App2NixError>;
