use std::fs;
use std::path::Path;

#[cfg(test)]
mod tests;

use app2nix_core::{App2NixError, AppEntry, AppRegistry, Installer, PackageFormat, Result};

pub struct DefaultInstaller {
    nix_binary: String,
    registry_path: String,
}

impl DefaultInstaller {
    pub fn new(nix_binary: &str, _use_flakes: bool, registry_path: &str) -> Self {
        Self {
            nix_binary: nix_binary.to_string(),
            registry_path: registry_path.to_string(),
        }
    }

    fn load_registry(&self) -> AppRegistry {
        let path = Path::new(&self.registry_path);
        if path.exists() {
            fs::read_to_string(path)
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok())
                .unwrap_or(AppRegistry { apps: vec![] })
        } else {
            AppRegistry { apps: vec![] }
        }
    }

    fn save_registry(&self, registry: &AppRegistry) -> Result<()> {
        let path = Path::new(&self.registry_path);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| App2NixError::InstallFailed(e.to_string()))?;
        }
        let json = serde_json::to_string_pretty(registry)
            .map_err(|e| App2NixError::InstallFailed(e.to_string()))?;
        fs::write(path, json).map_err(|e| App2NixError::InstallFailed(e.to_string()))?;
        Ok(())
    }
}

impl Installer for DefaultInstaller {
    fn build(&self, derivation_path: &str, output_dir: &str) -> Result<String> {
        let build_dir = Path::new(derivation_path)
            .parent()
            .unwrap_or(Path::new("."));

        let status = std::process::Command::new(&self.nix_binary)
            .args(["build", derivation_path, "--out-link", output_dir])
            .current_dir(build_dir)
            .status()
            .map_err(|e| App2NixError::BuildFailed(format!("nix build failed: {}", e)))?;

        if !status.success() {
            let result_link = Path::new(output_dir).join("result");
            if result_link.exists() {
                let real_path = fs::read_link(&result_link)
                    .map_err(|e| App2NixError::BuildFailed(e.to_string()))?;
                return Ok(real_path.to_string_lossy().to_string());
            }
            return Err(App2NixError::BuildFailed(
                "nix build returned non-zero exit code".into(),
            ));
        }

        let result_link = Path::new(output_dir).join("result");
        if result_link.exists() {
            let real_path = fs::read_link(&result_link)
                .map_err(|e| App2NixError::BuildFailed(e.to_string()))?;
            Ok(real_path.to_string_lossy().to_string())
        } else {
            Ok(format!("{}/result", output_dir))
        }
    }

    fn install(&self, store_path: &str, name: &str) -> Result<String> {
        let profile_name = format!("app2nix-{}", name);

        let status = std::process::Command::new(&self.nix_binary)
            .args(["profile", "install", store_path, "--priority", "5"])
            .status()
            .map_err(|e| App2NixError::InstallFailed(format!("nix profile install: {}", e)))?;

        if !status.success() {
            let legacy_status = std::process::Command::new("nix-env")
                .args(["-i", store_path])
                .status()
                .ok();

            match legacy_status {
                Some(s) if s.success() => {}
                _ => {
                    return Err(App2NixError::InstallFailed(
                        "Both nix profile install and nix-env -i failed".into(),
                    ));
                }
            }
        }

        let mut registry = self.load_registry();
        registry.apps.push(AppEntry {
            name: name.to_string(),
            version: "1.0.0".to_string(),
            format: PackageFormat::Unknown,
            install_path: store_path.to_string(),
            store_path: Some(store_path.to_string()),
            desktop_file: None,
            profile: profile_name.clone(),
            installed_at: chrono::Utc::now().to_rfc3339(),
            size: 0,
        });
        self.save_registry(&registry)?;

        Ok(profile_name)
    }

    fn uninstall(&self, name: &str) -> Result<()> {
        let profile_name = format!("app2nix-{}", name);

        let status = std::process::Command::new(&self.nix_binary)
            .args(["profile", "remove", &profile_name])
            .status()
            .map_err(|e| App2NixError::InstallFailed(format!("nix profile remove: {}", e)))?;

        if !status.success() {
            let legacy_status = std::process::Command::new("nix-env")
                .args(["-e", name])
                .status()
                .ok();

            match legacy_status {
                Some(s) if s.success() => {}
                _ => {
                    return Err(App2NixError::InstallFailed(
                        "Both nix profile remove and nix-env -e failed".into(),
                    ));
                }
            }
        }

        let mut registry = self.load_registry();
        registry.apps.retain(|a| a.name != name);
        self.save_registry(&registry)?;

        Ok(())
    }

    fn list_installed(&self) -> Result<Vec<AppEntry>> {
        let registry = self.load_registry();
        Ok(registry.apps)
    }
}
