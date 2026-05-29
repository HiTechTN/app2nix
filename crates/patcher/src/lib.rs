use std::path::Path;
use std::fs;
use std::os::unix::fs::PermissionsExt;

#[cfg(test)]
mod tests;

use app2nix_core::{AnalysisResult, ResolvedDependency, Patcher, Result, App2NixError};

pub struct DefaultPatcher;

impl DefaultPatcher {
    pub fn new() -> Self {
        Self
    }

    fn patch_elf_rpath(&self, elf_path: &str, lib_paths: &[String]) -> Result<()> {
        let mut rpath_parts: Vec<String> = Vec::new();

        rpath_parts.push("$ORIGIN".to_string());
        rpath_parts.push("$ORIGIN/../lib".to_string());
        rpath_parts.push("$ORIGIN/lib".to_string());

        for lib_path in lib_paths {
            rpath_parts.push(format!("$ORIGIN/{}", lib_path));
        }

        let rpath = rpath_parts.join(":");

        let status = std::process::Command::new("patchelf")
            .args(["--set-rpath", &rpath, elf_path])
            .status()
            .map_err(|e| {
                App2NixError::PatchingFailed(format!("patchelf rpath failed: {}", e))
            })?;

        if !status.success() {
            return Err(App2NixError::PatchingFailed(format!(
                "patchelf set-rpath failed for {}",
                elf_path
            )));
        }

        Ok(())
    }

    fn fix_interpreter(&self, elf_path: &str) -> Result<()> {
        let status = std::process::Command::new("patchelf")
            .args([
                "--set-interpreter",
                "/nix/store/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-glibc-*/lib/ld-linux-x86-64.so.2",
                elf_path,
            ])
            .status()
            .map_err(|e| {
                App2NixError::PatchingFailed(format!("patchelf interpreter failed: {}", e))
            })?;

        let _ = status;
        Ok(())
    }

    fn make_executable(&self, path: &str) -> Result<()> {
        let metadata = fs::metadata(path)
            .map_err(|e| App2NixError::PatchingFailed(e.to_string()))?;
        let mut perms = metadata.permissions();
        let mode = perms.mode();
        if mode & 0o111 == 0 {
            perms.set_mode(mode | 0o755);
            fs::set_permissions(path, perms)
                .map_err(|e| App2NixError::PatchingFailed(e.to_string()))?;
        }
        Ok(())
    }

    fn generate_wrapper(
        &self,
        binary_path: &str,
        output_dir: &str,
        app_name: &str,
    ) -> Result<String> {
        let wrapper_path = Path::new(output_dir).join(format!(".{}_wrapper", app_name));
        let wrapper_content = format!(
            r#"#!/usr/bin/env bash
# app2nix wrapper for {app_name}
# Generated automatically - do not edit

export PATH="{}:$PATH"
export LD_LIBRARY_PATH="${{LD_LIBRARY_PATH:-}}"
export APP2NIX_APP="{app_name}"

exec "{}" "$@"
"#,
            Path::new(binary_path).parent().unwrap_or(Path::new(".")).to_string_lossy(),
            binary_path,
        );

        fs::write(&wrapper_path, &wrapper_content)
            .map_err(|e| App2NixError::PatchingFailed(e.to_string()))?;

        let mut perms = fs::metadata(&wrapper_path)
            .map_err(|e| App2NixError::PatchingFailed(e.to_string()))?
            .permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&wrapper_path, perms)
            .map_err(|e| App2NixError::PatchingFailed(e.to_string()))?;

        Ok(wrapper_path.to_string_lossy().to_string())
    }
}

impl Patcher for DefaultPatcher {
    fn patch_binaries(
        &self,
        target_dir: &str,
        analysis: &AnalysisResult,
        resolved_deps: &[ResolvedDependency],
    ) -> Result<()> {
        let lib_paths: Vec<String> = resolved_deps
            .iter()
            .filter_map(|d| d.nix_attr.as_ref())
            .map(|attr| format!("../../../{}", attr.replace('.', "/")))
            .collect();

        for elf in &analysis.elf_binaries {
            self.make_executable(&elf.path)?;
            self.patch_elf_rpath(&elf.path, &lib_paths)?;
            self.fix_interpreter(&elf.path)?;
        }

        if let Some(ref main_bin) = analysis.main_binary {
            let app_name = &analysis.package.name;
            let _ = self.generate_wrapper(main_bin, target_dir, app_name);
        }

        Ok(())
    }
}
