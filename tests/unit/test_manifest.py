"""Tests for manifest.py — standalone manifest tracking and orphan cleanup."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import app2nix.manifest as manifest


class TestManifestPath:
    def test_returns_path_object(self):
        result = manifest.manifest_path()
        assert isinstance(result, Path)

    def test_ends_with_manifest_json(self):
        assert manifest.manifest_path().name == "manifest.json"

    def test_contains_app2nix(self):
        assert "app2nix" in str(manifest.manifest_path())


class TestLoadManifest:
    @patch("app2nix.manifest.manifest_path")
    def test_returns_empty_dict_when_no_file(self, mock_path):
        mock_path.return_value = Path("/nonexistent/manifest.json")
        result = manifest.load_manifest()
        assert result == {"packages": {}}

    @patch("app2nix.manifest.manifest_path")
    def test_loads_existing_json(self, mock_path, tmp_path):
        mf = tmp_path / "manifest.json"
        mf.write_text(json.dumps({"packages": {"firefox": {}}}))
        mock_path.return_value = mf
        result = manifest.load_manifest()
        assert result == {"packages": {"firefox": {}}}

    @patch("app2nix.manifest.manifest_path")
    def test_handles_corrupted_json(self, mock_path, tmp_path):
        mf = tmp_path / "manifest.json"
        mf.write_text("{invalid json}")
        mock_path.return_value = mf
        result = manifest.load_manifest()
        assert result == {"packages": {}}


class TestSaveManifest:
    @patch("app2nix.manifest.manifest_path")
    def test_creates_parent_dirs(self, mock_path, tmp_path):
        mf = tmp_path / "subdir" / "manifest.json"
        mock_path.return_value = mf
        manifest.save_manifest({"packages": {}})
        assert mf.exists()

    @patch("app2nix.manifest.manifest_path")
    def test_writes_valid_json(self, mock_path, tmp_path):
        mf = tmp_path / "manifest.json"
        mock_path.return_value = mf
        data = {"packages": {"test-app": {"desktop_files": ["test.desktop"]}}}
        manifest.save_manifest(data)
        loaded = json.loads(mf.read_text())
        assert loaded == data


class TestRecordInstall:
    @patch("app2nix.manifest.save_manifest")
    @patch("app2nix.manifest.load_manifest")
    def test_records_desktop_and_icon_files(self, mock_load, mock_save):
        mock_load.return_value = {"packages": {}}
        manifest.record_install("Test App", ["app.desktop"], ["app-icon"])
        saved = mock_save.call_args[0][0]
        assert "test-app" in saved["packages"]
        entry = saved["packages"]["test-app"]
        assert entry["desktop_files"] == ["app.desktop"]
        assert entry["icon_files"] == ["app-icon"]
        assert "nix_profile_key" not in entry

    @patch("app2nix.manifest.save_manifest")
    @patch("app2nix.manifest.load_manifest")
    def test_records_nix_profile_key(self, mock_load, mock_save):
        mock_load.return_value = {"packages": {}}
        manifest.record_install("my-pkg", [], [], nix_profile_key="nixpkgs#my-pkg")
        saved = mock_save.call_args[0][0]
        assert saved["packages"]["my-pkg"]["nix_profile_key"] == "nixpkgs#my-pkg"

    @patch("app2nix.manifest.save_manifest")
    @patch("app2nix.manifest.load_manifest")
    def test_merges_with_existing_entries(self, mock_load, mock_save):
        mock_load.return_value = {"packages": {"existing-pkg": {"desktop_files": ["old.desktop"]}}}
        manifest.record_install("new-pkg", ["new.desktop"], [])
        saved = mock_save.call_args[0][0]
        assert "existing-pkg" in saved["packages"]
        assert "new-pkg" in saved["packages"]

    @patch("app2nix.manifest.save_manifest")
    @patch("app2nix.manifest.load_manifest")
    def test_sanitizes_name(self, mock_load, mock_save):
        mock_load.return_value = {"packages": {}}
        manifest.record_install("My App With Spaces", [], [])
        saved = mock_save.call_args[0][0]
        assert "my-app-with-spaces" in saved["packages"]


class TestCleanupOrphanedEntries:
    @patch("app2nix.manifest.load_manifest")
    def test_returns_zero_when_no_tracked_packages(self, mock_load):
        mock_load.return_value = {"packages": {}}
        result = manifest.cleanup_orphaned_entries()
        assert result == 0

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_keeps_installed_packages(self, mock_load, mock_run):
        mock_load.return_value = {
            "packages": {
                "firefox": {"desktop_files": ["firefox.desktop"], "icon_files": ["firefox"]}
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({
                "elements": {
                    "firefox": {
                        "active": True,
                        "storePaths": ["/nix/store/abc123-firefox-128.0"],
                    }
                }
            })),
        ]
        with (
            patch("app2nix.manifest.save_manifest") as mock_save,
            patch.object(Path, "home", return_value=Path("/tmp")),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 0
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert "firefox" in saved["packages"]

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_cleans_orphaned_package(self, mock_load, mock_run, tmp_path):
        home = tmp_path / "home"
        desktop_dir = home / ".local" / "share" / "applications"
        icons_dir = home / ".local" / "share" / "icons"
        desktop_dir.mkdir(parents=True)
        icons_hicolor = icons_dir / "hicolor" / "48x48" / "apps"
        icons_hicolor.mkdir(parents=True)

        desktop_file = desktop_dir / "orphan.desktop"
        desktop_file.write_text("[Desktop Entry]")
        icon_file = icons_hicolor / "orphan.png"
        icon_file.write_text("fake icon")

        mock_load.return_value = {
            "packages": {
                "orphan-app": {
                    "desktop_files": ["orphan.desktop"],
                    "icon_files": ["orphan"],
                }
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"elements": {}})),
        ]

        with (
            patch("app2nix.manifest.save_manifest") as mock_save,
            patch.object(Path, "home", return_value=home),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 1
        assert not desktop_file.exists()
        assert not icon_file.exists()
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        assert "orphan-app" not in saved["packages"]

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_fallback_to_nix_env_when_profile_fails(self, mock_load, mock_run):
        mock_load.return_value = {
            "packages": {
                "hello": {"desktop_files": ["hello.desktop"], "icon_files": []}
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="hello-2.12.1\n"),
        ]
        with (
            patch("app2nix.manifest.save_manifest") as mock_save,
            patch.object(Path, "home", return_value=Path("/tmp")),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 0
        saved = mock_save.call_args[0][0]
        assert "hello" in saved["packages"]

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_both_nix_commands_fail(self, mock_load, mock_run, tmp_path):
        home = tmp_path / "home"
        mock_load.return_value = {
            "packages": {
                "gone-app": {"desktop_files": [], "icon_files": []}
            }
        }
        mock_run.side_effect = FileNotFoundError()
        with (
            patch("app2nix.manifest.save_manifest") as mock_save,
            patch.object(Path, "home", return_value=home),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 1
        mock_save.assert_called_once()

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_removes_legacy_glob_icons(self, mock_load, mock_run, tmp_path):
        home = tmp_path / "home"
        icon_dir = home / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        icon_dir.mkdir(parents=True)
        icon_file = icon_dir / "legacy-app.svg"
        icon_file.write_text("<svg/>")

        mock_load.return_value = {
            "packages": {
                "legacy-app": {
                    "desktop_files": [],
                    "icon_files": ["legacy-app.*"],
                }
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"elements": {}})),
        ]
        with (
            patch("app2nix.manifest.save_manifest"),
            patch.object(Path, "home", return_value=home),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 1
        assert not icon_file.exists()

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_refreshes_desktop_and_icon_cache(self, mock_load, mock_run, tmp_path):
        home = tmp_path / "home"
        mock_load.return_value = {
            "packages": {
                "gone": {"desktop_files": [], "icon_files": []}
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"elements": {}})),
        ]
        with (
            patch("app2nix.manifest.save_manifest"),
            patch.object(Path, "home", return_value=home),
        ):
            manifest.cleanup_orphaned_entries()
        assert mock_run.call_count >= 3

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_cache_refresh_errors_are_silent(self, mock_load, mock_run):
        mock_load.return_value = {
            "packages": {
                "gone": {"desktop_files": [], "icon_files": []}
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"elements": {}})),
            FileNotFoundError(),
            FileNotFoundError(),
        ]
        with (
            patch("app2nix.manifest.save_manifest"),
            patch.object(Path, "home", return_value=Path("/tmp")),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 1

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_multiple_orphans_cleaned(self, mock_load, mock_run, tmp_path):
        home = tmp_path / "home"
        mock_load.return_value = {
            "packages": {
                "app1": {"desktop_files": [], "icon_files": []},
                "app2": {"desktop_files": [], "icon_files": []},
                "app3": {"desktop_files": [], "icon_files": []},
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"elements": {}})),
        ]
        with (
            patch("app2nix.manifest.save_manifest"),
            patch.object(Path, "home", return_value=home),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 3

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_nix_profile_key_respects_attr_path(self, mock_load, mock_run):
        """nix_profile_key matching extracts package name after # for comparison."""
        mock_load.return_value = {
            "packages": {
                "firefox": {"desktop_files": [], "icon_files": [], "nix_profile_key": "nixpkgs#firefox"},
                "vscode": {"desktop_files": [], "icon_files": [], "nix_profile_key": "nixpkgs#vscode"},
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({
                "elements": {
                    "firefox": {
                        "attrPath": "nixpkgs#firefox",
                        "storePaths": ["/nix/store/abc-firefox-128.0"],
                    },
                    "vscode": {
                        "attrPath": "nixpkgs#vscode",
                        "storePaths": ["/nix/store/def-vscode-1.90.0"],
                    },
                }
            })),
        ]
        with (
            patch("app2nix.manifest.save_manifest") as mock_save,
            patch.object(Path, "home", return_value=Path("/tmp")),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 0
        saved = mock_save.call_args[0][0]["packages"]
        assert "firefox" in saved
        assert "vscode" in saved

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_profile_key_exact_match_keeps_installed(self, mock_load, mock_run):
        """When profile_key matches an element key directly, keep the package."""
        mock_load.return_value = {
            "packages": {
                "firefox": {"desktop_files": [], "icon_files": [], "nix_profile_key": "firefox"},
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({
                "elements": {
                    "firefox": {
                        "attrPath": "nixpkgs#firefox",
                        "storePaths": ["/nix/store/abc-firefox-128.0"],
                    },
                }
            })),
        ]
        with (
            patch("app2nix.manifest.save_manifest") as mock_save,
            patch.object(Path, "home", return_value=Path("/tmp")),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 0
        saved = mock_save.call_args[0][0]["packages"]
        assert "firefox" in saved

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_attr_path_with_hyphen_adds_base_name(self, mock_load, mock_run):
        """When attrPath contains a hyphen, the base name is also added to installed set."""
        mock_load.return_value = {
            "packages": {
                "google-chrome": {"desktop_files": [], "icon_files": [], "nix_profile_key": "nixpkgs#google-chrome"},
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({
                "elements": {
                    "google-chrome": {
                        "attrPath": "nixpkgs#google-chrome",
                        "storePaths": ["/nix/store/def-google-chrome-120.0"],
                    },
                }
            })),
        ]
        with (
            patch("app2nix.manifest.save_manifest") as mock_save,
            patch.object(Path, "home", return_value=Path("/tmp")),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 0
        saved = mock_save.call_args[0][0]["packages"]
        assert "google-chrome" in saved

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_orphan_when_key_does_not_match_attr_path(self, mock_load, mock_run, tmp_path):
        """Package with nix_profile_key that doesn't resolve to any installed
        element should be removed (orphaned)."""
        home = tmp_path / "home"
        mock_load.return_value = {
            "packages": {
                "removed-pkg": {
                    "desktop_files": [],
                    "icon_files": [],
                    "nix_profile_key": "nixpkgs#removed-pkg",
                }
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({
                "elements": {
                    "firefox": {
                        "attrPath": "nixpkgs#firefox",
                        "storePaths": ["/nix/store/abc-firefox-128.0"],
                    },
                }
            })),
        ]
        with (
            patch("app2nix.manifest.save_manifest") as mock_save,
            patch.object(Path, "home", return_value=home),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 1
        saved = mock_save.call_args[0][0]["packages"]
        assert "removed-pkg" not in saved

    @patch("app2nix.manifest.subprocess.run")
    @patch("app2nix.manifest.load_manifest")
    def test_orphan_with_no_desktop_files_does_not_fail(self, mock_load, mock_run, tmp_path):
        home = tmp_path / "home"
        mock_load.return_value = {
            "packages": {
                "headless-app": {"desktop_files": [], "icon_files": []}
            }
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"elements": {}})),
        ]
        with (
            patch("app2nix.manifest.save_manifest"),
            patch.object(Path, "home", return_value=home),
        ):
            result = manifest.cleanup_orphaned_entries()
        assert result == 1
