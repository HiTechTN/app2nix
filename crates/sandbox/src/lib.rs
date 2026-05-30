#[cfg(test)]
mod tests;

use app2nix_core::{App2NixError, Result};

pub struct Sandbox {
    enabled: bool,
    temp_dir: String,
}

impl Sandbox {
    /// Create a new `Sandbox` instance.
    ///
    /// When `enabled` is `false`, [`create_sandbox`](Sandbox::create_sandbox)
    /// returns a plain temp directory and [`cleanup`](Sandbox::cleanup) is a no-op.
    ///
    /// # Examples
    ///
    /// ```
    /// use app2nix_sandbox::Sandbox;
    ///
    /// let sb = Sandbox::new(false);
    /// assert!(!sb.is_enabled());
    /// ```
    pub fn new(enabled: bool) -> Self {
        Self {
            enabled,
            temp_dir: std::env::temp_dir()
                .join("app2nix-sandbox")
                .to_string_lossy()
                .to_string(),
        }
    }

    pub fn create_sandbox(&self, name: &str) -> Result<String> {
        if !self.enabled {
            return Ok(std::env::temp_dir()
                .join(format!("app2nix-{}", name))
                .to_string_lossy()
                .to_string());
        }

        let sandbox_dir = std::path::Path::new(&self.temp_dir).join(name);
        std::fs::create_dir_all(&sandbox_dir)
            .map_err(|e| App2NixError::SandboxError(e.to_string()))?;

        std::fs::create_dir_all(sandbox_dir.join("build"))
            .map_err(|e| App2NixError::SandboxError(e.to_string()))?;
        std::fs::create_dir_all(sandbox_dir.join("cache"))
            .map_err(|e| App2NixError::SandboxError(e.to_string()))?;
        std::fs::create_dir_all(sandbox_dir.join("output"))
            .map_err(|e| App2NixError::SandboxError(e.to_string()))?;

        Ok(sandbox_dir.to_string_lossy().to_string())
    }

    pub fn cleanup(&self, path: &str) -> Result<()> {
        if !self.enabled {
            return Ok(());
        }
        std::fs::remove_dir_all(path).map_err(|e| App2NixError::SandboxError(e.to_string()))
    }

    /// Check whether the sandbox is enabled.
    ///
    /// # Examples
    ///
    /// ```
    /// use app2nix_sandbox::Sandbox;
    ///
    /// let sb = Sandbox::new(true);
    /// assert!(sb.is_enabled());
    /// ```
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }
}
