use std::path::Path;
use std::fs;

#[cfg(test)]
mod tests;

use app2nix_core::{
    PackageInfo, PackageFormat, ExtractedFile, Extractor,
    App2NixError, Result,
};

#[derive(Default)]
pub struct DefaultExtractor;

impl DefaultExtractor {
    pub fn new() -> Self {
        Self
    }

    fn extract_deb(package: &PackageInfo, dest: &str) -> Result<Vec<ExtractedFile>> {
        let status = std::process::Command::new("dpkg-deb")
            .args(["-x", &package.source_path, dest])
            .status()
            .map_err(|e| App2NixError::ExtractionFailed(format!("dpkg-deb not found: {}", e)))?;

        if !status.success() {
            return Err(App2NixError::ExtractionFailed(
                "dpkg-deb extraction failed".into(),
            ));
        }

        let control_output = std::process::Command::new("dpkg-deb")
            .args(["-I", &package.source_path])
            .output()
            .map_err(|e| App2NixError::ExtractionFailed(format!("dpkg-deb info failed: {}", e)))?;

        let info = String::from_utf8_lossy(&control_output.stdout);
        Self::parse_deb_control(&info, dest)
    }

    fn parse_deb_control(_info: &str, dest: &str) -> Result<Vec<ExtractedFile>> {
        Self::scan_extracted(dest)
    }

    fn extract_rpm(package: &PackageInfo, dest: &str) -> Result<Vec<ExtractedFile>> {
        let has_rpm2cpio = std::process::Command::new("rpm2cpio")
            .arg("--version")
            .output()
            .is_ok();

        if has_rpm2cpio {
            let status = std::process::Command::new("sh")
                .args(["-c", &format!(
                    "rpm2cpio '{}' | cpio -idmv -D '{}'",
                    package.source_path, dest
                )])
                .status()
                .map_err(|e| App2NixError::ExtractionFailed(format!("rpm2cpio failed: {}", e)))?;

            if !status.success() {
                return Err(App2NixError::ExtractionFailed(
                    "rpm2cpio extraction failed".into(),
                ));
            }
        } else {
            let status = std::process::Command::new("rpm")
                .args(["-i", "--root", dest, "--nodeps", "--noscripts", "--notriggers"])
                .arg(&package.source_path)
                .status()
                .map_err(|e| App2NixError::ExtractionFailed(format!("rpm extraction failed: {}", e)))?;

            if !status.success() {
                return Err(App2NixError::ExtractionFailed(
                    "rpm extraction failed".into(),
                ));
            }
        }

        Self::scan_extracted(dest)
    }

    fn extract_appimage(package: &PackageInfo, dest: &str) -> Result<Vec<ExtractedFile>> {
        use std::os::unix::fs::PermissionsExt;
        let path = Path::new(&package.source_path);
        let mut perms = fs::metadata(&package.source_path)
            .map_err(|e| App2NixError::ExtractionFailed(e.to_string()))?
            .permissions();
        perms.set_mode(0o755);
        fs::set_permissions(path, perms)
            .map_err(|e| App2NixError::ExtractionFailed(e.to_string()))?;

        let extract_dir = Path::new(dest).join("squashfs-root");
        let _ = fs::remove_dir_all(&extract_dir);

        let status = std::process::Command::new(&package.source_path)
            .arg("--appimage-extract")
            .current_dir(dest)
            .status()
            .map_err(|e| {
                App2NixError::ExtractionFailed(format!(
                    "AppImage --appimage-extract failed: {}",
                    e
                ))
            })?;

        if !status.success() {
            let status2 = std::process::Command::new("unsquashfs")
                .args(["-d", &extract_dir.to_string_lossy(), &package.source_path])
                .status()
                .map_err(|e| {
                    App2NixError::ExtractionFailed(format!(
                        "unsquashfs fallback failed: {}",
                        e
                    ))
                })?;

            if !status2.success() {
                return Err(App2NixError::ExtractionFailed(
                    "AppImage extraction failed (tried --appimage-extract and unsquashfs)".into(),
                ));
            }
        }

        if extract_dir.exists() {
            for entry in walkdir::WalkDir::new(&extract_dir)
                .into_iter()
                .filter_map(|e| e.ok())
            {
                if entry.file_type().is_dir() {
                    continue;
                }
                let full_path = entry.path();
                let rel = full_path
                    .strip_prefix(dest)
                    .unwrap_or(full_path)
                    .to_string_lossy()
                    .to_string();
                let _ = fs::create_dir_all(Path::new(dest).join(Path::new(&rel).parent().unwrap_or(Path::new(""))));
                if full_path != Path::new(dest).join(&rel) {
                    let _ = fs::rename(full_path, Path::new(dest).join(&rel));
                }
            }
            let _ = fs::remove_dir_all(&extract_dir);
        }

        Self::scan_extracted(dest)
    }

    fn extract_targz(package: &PackageInfo, dest: &str) -> Result<Vec<ExtractedFile>> {
        let status = std::process::Command::new("tar")
            .args(["-xzf", &package.source_path, "-C", dest])
            .status()
            .map_err(|e| App2NixError::ExtractionFailed(format!("tar extraction failed: {}", e)))?;

        if !status.success() {
            return Err(App2NixError::ExtractionFailed(
                "tar extraction failed".into(),
            ));
        }

        Self::scan_extracted(dest)
    }

    fn extract_zip(package: &PackageInfo, dest: &str) -> Result<Vec<ExtractedFile>> {
        let status = std::process::Command::new("unzip")
            .args(["-o", &package.source_path, "-d", dest])
            .status()
            .map_err(|e| App2NixError::ExtractionFailed(format!("unzip failed: {}", e)))?;

        if !status.success() {
            return Err(App2NixError::ExtractionFailed(
                "unzip extraction failed".into(),
            ));
        }

        Self::scan_extracted(dest)
    }

    fn extract_elf(package: &PackageInfo, dest: &str) -> Result<Vec<ExtractedFile>> {
        let fname = Path::new(&package.source_path)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("binary");
        let dest_path = Path::new(dest).join(fname);
        fs::copy(&package.source_path, &dest_path)
            .map_err(|e| App2NixError::ExtractionFailed(e.to_string()))?;

        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(&dest_path)
            .map_err(|e| App2NixError::ExtractionFailed(e.to_string()))?
            .permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&dest_path, perms)
            .map_err(|e| App2NixError::ExtractionFailed(e.to_string()))?;

        Self::scan_extracted(dest)
    }

    fn scan_extracted(dest: &str) -> Result<Vec<ExtractedFile>> {
        let mut files = Vec::new();
        for entry in walkdir::WalkDir::new(dest)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            if !entry.file_type().is_file() {
                continue;
            }
            let full_path = entry.path().to_string_lossy().to_string();
            let rel_path = entry
                .path()
                .strip_prefix(dest)
                .unwrap_or(entry.path())
                .to_string_lossy()
                .to_string();

            let is_elf = Self::check_elf(&full_path);
            let is_exec = is_elf || Self::check_executable(&full_path);

            let file_type: String = if is_elf {
                "application/x-executable".into()
            } else {
                let output = std::process::Command::new("file")
                    .arg("-b")
                    .arg(&full_path)
                    .output()
                    .ok();
                match output {
                    Some(o) => String::from_utf8_lossy(&o.stdout).trim().to_string(),
                    None => "unknown".into(),
                }
            };

            files.push(ExtractedFile {
                path: full_path,
                relative_path: rel_path,
                file_type,
                is_elf,
                is_executable: is_exec,
                size: entry.metadata().ok().map(|m| m.len()).unwrap_or(0),
            });
        }
        Ok(files)
    }

    fn check_elf(path: &str) -> bool {
        let data = match fs::read(path) {
            Ok(d) if d.len() >= 4 => d,
            _ => return false,
        };
        &data[..4] == b"\x7fELF"
    }

    fn check_executable(path: &str) -> bool {
        use std::os::unix::fs::PermissionsExt;
        fs::metadata(path)
            .ok()
            .map(|m| m.permissions().mode() & 0o111 != 0)
            .unwrap_or(false)
    }
}

impl Extractor for DefaultExtractor {
    fn extract(&self, package: &PackageInfo, dest: &str) -> Result<Vec<ExtractedFile>> {
        fs::create_dir_all(dest)
            .map_err(|e| App2NixError::ExtractionFailed(e.to_string()))?;

        match package.format {
            PackageFormat::Deb => DefaultExtractor::extract_deb(package, dest),
            PackageFormat::Rpm => DefaultExtractor::extract_rpm(package, dest),
            PackageFormat::AppImage => DefaultExtractor::extract_appimage(package, dest),
            PackageFormat::TarGz => DefaultExtractor::extract_targz(package, dest),
            PackageFormat::Zip => DefaultExtractor::extract_zip(package, dest),
            PackageFormat::ElfBinary | PackageFormat::Electron => {
                DefaultExtractor::extract_elf(package, dest)
            }
            PackageFormat::Flatpak => Err(App2NixError::ExtractionFailed(
                "Flatpak extraction not yet implemented".into(),
            )),
            PackageFormat::Snap => Err(App2NixError::ExtractionFailed(
                "Snap extraction not yet implemented".into(),
            )),
            PackageFormat::Java => Err(App2NixError::ExtractionFailed(
                "Java extraction not yet implemented".into(),
            )),
            PackageFormat::NodeJs => Err(App2NixError::ExtractionFailed(
                "NodeJS extraction not yet implemented".into(),
            )),
            PackageFormat::Unknown => {
                DefaultExtractor::extract_elf(package, dest).or_else(|_| {
                    DefaultExtractor::extract_targz(package, dest).or_else(|_| {
                        DefaultExtractor::extract_zip(package, dest)
                    })
                })
            }
        }
    }
}
