use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct App2NixConfig {
    pub cache_dir: PathBuf,
    pub data_dir: PathBuf,
    pub build_dir: PathBuf,
    pub nix_binary: String,
    pub use_flakes: bool,
    pub auto_install: bool,
    pub auto_desktop: bool,
    pub keep_build: bool,
    pub verbose: bool,
    pub max_parallel: usize,
    pub timeout_seconds: u64,
}

impl Default for App2NixConfig {
    fn default() -> Self {
        let data_dir = dirs::data_dir()
            .unwrap_or_else(|| PathBuf::from("/tmp"))
            .join("app2nix");

        Self {
            cache_dir: data_dir.join("cache"),
            data_dir,
            build_dir: std::env::temp_dir().join("app2nix-build"),
            nix_binary: which_nix(),
            use_flakes: true,
            auto_install: true,
            auto_desktop: true,
            keep_build: false,
            verbose: false,
            max_parallel: 4,
            timeout_seconds: 600,
        }
    }
}

fn which_nix() -> String {
    std::env::var("NIX_BIN").unwrap_or_else(|_| "nix".to_string())
}

impl App2NixConfig {
    pub fn with_verbose(mut self, verbose: bool) -> Self {
        self.verbose = verbose;
        self
    }

    pub fn with_keep_build(mut self, keep: bool) -> Self {
        self.keep_build = keep;
        self
    }

    pub fn with_no_install(mut self) -> Self {
        self.auto_install = false;
        self
    }

    pub fn cache_db_path(&self) -> PathBuf {
        self.cache_dir.join("resolver.db")
    }

    pub fn registry_path(&self) -> PathBuf {
        self.data_dir.join("registry.json")
    }

    pub fn builds_dir(&self) -> PathBuf {
        self.build_dir.clone()
    }
}
