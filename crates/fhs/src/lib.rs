#[cfg(test)]
mod tests;

use app2nix_core::Result;

pub struct FhsCompat {
    enabled: bool,
}

impl FhsCompat {
    pub fn new(enabled: bool) -> Self {
        Self { enabled }
    }

    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    pub fn generate_fhs_env(&self, app_name: &str, deps: &[String], main_binary: &str) -> Result<String> {
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

    pub fn generate_build_fhs_expression(
        &self,
        app_name: &str,
        deps: &[String],
    ) -> Result<String> {
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
