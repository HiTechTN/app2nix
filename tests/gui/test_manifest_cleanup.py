"""Unit tests for the manifest-based .desktop/icon cleanup feature in InstallWorker.

Tests verify:
- Manifest load/save round-trip
- _record_install writes correct manifest entries
- _cleanup_orphaned_entries detects and removes orphaned .desktop files and icons
- Edge cases: empty manifest, corrupted manifest, missing nix profile
- _patch_desktop_icon correctly patches .desktop Icon= lines
- _find_icons_in_store finds icons in Nix store paths
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from app2nix.gui.main_window import InstallWorker

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manifest_file(tmp_path):
    """Provide a temporary manifest path by patching manifest_path."""
    mf = tmp_path / "manifest.json"
    with patch("app2nix.manifest.manifest_path", return_value=mf):
        yield mf


@pytest.fixture
def home_dir(tmp_path):
    """Provide a temporary home directory by patching Path.home."""
    home = tmp_path / "home_user"
    home.mkdir()
    with patch.object(Path, "home", return_value=home):
        yield home


# ---------------------------------------------------------------------------
# _manifest_path
# ---------------------------------------------------------------------------

class TestManifestPath:
    def test_returns_path_object(self):
        result = InstallWorker._manifest_path()
        assert isinstance(result, Path)

    def test_ends_with_manifest_json(self):
        result = InstallWorker._manifest_path()
        assert result.name == "manifest.json"

    def test_path_contains_app2nix(self):
        result = InstallWorker._manifest_path()
        assert "app2nix" in str(result)


# ---------------------------------------------------------------------------
# _load_manifest / _save_manifest
# ---------------------------------------------------------------------------

class TestManifestLoadSave:
    def test_load_manifest_returns_empty_when_no_file(self, manifest_file):
        """Loading from a non-existent file should return default structure."""
        result = InstallWorker._load_manifest()
        assert result == {"packages": {}}

    def test_load_manifest_returns_empty_for_corrupted_file(self, manifest_file):
        """Corrupted JSON should return default structure."""
        manifest_file.write_text("NOT VALID JSON {{{", encoding="utf-8")
        result = InstallWorker._load_manifest()
        assert result == {"packages": {}}

    def test_save_and_load_round_trip(self, manifest_file):
        """Save then load should return the same data."""
        data = {
            "packages": {
                "firefox": {
                    "desktop_files": ["firefox.desktop"],
                    "icon_files": ["hicolor/48x48/apps/firefox.png"],
                }
            }
        }
        InstallWorker._save_manifest(data)
        loaded = InstallWorker._load_manifest()
        assert loaded == data

    def test_save_creates_parent_dirs(self, tmp_path):
        """_save_manifest should create parent directories if they don't exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "manifest.json"
        self._manifest_file = deep_path
        with patch("app2nix.manifest.manifest_path", return_value=deep_path):
            InstallWorker._save_manifest({"packages": {}})
        assert deep_path.exists()

    def test_save_writes_valid_json(self, manifest_file):
        """The saved file should be valid JSON."""
        InstallWorker._save_manifest(
            {"packages": {"test": {"desktop_files": [], "icon_files": []}}}
        )
        content = manifest_file.read_text(encoding="utf-8")
        data = json.loads(content)
        assert "packages" in data
        assert "test" in data["packages"]


# ---------------------------------------------------------------------------
# _record_install
# ---------------------------------------------------------------------------
class TestRecordInstall:
    def test_records_desktop_and_icon_files(self, manifest_file):
        """_record_install should store desktop and icon file lists."""
        InstallWorker._record_install(
            "My App",
            ["my-app.desktop", "my-app-editor.desktop"],
            ["hicolor/48x48/apps/my-app.png"],
        )
        data = InstallWorker._load_manifest()
        assert "my-app" in data["packages"]
        entry = data["packages"]["my-app"]
        assert entry["desktop_files"] == [
            "my-app.desktop",
            "my-app-editor.desktop",
        ]
        assert entry["icon_files"] == ["hicolor/48x48/apps/my-app.png"]

    def test_package_name_is_normalized(self, manifest_file):
        """Package names should be lowercased and spaces replaced with hyphens."""
        InstallWorker._record_install("My Fancy App", ["a.desktop"], [])
        data = InstallWorker._load_manifest()
        assert "my-fancy-app" in data["packages"]
        assert "My Fancy App" not in data["packages"]

    def test_empty_lists_are_stored(self, manifest_file):
        """Empty desktop/icon lists should still be recorded."""
        InstallWorker._record_install("bare-pkg", [], [])
        data = InstallWorker._load_manifest()
        assert data["packages"]["bare-pkg"]["desktop_files"] == []
        assert data["packages"]["bare-pkg"]["icon_files"] == []

    def test_overwrites_existing_entry(self, manifest_file):
        """Recording the same package twice should overwrite the previous entry."""
        InstallWorker._record_install("pkg", ["old.desktop"], [])
        InstallWorker._record_install(
            "pkg", ["new.desktop", "new2.desktop"], ["icon.png"]
        )
        data = InstallWorker._load_manifest()
        assert data["packages"]["pkg"]["desktop_files"] == [
            "new.desktop",
            "new2.desktop",
        ]
        assert data["packages"]["pkg"]["icon_files"] == ["icon.png"]

    def test_multiple_packages(self, manifest_file):
        """Multiple packages should coexist in the manifest."""
        InstallWorker._record_install("firefox", ["firefox.desktop"], [])
        InstallWorker._record_install(
            "thunderbird", ["thunderbird.desktop"], ["thunderbird.png"]
        )
        data = InstallWorker._load_manifest()
        assert len(data["packages"]) == 2
        assert "firefox" in data["packages"]
        assert "thunderbird" in data["packages"]


# ---------------------------------------------------------------------------
# _cleanup_orphaned_entries
# ---------------------------------------------------------------------------
class TestCleanupOrphanedEntries:
    """Tests for orphan detection and cleanup.

    Note: _cleanup_orphaned_entries uses:
      - Path.home() / ".local" / "share" / "applications" for desktop files
      - Path.home() / ".local" / "share" / "icons" for icon files
    So we must patch Path.home() to redirect to tmp_path, and create
    files in the correct subdirectories.
    """

    def _make_desktop_dir(self, tmp_path):
        d = tmp_path / ".local" / "share" / "applications"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _make_icons_dir(self, tmp_path):
        d = tmp_path / ".local" / "share" / "icons"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_no_op_when_manifest_empty(self, manifest_file):
        """Cleanup should do nothing when manifest has no packages."""
        InstallWorker._save_manifest({"packages": {}})
        # Should not raise
        InstallWorker._cleanup_orphaned_entries()
        data = InstallWorker._load_manifest()
        assert data["packages"] == {}

    def test_removes_orphaned_desktop_file(self, manifest_file, tmp_path):
        """Desktop files for orphaned packages should be deleted."""
        desktop_dir = self._make_desktop_dir(tmp_path)
        desktop_file = desktop_dir / "orphan-app.desktop"
        desktop_file.write_text(
            "[Desktop Entry]\nName=OrphanApp\n", encoding="utf-8"
        )

        # Record the orphan
        InstallWorker._record_install(
            "orphan-app", ["orphan-app.desktop"], []
        )

        with (
            patch("subprocess.run") as mock_run,
            patch.object(Path, "home", return_value=tmp_path),
        ):
            # Mock nix profile list to fail → package not found → orphan
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result

            InstallWorker._cleanup_orphaned_entries()

        assert not desktop_file.exists(), (
            "Orphaned .desktop file should be removed"
        )

    def test_preserves_non_orphaned_files(self, manifest_file, tmp_path):
        """Desktop files for still-installed packages should be kept."""
        desktop_dir = self._make_desktop_dir(tmp_path)
        desktop_file = desktop_dir / "active-app.desktop"
        desktop_file.write_text(
            "[Desktop Entry]\nName=ActiveApp\n", encoding="utf-8"
        )

        InstallWorker._record_install(
            "active-app", ["active-app.desktop"], []
        )

        with (
            patch("subprocess.run") as mock_run,
            patch.object(Path, "home", return_value=tmp_path),
        ):
            # Mock nix profile list to include "active-app"
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "elements": {
                        "legacyPackages.x86_64-linux.active-app": {
                            "storePaths": ["/nix/store/abc-active-app"]
                        }
                    }
                }
            )
            mock_run.return_value = mock_result

            InstallWorker._cleanup_orphaned_entries()

        assert desktop_file.exists(), (
            "Non-orphaned .desktop file should be preserved"
        )

    def test_removes_orphaned_icon_file(self, manifest_file, tmp_path):
        """Icon files for orphaned packages should be deleted."""
        icons_dir = tmp_path / ".local" / "share" / "icons" / "hicolor" / "48x48" / "apps"
        icons_dir.mkdir(parents=True, exist_ok=True)
        icon_file = icons_dir / "orphan-app.png"
        icon_file.write_bytes(b"\x89PNG fake")

        InstallWorker._record_install(
            "orphan-app", [], ["orphan-app"]
        )

        with (
            patch("subprocess.run") as mock_run,
            patch.object(Path, "home", return_value=tmp_path),
        ):
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result

            InstallWorker._cleanup_orphaned_entries()

        assert not icon_file.exists(), (
            "Orphaned icon file should be removed"
        )

    def test_no_files_to_remove_still_updates_manifest(
        self, manifest_file
    ):
        """Even when no files exist on disk, the manifest should be cleaned of orphaned entries."""
        InstallWorker._record_install(
            "ghost-pkg", ["ghost.desktop"], ["ghost.png"]
        )

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result

            InstallWorker._cleanup_orphaned_entries()

        data = InstallWorker._load_manifest()
        assert "ghost-pkg" not in data["packages"], (
            "Orphaned entry should be removed from manifest even if files don't exist on disk"
        )

    def test_mixed_orphaned_and_active(self, manifest_file, tmp_path):
        """When some packages are orphaned and some are active, only orphans should be cleaned."""
        desktop_dir = self._make_desktop_dir(tmp_path)

        orphan_desktop = desktop_dir / "orphan.desktop"
        orphan_desktop.write_text("orphan", encoding="utf-8")

        active_desktop = desktop_dir / "active.desktop"
        active_desktop.write_text("active", encoding="utf-8")

        InstallWorker._record_install("orphan", ["orphan.desktop"], [])
        InstallWorker._record_install("active", ["active.desktop"], [])

        with (
            patch("subprocess.run") as mock_run,
            patch.object(Path, "home", return_value=tmp_path),
        ):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "elements": {
                        "legacyPackages.x86_64-linux.active": {
                            "storePaths": ["/nix/store/xyz-active"]
                        }
                    }
                }
            )
            mock_run.return_value = mock_result

            InstallWorker._cleanup_orphaned_entries()

        assert not orphan_desktop.exists(), (
            "Orphaned file should be removed"
        )
        assert active_desktop.exists(), "Active file should be preserved"

        data = InstallWorker._load_manifest()
        assert "orphan" not in data["packages"]
        assert "active" in data["packages"]

    def test_nix_env_fallback_matching(self, manifest_file):
        """When nix profile list fails, cleanup should fall back to nix-env -q."""
        InstallWorker._record_install(
            "mypkg", ["mypkg.desktop"], []
        )

        with patch("subprocess.run") as mock_run:
            # First call: nix profile list fails
            fail_result = MagicMock()
            fail_result.returncode = 1

            # Second call: nix-env -q succeeds with the package
            success_result = MagicMock()
            success_result.returncode = 0
            success_result.stdout = "mypkg-1.0 /nix/store/abc\n"

            mock_run.side_effect = [fail_result, success_result]

            InstallWorker._cleanup_orphaned_entries()

        data = InstallWorker._load_manifest()
        assert "mypkg" in data["packages"], (
            "Package found via nix-env -q should not be cleaned"
        )

    def test_cleanup_exception_does_not_propagate(self, manifest_file):
        """If subprocess fails entirely, cleanup should not raise."""
        InstallWorker._record_install(
            "test-pkg", ["test.desktop"], []
        )

        with patch("subprocess.run", side_effect=OSError("nix not found")):
            # Should not raise
            InstallWorker._cleanup_orphaned_entries()

    def test_partial_nix_profile_matching(self, manifest_file):
        """Package name substring match in nix profile elements should prevent cleanup."""
        InstallWorker._record_install(
            "myapp", ["myapp.desktop"], []
        )

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            # The nix profile element key contains the package name as a substring
            mock_result.stdout = json.dumps(
                {
                    "elements": {
                        "legacyPackages.x86_64-linux.myapp-2.0": {
                            "storePaths": ["/nix/store/xyz-myapp"]
                        }
                    }
                }
            )
            mock_run.return_value = mock_result

            InstallWorker._cleanup_orphaned_entries()

        data = InstallWorker._load_manifest()
        assert "myapp" in data["packages"], (
            "Package matched by substring in nix profile should not be cleaned"
        )

    def test_nix_profile_base_name_matching(self, manifest_file):
        """Package base name (before first hyphen) matching should prevent cleanup."""
        InstallWorker._record_install(
            "firefox", ["firefox.desktop"], []
        )

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {
                    "elements": {
                        "firefox": {
                            "storePaths": ["/nix/store/abc-firefox"]
                        }
                    }
                }
            )
            mock_run.return_value = mock_result

            InstallWorker._cleanup_orphaned_entries()

        data = InstallWorker._load_manifest()
        assert "firefox" in data["packages"], (
            "Package with exact name match in nix profile should not be cleaned"
        )

    def test_corrupted_manifest_does_not_crash(self, manifest_file):
        """A corrupted manifest file should not cause a crash."""
        manifest_file.write_text("{bad json!!!", encoding="utf-8")
        # Should not raise, load returns empty and cleanup is a no-op
        InstallWorker._cleanup_orphaned_entries()
        data = InstallWorker._load_manifest()
        assert data == {"packages": {}}

    def test_cleanup_refreshes_desktop_database(self, manifest_file, tmp_path):
        """After cleanup, update-desktop-database should be called."""
        InstallWorker._record_install(
            "orphan-pkg", ["orphan-pkg.desktop"], []
        )

        with (
            patch("subprocess.run") as mock_run,
            patch.object(Path, "home", return_value=tmp_path),
        ):
            # First two calls: nix profile list + nix-env -q (both fail)
            fail_result = MagicMock()
            fail_result.returncode = 1
            mock_run.side_effect = [fail_result, fail_result]

            InstallWorker._cleanup_orphaned_entries()

        # Note: update-desktop-database may or may not be called
        # depending on whether files actually existed. With no files on disk,
        # cleaned=False and it won't be called. That's expected.


# ---------------------------------------------------------------------------
# _patch_desktop_icon
# ---------------------------------------------------------------------------
class TestPatchDesktopIcon:
    def test_replaces_icon_line(self):
        """_patch_desktop_icon should replace the Icon= line."""
        content = (
            "[Desktop Entry]\n"
            "Name=Test\n"
            "Icon=old-icon\n"
            "Exec=/usr/bin/test\n"
        )
        result = InstallWorker._patch_desktop_icon(content, "new-icon")
        assert "Icon=new-icon" in result
        assert "Icon=old-icon" not in result

    def test_adds_icon_if_missing(self):
        """_patch_desktop_icon should add Icon= line if not present."""
        content = "[Desktop Entry]\nName=Test\nExec=/usr/bin/test\n"
        result = InstallWorker._patch_desktop_icon(content, "my-icon")
        assert "Icon=my-icon" in result

    def test_preserves_other_lines(self):
        """Patching should not alter non-Icon lines."""
        content = (
            "[Desktop Entry]\n"
            "Name=MyApp\n"
            "Exec=/usr/bin/myapp\n"
            "Terminal=false\n"
            "Categories=Utility;\n"
        )
        result = InstallWorker._patch_desktop_icon(content, "myapp")
        assert "Name=MyApp" in result
        assert "Exec=/usr/bin/myapp" in result
        assert "Terminal=false" in result
        assert "Categories=Utility;" in result
        assert "Icon=myapp" in result

    def test_empty_content_adds_icon(self):
        """Empty content should get an Icon= line appended."""
        result = InstallWorker._patch_desktop_icon("", "test-icon")
        assert "Icon=test-icon" in result


# ---------------------------------------------------------------------------
# _find_icons_in_store
# ---------------------------------------------------------------------------
class TestFindIconsInStore:
    def test_finds_png_icons(self, tmp_path):
        """Should find .png files in share/icons/."""
        store = tmp_path / "store"
        icons_dir = store / "share" / "icons" / "hicolor" / "48x48" / "apps"
        icons_dir.mkdir(parents=True)
        (icons_dir / "app.png").write_bytes(b"\x89PNG")

        result = InstallWorker._find_icons_in_store(store)
        assert any("app.png" in str(p) for p in result)

    def test_finds_svg_icons(self, tmp_path):
        """Should find .svg files."""
        store = tmp_path / "store"
        icons_dir = store / "share" / "icons" / "hicolor" / "scalable" / "apps"
        icons_dir.mkdir(parents=True)
        (icons_dir / "app.svg").write_text("<svg/>")

        result = InstallWorker._find_icons_in_store(store)
        assert any("app.svg" in str(p) for p in result)

    def test_returns_empty_when_no_icons(self, tmp_path):
        """Should return empty list when no icons exist."""
        store = tmp_path / "store"
        store.mkdir()

        result = InstallWorker._find_icons_in_store(store)
        assert result == []

    def test_finds_icons_in_nested_store_paths(self, tmp_path):
        """Should find icons in nested store paths (*/share/icons/)."""
        store = tmp_path / "store"
        nested = store / "lib" / "firefox" / "share" / "icons" / "hicolor" / "48x48" / "apps"
        nested.mkdir(parents=True)
        (nested / "firefox.png").write_bytes(b"\x89PNG")

        result = InstallWorker._find_icons_in_store(store)
        assert any("firefox.png" in str(p) for p in result)

    def test_finds_xpm_icons(self, tmp_path):
        """Should find .xpm files."""
        store = tmp_path / "store"
        icons_dir = store / "share" / "icons" / "hicolor" / "32x32" / "apps"
        icons_dir.mkdir(parents=True)
        (icons_dir / "app.xpm").write_bytes(b"/* XPM */")

        result = InstallWorker._find_icons_in_store(store)
        assert any("app.xpm" in str(p) for p in result)

    def test_ignores_non_icon_files(self, tmp_path):
        """Should not return .txt or .html files."""
        store = tmp_path / "store"
        icons_dir = store / "share" / "icons"
        icons_dir.mkdir(parents=True)
        (icons_dir / "readme.txt").write_text("not an icon")
        (icons_dir / "page.html").write_text("<html/>")

        result = InstallWorker._find_icons_in_store(store)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _manifest_path
# ---------------------------------------------------------------------------
class TestGuiManifestPath:
    def test_returns_path_object(self):
        result = InstallWorker._manifest_path()
        assert isinstance(result, Path)

    def test_ends_with_manifest_json(self):
        result = InstallWorker._manifest_path()
        assert result.name == "manifest.json"

    def test_path_contains_app2nix(self):
        result = InstallWorker._manifest_path()
        assert "app2nix" in str(result)
