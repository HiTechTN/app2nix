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

/// FHS (Filesystem Hierarchy Standard) compatibility mode.
///
/// Generates Nix expressions for FHS user environments,
/// useful for running Linux binaries that expect a standard filesystem layout.
pub struct FhsCompat {
    enabled: bool,
}

impl FhsCompat {
    /// Create a new `FhsCompat` instance.
    ///
    /// When `enabled` is `false`, all generation methods return empty strings.
    ///
    /// # Examples
    ///
    /// ```
    /// use app2nix_sandbox::FhsCompat;
    ///
    /// let compat = FhsCompat::new(false);
    /// assert!(!compat.is_enabled());
    /// ```
    pub fn new(enabled: bool) -> Self {
        Self { enabled }
    }

    /// Check whether FHS compatibility mode is enabled.
    ///
    /// # Examples
    ///
    /// ```
    /// use app2nix_sandbox::FhsCompat;
    ///
    /// let compat = FhsCompat::new(true);
    /// assert!(compat.is_enabled());
    /// ```
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    pub fn generate_fhs_env(
        &self,
        app_name: &str,
        deps: &[String],
        main_binary: &str,
    ) -> Result<String> {
        if !self.enabled {
            return Ok(String::new());
        }

        let dep_list = deps
            .iter()
            .map(|d| format!("    {}", d))
            .collect::<Vec<_>>()
            .join("\n");

        let nix_code = format!(
            r#"{{ pkgs ? import <nixpkgs> {{ }} }}:

let
  fhs = pkgs.buildFHSUserEnv {{
    name = "{app_name}-fhs";
    targetPkgs = pkgs_: with pkgs_; [
      {dep_list}
    ];
    multiPkgs = pkgs_: with pkgs_; [
      glibc
      zlib
      stdenv.cc.cc.lib
    ];
    runScript = "{main_binary}";
    profile = ''
      export FHS=1
      export APP2NIX_FHS_ENV=1
    '';
  }};
in
  fhs.env
"#,
            app_name = app_name,
            dep_list = dep_list,
            main_binary = main_binary,
        );

        Ok(nix_code)
    }

    pub fn generate_build_fhs_expression(&self, app_name: &str, deps: &[String]) -> Result<String> {
        if !self.enabled {
            return Ok(String::new());
        }
        let dep_list = deps
            .iter()
            .map(|d| format!("      {}", d))
            .collect::<Vec<_>>()
            .join("\n");

        let nix_code = format!(
            r#"{{ lib, stdenv, buildFHSUserEnv, makeWrapper
, {dep_list}
}}:

let
  fhsEnv = buildFHSUserEnv {{
    name = "{app_name}-fhs-env";
    targetPkgs = pkgs_: with pkgs_; [
      {dep_list}
    ];
    runScript = "";
  }};
in
stdenv.mkDerivation {{
  name = "{app_name}-fhs";
  nativeBuildInputs = [ makeWrapper ];

  phases = [ "installPhase" ];

  installPhase = ''
    mkdir -p $out/bin
    makeWrapper ${{fhsEnv}}/bin/{app_name}-fhs-env $out/bin/{app_name} \
      --add-flags "${{fhsEnv}}/bin/{app_name}-fhs-env"
  '';
}}
"#,
            app_name = app_name,
            dep_list = dep_list,
        );

        Ok(nix_code)
    }
}
