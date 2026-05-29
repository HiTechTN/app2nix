use std::path::Path;
use std::fs;
use sha2::{Sha256, Digest};

#[cfg(test)]
mod tests;

use app2nix_core::{PackageInfo, PackageFormat, Detector, App2NixError, Result};

pub struct DefaultDetector;

impl DefaultDetector {
    pub fn new() -> Self {
        Self
    }

    fn detect_by_extension(path: &str) -> Option<PackageFormat> {
        let p = Path::new(path);
        match p.extension()?.to_str()? {
            "deb" => Some(PackageFormat::Deb),
            "rpm" => Some(PackageFormat::Rpm),
            "AppImage" => Some(PackageFormat::AppImage),
            "appimage" => Some(PackageFormat::AppImage),
            "gz" | "tgz" => {
                let name = p.file_name()?.to_str()?;
                if name.ends_with(".tar.gz") || name.ends_with(".tgz") {
                    Some(PackageFormat::TarGz)
                } else {
                    None
                }
            }
            "zip" => Some(PackageFormat::Zip),
            "flatpak" => Some(PackageFormat::Flatpak),
            "snap" => Some(PackageFormat::Snap),
            "jar" => Some(PackageFormat::Java),
            _ => {
                let name = p.file_name()?.to_str()?;
                if name.ends_with(".tar.gz") {
                    Some(PackageFormat::TarGz)
                } else if name.ends_with(".AppImage") {
                    Some(PackageFormat::AppImage)
                } else {
                    None
                }
            }
        }
    }

    fn detect_by_magic(path: &str) -> Option<PackageFormat> {
        let data = fs::read(path).ok()?;
        if data.len() < 16 {
            return None;
        }

        if data.starts_with(b"!<arch>\n") || data.starts_with(b"!<arch>\xde") {
            if data.len() > 60 && &data[..8] == b"!<arch>\n" {
                let name = std::str::from_utf8(&data[16..60]).ok()?;
                let deb_check = name.split_whitespace().next()?;
                if deb_check.contains("debian") || deb_check.contains("deb") {
                    return Some(PackageFormat::Deb);
                }
            }
        }

        if &data[..4] == b"\x7fELF" {
            return Some(PackageFormat::ElfBinary);
        }

        if &data[..5] == b"\x1f\x8b\x08\x00\x00" {
            return Some(PackageFormat::TarGz);
        }

        if &data[..4] == b"PK\x03\x04" {
            if path.ends_with(".jar") || path.ends_with(".zip") {
                return Some(PackageFormat::Zip);
            }
            return Some(PackageFormat::Zip);
        }

        if &data[..4] == b"\x00\x01\x00\x00" {
            return Some(PackageFormat::Rpm);
        }

        if &data[..4] == b"\xed\xab\xee\xdb" {
            return Some(PackageFormat::Rpm);
        }

        if &data[..4] == b"\x41\x49\x01\x01" {
            return Some(PackageFormat::AppImage);
        }

        if &data[..4] == b"\x41\x49\x02\x00" {
            return Some(PackageFormat::AppImage);
        }

        if &data[..7] == b"\x68\x73\x71\x73\x2f\x00\x00" {
            return Some(PackageFormat::Snap);
        }

        let header = &data[..8.min(data.len())];
        let header_str = std::str::from_utf8(header).unwrap_or("");
        if header_str.starts_with("#!/") {
            return Some(PackageFormat::Unknown);
        }

        None
    }

    fn detect_by_file_cmd(path: &str) -> Option<PackageFormat> {
        let output = std::process::Command::new("file")
            .arg("-b")
            .arg(path)
            .output()
            .ok()?;
        let stdout = String::from_utf8_lossy(&output.stdout).to_lowercase();

        if stdout.contains("debian") || stdout.contains("deb archive") {
            return Some(PackageFormat::Deb);
        }
        if stdout.contains("rpm") && stdout.contains("binary") {
            return Some(PackageFormat::Rpm);
        }
        if stdout.contains("appimage") || stdout.contains("app image") {
            return Some(PackageFormat::AppImage);
        }
        if stdout.contains("gzip") || stdout.contains("tar archive") {
            return Some(PackageFormat::TarGz);
        }
        if stdout.contains("zip") {
            return Some(PackageFormat::Zip);
        }
        if stdout.contains("elf") {
            return Some(PackageFormat::ElfBinary);
        }
        if stdout.contains("flatpak") {
            return Some(PackageFormat::Flatpak);
        }
        if stdout.contains("squashfs") {
            return Some(PackageFormat::Snap);
        }

        None
    }

    fn compute_hash(path: &str) -> String {
        let data = match fs::read(path) {
            Ok(d) => d,
            Err(_) => return "unknown".into(),
        };
        let hash = Sha256::digest(&data);
        format!("{:x}", hash)
    }

    fn infer_name(path: &str) -> String {
        Path::new(path)
            .file_stem()
            .and_then(|s| s.to_str())
            .map(|s| {
                let s = s.trim_end_matches(".tar");
                let s = s.trim_end_matches("_amd64");
                let s = s.trim_end_matches("_x86_64");
                let s = s.trim_end_matches("-amd64");
                let s = s.trim_end_matches("-x86_64");
                let s = s.trim_end_matches("_x64");
                let s = s.trim_end_matches("-x64");
                let s = s.trim_end_matches("_linux");
                let s = s.trim_end_matches("-linux");
                s.to_lowercase()
            })
            .unwrap_or_else(|| "unknown".into())
    }
}

impl Detector for DefaultDetector {
    fn detect(&self, path: &str) -> Result<PackageInfo> {
        if !Path::new(path).exists() {
            return Err(App2NixError::FileNotFound(path.into()));
        }

        let metadata = fs::metadata(path)
            .map_err(|e| App2NixError::Io(e))?;
        let size = metadata.len();
        let hash = Self::compute_hash(path);

        let format = Self::detect_by_extension(path)
            .or_else(|| Self::detect_by_magic(path))
            .or_else(|| Self::detect_by_file_cmd(path))
            .unwrap_or(PackageFormat::Unknown);

        let name = Self::infer_name(path);

        Ok(PackageInfo {
            name,
            version: None,
            format,
            description: None,
            source_path: path.to_string(),
            size,
            hash,
            architecture: None,
            maintainer: None,
            homepage: None,
        })
    }
}
