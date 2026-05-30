use std::path::Path;

use clap::{Parser, Subcommand};

use app2nix_core::{
    App2NixConfig, Pipeline, Result, App2NixError,
    Detector, Extractor, Analyzer, Installer, DesktopIntegrator,
};
use app2nix_detector::DefaultDetector;
use app2nix_extractor::DefaultExtractor;
use app2nix_analyzer::DefaultAnalyzer;
use app2nix_patcher::DefaultPatcher;
use app2nix_nixgen::DefaultNixGenerator;
use app2nix_installer::DefaultInstaller;
use app2nix_desktop::DefaultDesktopIntegrator;

#[derive(Parser)]
#[command(name = "app2nix")]
#[command(version = "3.0.1")]
#[command(about = "Universal Linux application installer for NixOS")]
#[command(long_about = r#"
app2nix - Universal Linux Application Installer for NixOS

Convert any Linux application file into a reproducible Nix package,
install it into the Nix profile, and integrate it into the system
application menu automatically.

Examples:
  app2nix install discord.deb
  app2nix install code.deb
  app2nix install obsidian-*.AppImage
  app2nix inspect some-file
  app2nix list
  app2nix doctor
"#)]
struct Cli {
    #[command(subcommand)]
    command: Commands,

    #[arg(global = true, long, short = 'v')]
    #[arg(help = "Enable verbose output")]
    verbose: bool,

    #[arg(global = true, long)]
    #[arg(help = "Keep build directory after installation")]
    keep: bool,
}

#[derive(Subcommand)]
enum Commands {
    /// Install a Linux application file
    Install {
        /// Path or URL to the application file
        file: String,

        /// Custom name for the package
        #[arg(long, short)]
        name: Option<String>,

        /// Do not install into profile (build only)
        #[arg(long)]
        build_only: bool,

        /// Use FHS compatibility mode
        #[arg(long)]
        fhs: bool,

        /// Skip desktop integration
        #[arg(long)]
        no_desktop: bool,
    },

    /// Uninstall an installed application
    Uninstall {
        /// Application name to remove
        app: String,
    },

    /// List installed applications
    List,

    /// Inspect a file without installing
    Inspect {
        /// Path to the file to inspect
        file: String,

        /// Output format (json or text)
        #[arg(long, default_value = "text")]
        format: String,
    },

    /// Build a Nix derivation without installing
    Build {
        /// Path to the application file
        file: String,

        /// Output directory
        #[arg(long, short, default_value = "./result")]
        output: String,

        /// Custom name for the package
        #[arg(long, short)]
        name: Option<String>,

        /// Use FHS compatibility mode
        #[arg(long)]
        fhs: bool,
    },

    /// Run system diagnostics
    Doctor,

    /// Manage dependency cache
    Cache {
        #[command(subcommand)]
        action: CacheAction,
    },

    /// Clean build artifacts and cache
    Clean {
        /// Also remove all installed apps
        #[arg(long)]
        all: bool,
    },
}

#[derive(Subcommand)]
enum CacheAction {
    /// Show cache statistics
    Info,
    /// Clear the dependency cache
    Clear,
}

fn main() {
    let cli = Cli::parse();
    let config = App2NixConfig::default()
        .with_verbose(cli.verbose)
        .with_keep_build(cli.keep);

    if cli.verbose {
        tracing_subscriber::fmt()
            .with_env_filter("app2nix=debug")
            .init();
    }

    let result = match &cli.command {
        Commands::Install { file, name: _name, build_only: _build_only, fhs: _fhs, no_desktop: _no_desktop } => {
            cmd_install(&config, file)
        }
        Commands::Uninstall { app } => cmd_uninstall(&config, app),
        Commands::List => cmd_list(&config),
        Commands::Inspect { file, format } => cmd_inspect(&config, file, format),
        Commands::Build { file, output, name, fhs } => cmd_build(&config, file, output, name.as_deref(), *fhs),
        Commands::Doctor => cmd_doctor(&config),
        Commands::Cache { action } => cmd_cache(&config, action),
        Commands::Clean { all } => cmd_clean(&config, *all),
    };

    if let Err(e) = result {
        eprintln!("error: {}", e);
        std::process::exit(1);
    }
}

fn build_pipeline(config: &App2NixConfig) -> Pipeline {
    let detector = Box::new(DefaultDetector::new());
    let extractor = Box::new(DefaultExtractor::new());
    let analyzer = Box::new(DefaultAnalyzer::new());
    let patcher = Box::new(DefaultPatcher::new());
    let generator = Box::new(DefaultNixGenerator::new());
    let installer = Box::new(DefaultInstaller::new(
        &config.nix_binary,
        config.use_flakes,
        &config.registry_path().to_string_lossy(),
    ));
    let desktop = Box::new(DefaultDesktopIntegrator::new());

    Pipeline::new(detector, extractor, analyzer, patcher, generator, installer, desktop)
}

fn cmd_install(
    config: &App2NixConfig,
    file: &str,
) -> Result<()> {
    eprintln!("🔍 app2nix v{}", env!("CARGO_PKG_VERSION"));
    eprintln!("──────────────────────────────────────");

    if !Path::new(file).exists() {
        return Err(App2NixError::FileNotFound(file.into()));
    }

    let pipeline = build_pipeline(config);

    let work_dir = config.builds_dir()
        .join("install")
        .join(chrono::Utc::now().format("%Y%m%d%H%M%S").to_string());

    eprintln!("📦 Detecting package type...");
    let result = pipeline.run(file, &work_dir.to_string_lossy())?;

    eprintln!("✅ {} v{} installed successfully!", result.app_name, result.version);
    eprintln!("   Store path: {}", result.store_paths.first().unwrap_or(&String::new()));
    eprintln!("   Profile: {}", result.profile_name.as_deref().unwrap_or("unknown"));

    for desktop in &result.desktop_files {
        eprintln!("   Desktop: {}", desktop);
    }

    eprintln!();
    eprintln!("   You can now run '{}' from your application menu or terminal.", result.app_name);

    if !config.keep_build {
        let _ = std::fs::remove_dir_all(&work_dir);
    }

    Ok(())
}

fn cmd_uninstall(config: &App2NixConfig, app: &str) -> Result<()> {
    eprintln!("🗑️  Uninstalling {}...", app);

    let desktop_integrator = DefaultDesktopIntegrator::new();
    desktop_integrator.unregister(app)?;

    let installer = DefaultInstaller::new(
        &config.nix_binary,
        config.use_flakes,
        &config.registry_path().to_string_lossy(),
    );
    installer.uninstall(app)?;

    eprintln!("✅ {} uninstalled successfully.", app);
    Ok(())
}

fn cmd_list(config: &App2NixConfig) -> Result<()> {
    let installer = DefaultInstaller::new(
        &config.nix_binary,
        config.use_flakes,
        &config.registry_path().to_string_lossy(),
    );
    let apps = installer.list_installed()?;

    if apps.is_empty() {
        eprintln!("No applications installed via app2nix.");
        return Ok(());
    }

    eprintln!("📋 Installed applications via app2nix:");
    eprintln!("────────────────────────────────────────");
    eprintln!(" {:<20} {:<12} {:<30}", "Name", "Version", "Store Path");
    eprintln!(" ────────────────────────────────────────");

    for app in &apps {
        let store = app.store_path.as_deref().unwrap_or("-");
        let store_short = if store.len() > 28 {
            format!("...{}", &store[store.len().saturating_sub(25)..])
        } else {
            store.to_string()
        };
        eprintln!(" {:<20} {:<12} {:<30}", app.name, app.version, store_short);
    }
    eprintln!(" ────────────────────────────────────────");
    eprintln!(" Total: {} application(s)", apps.len());

    Ok(())
}

fn cmd_inspect(config: &App2NixConfig, file: &str, format: &str) -> Result<()> {
    if !Path::new(file).exists() {
        return Err(App2NixError::FileNotFound(file.into()));
    }

    eprintln!("🔍 Inspecting: {}", file);
    eprintln!("──────────────────────────────────────");

    let detector = DefaultDetector::new();
    let package_info = detector.detect(file)?;

    let extractor = DefaultExtractor::new();
    let work_dir = config.builds_dir().join("inspect");
    let files = extractor.extract(&package_info, &work_dir.to_string_lossy())?;

    let analyzer = DefaultAnalyzer::new();
    let analysis = analyzer.analyze(&package_info, &files)?;

    if format == "json" {
        println!("{}", serde_json::to_string_pretty(&analysis).unwrap_or_default());
    } else {
        eprintln!(" Package: {} ({})", analysis.package.name, analysis.package.format);
        eprintln!(" Path: {}", analysis.package.source_path);
        eprintln!(" Size: {} bytes", analysis.package.size);
        eprintln!(" Hash: {}", analysis.package.hash);
        eprintln!();
        eprintln!(" Format: {}", analysis.package.format);
        eprintln!(" Files extracted: {}", analysis.extracted_files.len());
        eprintln!(" ELF binaries: {}", analysis.elf_binaries.len());
        eprintln!(" Dependencies found: {}", analysis.resolved_deps.len());
        eprintln!(" Unresolved: {}", analysis.unresolved_libs.len());
        eprintln!();

        if !analysis.all_needed_libs.is_empty() {
            eprintln!(" Libraries needed:");
            for lib in &analysis.all_needed_libs {
                let resolved = analysis.resolved_deps.iter().find(|d| &d.library == lib);
                match resolved {
                    Some(r) if r.nix_attr.is_some() => {
                        eprintln!("   ✓ {} → {}", lib, r.nix_attr.as_ref().unwrap());
                    }
                    _ => eprintln!("   ✗ {} (unresolved)", lib),
                }
            }
            eprintln!();
        }

        if !analysis.desktop_entries.is_empty() {
            eprintln!(" Desktop entries:");
            for entry in &analysis.desktop_entries {
                eprintln!("   ✓ {}", entry.app_name);
            }
            eprintln!();
        }

        if let Some(main) = &analysis.main_binary {
            eprintln!(" Main binary: {}", main);
        }

        if !analysis.app_type_hints.is_empty() {
            eprintln!(" App type hints:");
            for hint in &analysis.app_type_hints {
                eprintln!("   {:?}", hint);
            }
        }
    }

    if !config.keep_build {
        let _ = std::fs::remove_dir_all(&work_dir);
    }

    Ok(())
}

fn cmd_build(
    config: &App2NixConfig,
    file: &str,
    output: &str,
    name: Option<&str>,
    use_fhs: bool,
) -> Result<()> {
    if !Path::new(file).exists() {
        return Err(App2NixError::FileNotFound(file.into()));
    }

    let pipeline = build_pipeline(config);

    let work_dir = config.builds_dir()
        .join("build")
        .join(chrono::Utc::now().format("%Y%m%d%H%M%S").to_string());

    let package_info = pipeline.detector.detect(file)?;
    let extracted = pipeline.extractor.extract(&package_info, &work_dir.to_string_lossy())?;
    let analysis = pipeline.analyzer.analyze(&package_info, &extracted)?;

    let opts = app2nix_core::GenerateOptions {
        app_name: name.unwrap_or(&package_info.name).to_string(),
        version: package_info.version.clone().unwrap_or_else(|| "1.0.0".into()),
        description: package_info.description.clone().unwrap_or_default(),
        format: package_info.format,
        main_binary: analysis.main_binary.clone(),
        build_inputs: analysis.resolved_deps.iter()
            .filter_map(|d| d.nix_attr.clone())
            .collect(),
        native_build_inputs: vec!["autoPatchelfHook".into()],
        elf_binaries: analysis.elf_binaries.clone(),
        all_files: analysis.extracted_files.clone(),
        desktop_entries: analysis.desktop_entries.clone(),
        icons: analysis.icons.clone(),
        app_type_hints: analysis.app_type_hints.clone(),
        env_vars: std::collections::HashMap::new(),
        use_fhs,
        extra_phases: Vec::new(),
    };

    let derivation_path = pipeline.generator.generate(&opts, &work_dir.to_string_lossy())?;
    let store_path = pipeline.installer.build(&derivation_path, output)?;

    eprintln!("✅ Build complete!");
    eprintln!("   Derivation: {}", derivation_path);
    eprintln!("   Output: {}", store_path);

    if !config.keep_build {
        let _ = std::fs::remove_dir_all(&work_dir);
    }

    Ok(())
}

fn cmd_doctor(_config: &App2NixConfig) -> Result<()> {
    eprintln!("🔧 app2nix system diagnostics");
    eprintln!("──────────────────────────────");

    let checks: Vec<Check> = vec![
        ("nix", || which("nix")),
        ("patchelf", || which("patchelf")),
        ("file", || which("file")),
        ("dpkg-deb", || which("dpkg-deb")),
        ("tar", || which("tar")),
        ("unzip", || which("unzip")),
        ("rpm2cpio", || which("rpm2cpio")),
        ("unsquashfs", || which("unsquashfs")),
        ("update-desktop-database", || which("update-desktop-database")),
    ];

    for (name, check_fn) in &checks {
        let found = check_fn();
        let status = if found { "✓" } else { "✗" };
        eprintln!(" {} {} {}", status, name, if found { "found" } else { "not found" });
    }

    eprintln!();
    let has_nix = which("nix");
    if has_nix {
        let version_output = std::process::Command::new("nix")
            .arg("--version")
            .output()
            .ok();
        if let Some(output) = version_output {
            eprintln!(" nix version: {}", String::from_utf8_lossy(&output.stdout).trim());
        }

        if let Ok(nixos_output) = std::process::Command::new("nixos-version")
            .arg("--version")
            .output()
        {
            let ver = String::from_utf8_lossy(&nixos_output.stdout);
            eprintln!(" OS: NixOS {}", ver.trim());
        } else {
            eprintln!(" OS: Linux (not NixOS)");
        }
    } else {
        eprintln!(" ⚠️  nix is not installed! app2nix requires Nix package manager.");
        eprintln!("    Install it: curl -L https://nixos.org/nix/install | sh");
    }

    let dirs_to_check = vec![
        ("Cache dir", _config.cache_dir.to_string_lossy().to_string()),
        ("Data dir", _config.data_dir.to_string_lossy().to_string()),
        ("Build dir", _config.build_dir.to_string_lossy().to_string()),
    ];

    eprintln!();
    for (label, dir) in &dirs_to_check {
        let exists = Path::new(dir).exists();
        eprintln!(" {} {} {}", if exists { "✓" } else { " " }, label, dir);
    }

    Ok(())
}

fn cmd_cache(_config: &App2NixConfig, action: &CacheAction) -> Result<()> {
    match action {
        CacheAction::Info => {
            eprintln!("Cache management not yet implemented (stub)");
            eprintln!("  Cache dir: {}", _config.cache_dir.to_string_lossy());
            Ok(())
        }
        CacheAction::Clear => {
            let cache_dir = &_config.cache_dir;
            if cache_dir.exists() {
                std::fs::remove_dir_all(cache_dir)
                    .map_err(|e| App2NixError::Other(format!("Failed to clear cache: {}", e)))?;
                eprintln!("✅ Cache cleared.");
            } else {
                eprintln!("Cache is already empty.");
            }
            Ok(())
        }
    }
}

fn cmd_clean(config: &App2NixConfig, all: bool) -> Result<()> {
    if config.build_dir.exists() {
        std::fs::remove_dir_all(&config.build_dir)
            .map_err(|e| App2NixError::Other(format!("Failed to clean builds: {}", e)))?;
        eprintln!("✅ Build artifacts cleaned.");
    }

    if config.cache_dir.exists() {
        std::fs::remove_dir_all(&config.cache_dir)
            .map_err(|e| App2NixError::Other(format!("Failed to clean cache: {}", e)))?;
        eprintln!("✅ Cache cleaned.");
    }

    if all {
        let registry_path = config.registry_path();
        if registry_path.exists() {
            std::fs::remove_file(&registry_path)
                .map_err(|e| App2NixError::Other(format!("Failed to remove registry: {}", e)))?;
            eprintln!("✅ Registry cleared.");
        }

        let installer = DefaultInstaller::new(
            &config.nix_binary,
            config.use_flakes,
            &config.registry_path().to_string_lossy(),
        );
        let apps = installer.list_installed()?;
        for app in &apps {
            eprintln!("   Uninstalling {}...", app.name);
            let _ = installer.uninstall(&app.name);
        }
        eprintln!("✅ All applications uninstalled.");
    }

    Ok(())
}

type Check = (&'static str, fn() -> bool);

fn which(cmd: &str) -> bool {
    std::process::Command::new("which")
        .arg(cmd)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}
