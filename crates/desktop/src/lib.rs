use std::path::Path;
use std::fs;

use app2nix_core::{
    DetectedDesktopEntry, DetectedIcon, DesktopIntegrator,
    Result, App2NixError,
};

pub struct DefaultDesktopIntegrator;

impl DefaultDesktopIntegrator {
    pub fn new() -> Self {
        Self
    }

    fn applications_dir() -> Result<String> {
        let base = dirs::data_dir()
            .ok_or_else(|| App2NixError::DesktopFailed("Cannot find XDG data dir".into()))?;
        let dir = base.join("applications");
        fs::create_dir_all(&dir)
            .map_err(|e| App2NixError::DesktopFailed(e.to_string()))?;
        Ok(dir.to_string_lossy().to_string())
    }

    fn icons_dir() -> Result<String> {
        let base = dirs::data_dir()
            .ok_or_else(|| App2NixError::DesktopFailed("Cannot find XDG data dir".into()))?;
        let dir = base.join("icons").join("hicolor").join("48x48").join("apps");
        fs::create_dir_all(&dir)
            .map_err(|e| App2NixError::DesktopFailed(e.to_string()))?;
        Ok(dir.to_string_lossy().to_string())
    }

    fn generate_desktop_file(
        &self,
        app_name: &str,
        exec_path: &str,
        entry: &DetectedDesktopEntry,
        icons: &[DetectedIcon],
    ) -> Result<String> {
        let sanitized_name = sanitize_desktop_name(app_name);
        let dest_path = Path::new(&Self::applications_dir()?)
            .join(format!("{}.desktop", sanitized_name));

        let exec_line = if entry.exec_line.is_empty() {
            format!("{} \"$@\"", exec_path)
        } else {
            let exec = entry
                .exec_line
                .replace("%f", "")
                .replace("%F", "")
                .replace("%u", "")
                .replace("%U", "")
                .trim()
                .to_string();
            if exec.contains('/') || exec.starts_with(exec_path) {
                exec
            } else {
                format!("{} {}", exec_path, exec)
            }
        };

        let icon_name = if let Some(icon_ref) = &entry.icon_path {
            if Path::new(icon_ref).exists() {
                let icon_dest = Self::icons_dir()?.to_string();
                let ext = Path::new(icon_ref)
                    .extension()
                    .and_then(|e| e.to_str())
                    .unwrap_or("png");
                let icon_filename = format!("{}.{}", sanitized_name, ext);
                let icon_dest_path = Path::new(&icon_dest).join(&icon_filename);
                let _ = fs::copy(icon_ref, &icon_dest_path);
                icon_filename
            } else {
                icon_ref.clone()
            }
        } else {
            for icon in icons {
                let icon_dest = Self::icons_dir()?.to_string();
                let ext = Path::new(&icon.path)
                    .extension()
                    .and_then(|e| e.to_str())
                    .unwrap_or("png");
                let icon_filename = format!("{}.{}", sanitized_name, ext);
                let icon_dest_path = Path::new(&icon_dest).join(&icon_filename);
                let _ = fs::copy(&icon.path, &icon_dest_path);
            }
            sanitized_name.clone()
        };

        let categories = if entry.categories.is_empty() {
            "Utility"
        } else {
            &entry.categories.join(";")
        };

        let content = format!(
            r#"[Desktop Entry]
Type=Application
Name={name}
Exec={exec}
Icon={icon}
Categories={categories};
Terminal=false
StartupNotify=true
"#,
            name = entry.app_name,
            exec = exec_line,
            icon = icon_name,
            categories = categories,
        );

        fs::write(&dest_path, &content)
            .map_err(|e| App2NixError::DesktopFailed(e.to_string()))?;

        Ok(dest_path.to_string_lossy().to_string())
    }
}

fn sanitize_desktop_name(name: &str) -> String {
    name.to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' { c } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string()
}

impl DesktopIntegrator for DefaultDesktopIntegrator {
    fn register(
        &self,
        app_name: &str,
        exec_path: &str,
        entries: &[DetectedDesktopEntry],
        icons: &[DetectedIcon],
    ) -> Result<Vec<String>> {
        let mut created = Vec::new();

        let exec_binary = if exec_path.starts_with("/nix/store/") {
            format!("{}/bin/{}", exec_path.trim_end_matches('/'), sanitize_desktop_name(app_name))
        } else {
            exec_path.to_string()
        };

        if entries.is_empty() {
            let dummy_entry = DetectedDesktopEntry {
                path: String::new(),
                app_name: app_name.to_string(),
                exec_line: String::new(),
                icon_path: None,
                categories: vec!["Utility".to_string()],
            };
            let path = self.generate_desktop_file(app_name, &exec_binary, &dummy_entry, icons)?;
            created.push(path);
        } else {
            for entry in entries {
                let path = self.generate_desktop_file(app_name, &exec_binary, entry, icons)?;
                created.push(path);
            }
        }

        let _ = std::process::Command::new("update-desktop-database")
            .arg(Self::applications_dir().unwrap_or_default())
            .output();

        Ok(created)
    }

    fn unregister(&self, app_name: &str) -> Result<()> {
        let sanitized = sanitize_desktop_name(app_name);
        let desktop_path = Path::new(&Self::applications_dir()?)
            .join(format!("{}.desktop", sanitized));

        if desktop_path.exists() {
            fs::remove_file(&desktop_path)
                .map_err(|e| App2NixError::DesktopFailed(e.to_string()))?;
        }

        let icon_path = Path::new(&Self::icons_dir()?)
            .join(format!("{}.png", sanitized));
        if icon_path.exists() {
            let _ = fs::remove_file(&icon_path);
        }

        let _ = std::process::Command::new("update-desktop-database")
            .arg(Self::applications_dir().unwrap_or_default())
            .output();

        Ok(())
    }
}
