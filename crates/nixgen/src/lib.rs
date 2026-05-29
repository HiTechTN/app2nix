use std::path::Path;
use std::fs;

#[cfg(test)]
mod tests;

use app2nix_core::{
    GenerateOptions, PackageFormat, NixGenerator,
    Result, App2NixError,
};

pub struct DefaultNixGenerator;

impl DefaultNixGenerator {
    pub fn new() -> Self {
        Self
    }

    fn generate_derivation(&self, opts: &GenerateOptions) -> Result<String> {
        let bin_path = opts
            .main_binary
            .as_deref()
            .unwrap_or("bin/unknown")
            .trim_start_matches("/build/")
            .trim_start_matches("/tmp/");

        let main_bin_relative = if bin_path.contains('/') {
            let parts: Vec<&str> = bin_path.split('/').collect();
            if parts.len() > 2 {
                format!("$out/{}", parts[parts.len()-2..].join("/"))
            } else {
                format!("$out/{}", bin_path)
            }
        } else {
            format!("$out/bin/{}", bin_path)
        };

        let install_phase = self.generate_install_phase(opts);
        let build_inputs = self.format_nix_list(&opts.build_inputs);
        let native_inputs = self.format_nix_list(&opts.native_build_inputs);
        let desktop_phase = self.generate_desktop_phase(opts);
        let env_vars = self.generate_env_vars(opts);
        let wrapper_script = self.generate_wrapper_script(opts);

        let derivation = format!(
            r#"{{ lib, stdenv, autoPatchelfHook, makeWrapper
, dpkg, rpm, cpio, squashfsTools, p7zip, file
, fetchurl, writeScript
{inputs}
}}:

stdenv.mkDerivation {{
  pname = "{name}";
  version = "{version}";

  src = ./.;

  dontBuild = true;
  dontConfigure = true;

  nativeBuildInputs = [
    autoPatchelfHook
    makeWrapper
    {native_inputs}
  ];

  buildInputs = [
    {build_inputs}
  ];

  {env_vars}

  installPhase = ''
    runHook preInstall

    mkdir -p $out/bin $out/lib $out/share

    {install_phase}

    # Fix permissions
    find $out -type f -executable -exec chmod +x {{}} \;

    # Ensure main binary is executable
    chmod +x {main_bin_relative} 2>/dev/null || true

    # Create wrapper script
    {wrapper_script}

    {desktop_phase}

    # Patch all ELF binaries
    find $out -type f -executable -exec patchelf --set-rpath "$out/lib:$out/lib64:${{out}}/lib/x86_64-linux-gnu:$ORIGIN:$ORIGIN/../lib" {{}} \; 2>/dev/null || true

    runHook postInstall
  '';

  meta = with lib; {{
    description = "{description}";
    {homepage_line}
    license = licenses.unfree;
    platforms = platforms.linux;
    maintainers = [];
  }};
}}
"#,
            name = sanitize_name(&opts.app_name),
            version = sanitize_version(&opts.version),
            description = opts.description.replace('"', r#"\""#),
            inputs = opts.build_inputs.iter()
                .filter(|i| i.contains('.'))
                .map(|i| {
                    let (ns, attr) = i.split_once('.').unwrap_or(("pkgs", i));
                    format!(", inherit ({}) {};", ns, attr)
                })
                .collect::<Vec<_>>()
                .join("\n"),
            build_inputs = build_inputs,
            native_inputs = native_inputs,
            env_vars = env_vars,
            install_phase = install_phase,
            main_bin_relative = main_bin_relative,
            wrapper_script = wrapper_script,
            desktop_phase = desktop_phase,
            homepage_line = String::new(),
        );

        Ok(derivation)
    }

    fn generate_flake(&self, opts: &GenerateOptions) -> Result<String> {
        let _derivation = self.generate_derivation(opts)?;

        let flake = format!(
            r#"{{
  description = "{description}";

  inputs = {{
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  }};

  outputs = {{ self, nixpkgs, flake-utils }}:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${{system}};
      in
      {{
        packages.default = pkgs.callPackage ./derivation.nix {{}};
        packages.{name} = pkgs.callPackage ./derivation.nix {{}};
        apps.default = {{
          type = "app";
          program = "${{pkgs.callPackage ./derivation.nix {{}}}}/bin/{name}";
        }};
      }}
    );
}}
"#,
            name = sanitize_name(&opts.app_name),
            description = opts.description.replace('"', r#"\""#),
        );

        Ok(flake)
    }

    fn generate_install_phase(&self, opts: &GenerateOptions) -> String {
        match opts.format {
            PackageFormat::Deb => {
                r#"dpkg-deb -x "$src" $out
# Move files from usr/ to proper locations
if [ -d "$out/usr" ]; then
    cp -rfl $out/usr/* $out/ 2>/dev/null || cp -r $out/usr/* $out/
    rm -rf $out/usr
fi
"#.to_string()
            }
            PackageFormat::Rpm => {
                r#"rpm2cpio "$src" | cpio -idmv -D $out
"#.to_string()
            }
            PackageFormat::AppImage => {
                r#"chmod +x "$src"
# Try --appimage-extract first
"$src" --appimage-extract --dest=$out/appimage-extracted 2>/dev/null || \
    unsquashfs -d $out/appimage-extracted "$src" 2>/dev/null || true
if [ -d "$out/appimage-extracted" ]; then
    cp -rfl $out/appimage-extracted/* $out/ 2>/dev/null || \
    cp -r $out/appimage-extracted/* $out/
    rm -rf "$out/appimage-extracted"
fi
# Find and copy the AppRun or main binary
find $out -name "AppRun" -type f -exec cp {} $out/bin/ \; 2>/dev/null || true
"#.to_string()
            }
            PackageFormat::TarGz | PackageFormat::Zip => {
                r#"cp -rfl * $out/ 2>/dev/null || cp -r * $out/
"#.to_string()
            }
            PackageFormat::ElfBinary | PackageFormat::Electron => {
                r#"cp "$src" $out/bin/
chmod +x $out/bin/*
"#.to_string()
            }
            _ => {
                r#"cp -r * $out/ 2>/dev/null || true
"#.to_string()
            }
        }
    }

    fn generate_desktop_phase(&self, opts: &GenerateOptions) -> String {
        if opts.desktop_entries.is_empty() && opts.icons.is_empty() {
            return String::new();
        }

        let mut phase = String::from("\n    # Install desktop integration files\n");

        for entry in &opts.desktop_entries {
            let desktop_path = entry.path.trim_start_matches("/build/").trim_start_matches("/tmp/");
            phase.push_str(&format!(
                "mkdir -p $out/share/applications\n"
            ));
            phase.push_str(&format!(
                "cp -f {} $out/share/applications/ 2>/dev/null || true\n",
                desktop_path
            ));
        }

        for icon in &opts.icons {
            let icon_path = icon.path.trim_start_matches("/build/").trim_start_matches("/tmp/");
            phase.push_str(&format!(
                "mkdir -p $out/share/icons/hicolor/48x48/apps\n"
            ));
            phase.push_str(&format!(
                "cp -f {} $out/share/icons/hicolor/48x48/apps/ 2>/dev/null || true\n",
                icon_path
            ));
        }

        phase
    }

    fn generate_wrapper_script(&self, opts: &GenerateOptions) -> String {
        let bin_name = sanitize_name(&opts.app_name);
        let main_bin = opts
            .main_binary
            .as_deref()
            .unwrap_or("bin/unknown")
            .trim_start_matches("/build/")
            .trim_start_matches("/tmp/");

        format!(
            r#"cat > $out/bin/{bin_name} << 'WRAPPER_EOF'
#!/usr/bin/env bash
# app2nix wrapper for {app_name}
export PATH="$out/bin:$out/sbin:$PATH"
export LD_LIBRARY_PATH="$out/lib:$out/lib64:${{LD_LIBRARY_PATH:-}}"
exec $out/{main_bin} "$@"
WRAPPER_EOF
chmod +x $out/bin/{bin_name}
"#,
            bin_name = bin_name,
            app_name = opts.app_name,
            main_bin = main_bin,
        )
    }

    fn generate_env_vars(&self, opts: &GenerateOptions) -> String {
        if opts.env_vars.is_empty() {
            return String::new();
        }

        let mut vars = String::from("  preFixup = ''\n");
        for (key, val) in &opts.env_vars {
            vars.push_str(&format!("    export {}={}\n", key, val));
        }
        vars.push_str("  '';\n");
        vars
    }

    fn format_nix_list(&self, items: &[String]) -> String {
        if items.is_empty() {
            return String::new();
        }

        let mut deduped: Vec<&str> = items.iter().map(|s| s.as_str()).collect();
        deduped.sort();
        deduped.dedup();

        deduped
            .iter()
            .map(|item| {
                if item.contains('.') {
                    let parts: Vec<&str> = item.splitn(2, '.').collect();
                    format!("{}.{}", parts[0], parts[1])
                } else {
                    item.to_string()
                }
            })
            .collect::<Vec<_>>()
            .join("\n    ")
    }
}

impl NixGenerator for DefaultNixGenerator {
    fn generate(&self, opts: &GenerateOptions, output_dir: &str) -> Result<String> {
        fs::create_dir_all(output_dir)
            .map_err(|e| App2NixError::GenerationFailed(e.to_string()))?;

        let derivation = self.generate_derivation(opts)?;
        let derivation_path = Path::new(output_dir).join("derivation.nix");
        fs::write(&derivation_path, &derivation)
            .map_err(|e| App2NixError::GenerationFailed(e.to_string()))?;

        let flake = self.generate_flake(opts)?;
        let flake_path = Path::new(output_dir).join("flake.nix");
        fs::write(&flake_path, &flake)
            .map_err(|e| App2NixError::GenerationFailed(e.to_string()))?;

        let flake_lock_path = Path::new(output_dir).join("flake.lock");
        if !flake_lock_path.exists() {
            let _ = std::process::Command::new("nix")
                .args(["flake", "lock"])
                .current_dir(output_dir)
                .output();
        }

        Ok(derivation_path.to_string_lossy().to_string())
    }
}

pub fn sanitize_name(name: &str) -> String {
    name.to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' { c } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string()
}

pub fn sanitize_version(version: &str) -> String {
    version
        .chars()
        .filter(|c| c.is_alphanumeric() || *c == '.' || *c == '-' || *c == '_')
        .collect()
}
