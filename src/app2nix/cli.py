#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

app = typer.Typer(
    name="app2nix",
    help="Convert Linux packages to NixOS expressions",
    rich_markup_mode="rich",
)
console = Console()

# All extensions that detect_format() can recognise (used by directory scan).
_DETECTABLE_EXTS: set[str] = {
    ".deb", ".rpm", ".appimage", ".flatpak", ".snap",
    ".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tar.xz", ".txz", ".tbz2",
    ".zip", ".7z",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_packages(directory: Path, *, recursive: bool = False) -> list[Path]:
    """Return sorted list of supported package files inside *directory*."""
    from app2nix.core.analyzer import detect_format

    pattern = "**/*" if recursive else "*"
    found: list[Path] = []
    for p in directory.glob(pattern):
        if not p.is_file():
            continue
        if detect_format(p.name) is not None:
            found.append(p)
    return sorted(found)


def _convert_single(
    package: Path,
    *,
    output_dir: Path,
    flake: bool,
    json_out: bool,
    print_deps: bool,
    validate: bool,
    verbose: bool,
    quiet: bool = False,
) -> dict[str, object]:
    """Convert a single package file and return a result dict for batch tables.

    Returns ``{"path": Path, "status": "ok"|"error", "name": str, ...}``
    """
    from app2nix.core.analyzer import UniversalAnalyzer
    from app2nix.core.generator import NixGenerator
    from app2nix.core.resolver import DependencyResolver

    result: dict[str, object] = {"path": package, "status": "ok"}

    try:
        analyzer = UniversalAnalyzer()
        info = analyzer.analyze(str(package))

        result["name"] = info.name
        result["version"] = info.version
        result["format"] = info.format

        # --print-deps ---------------------------------------------------
        if print_deps:
            resolver = DependencyResolver()
            resolved, unresolved = resolver.resolve_all(info.dependencies)

            table = Table(title=f"Dependencies for {info.name}")
            table.add_column("Library", style="cyan")
            table.add_column("Nixpkg", style="green")
            table.add_column("Status", style="bold")
            for lib, nix in zip(info.dependencies, resolved, strict=False):
                table.add_row(lib, nix, "OK")
            for lib in unresolved:
                table.add_row(lib, "-", "[red]unknown[/red]")
            if not quiet:
                console.print(table)
            return result

        # --json ---------------------------------------------------------
        if json_out:
            import json as _json

            from app2nix.core.resolver import DEP_MAP

            nix_deps = [
                DEP_MAP.get(d[3:] if d.startswith("lib") else d, f"#{d}")
                for d in info.dependencies
            ]
            json_result = {
                "name": info.name,
                "version": info.version,
                "architecture": info.architecture,
                "dependencies": nix_deps,
                "libraries": info.dependencies,
            }
            out_path = output_dir / f"{info.name}.json"
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(_json.dumps(json_result, indent=2))
            if not quiet:
                console.print(f"[green]Generated:[/green] {out_path}")
            return result

        # default.nix ----------------------------------------------------
        generator = NixGenerator()
        gen_result = generator.generate_default_nix(info)

        if validate and gen_result.validation_error:
            if not quiet:
                console.print(Panel(
                    f"[yellow]Validation warning:[/yellow]\n{gen_result.validation_error}",
                    title="Nix Validation",
                ))

        output_dir.mkdir(parents=True, exist_ok=True)
        nix_path = output_dir / "default.nix"
        nix_path.write_text(gen_result.nix_content)
        if not quiet:
            console.print(f"[green]Generated:[/green] {nix_path}")

        if flake:
            flake_result = generator.generate_flake_nix(info)
            flake_path = output_dir / "flake.nix"
            flake_path.write_text(flake_result.nix_content)
            if not quiet:
                console.print(f"[green]Generated:[/green] {flake_path}")

        if gen_result.unresolved_deps:
            if not quiet:
                console.print(Panel(
                    "\n".join(f"  {d}" for d in gen_result.unresolved_deps),
                    title=f"[yellow]{len(gen_result.unresolved_deps)} unresolved dependencies[/yellow]",
                    subtitle="Consider adding to the dependency map",
                ))

        if verbose and not quiet:
            console.print(Panel(
                f"Name: {info.name}\nVersion: {info.version}\n"
                f"Format: {info.format}\nArch: {info.architecture}\n"
                f"Libraries: {len(info.dependencies)}\n"
                f"Resolved: {len(info.dependencies) - len(gen_result.unresolved_deps)}",
                title="Package Info",
            ))

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        if not quiet:
            console.print(f"[red]Error processing {package.name}:[/red] {exc}")

    return result


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def convert(
    package: str = typer.Argument(..., help="Package file or directory (.deb, .rpm, .AppImage, ...)"),
    output_dir: str = typer.Option(".", "--output-dir", "-d", help="Output directory"),
    flake: bool = typer.Option(False, "--flake", "-f", help="Also generate flake.nix"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON descriptor"),
    print_deps: bool = typer.Option(False, "--print-deps", help="Only print dependencies"),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Validate generated Nix"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Recursively scan subdirectories when INPUT is a directory"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="Number of parallel workers (batch mode)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output"),
):
    """Convert Linux packages to NixOS expressions.

    Accepts a single file, a glob pattern, or a **directory**.  When a
    directory is given, all supported packages inside it are processed
    automatically (use ``--recursive`` to include subdirectories).
    """
    from app2nix.core.analyzer import detect_format

    package_path = Path(package)
    output_path = Path(output_dir)

    # ── Resolve input to a list of package paths ──────────────────────
    if package_path.is_dir():
        # Directory mode: scan for supported packages
        packages = _find_packages(package_path, recursive=recursive)
        if not packages:
            if not quiet:
                console.print(
                    f"[yellow]No supported packages found in[/yellow] {package_path}"
                )
            raise typer.Exit(1)
        if not quiet:
            console.print(
                f"[cyan]Found {len(packages)} package(s) in {package_path}[/cyan]"
            )
    elif package_path.is_file():
        # Single file
        if detect_format(package_path.name) is None:
            if not quiet:
                console.print(f"[red]Unsupported format:[/red] {package_path.suffix}")
            raise typer.Exit(1)
        packages = [package_path]
    else:
        if not quiet:
            console.print(f"[red]Not found:[/red] {package_path}")
        raise typer.Exit(1)

    # ── Batch mode (more than one package OR --parallel > 1) ──────────
    if len(packages) > 1:
        _run_batch(
            packages,
            output_dir=output_path,
            flake=flake,
            json_out=json_out,
            print_deps=print_deps,
            validate=validate,
            verbose=verbose,
            parallel=parallel,
            quiet=quiet,
        )
        return

    # ── Single-file mode ──────────────────────────────────────────────
    pkg = packages[0]
    status_msg = f"[bold cyan]Analyzing {pkg.name}...[/bold cyan]" if not quiet else ""
    with console.status(status_msg) if not quiet else nullcontext():
        _convert_single(
            pkg,
            output_dir=output_path,
            flake=flake,
            json_out=json_out,
            print_deps=print_deps,
            validate=validate,
            verbose=verbose,
            quiet=quiet,
        )


def _run_batch(
    packages: list[Path],
    *,
    output_dir: Path,
    flake: bool,
    json_out: bool,
    print_deps: bool,
    validate: bool,
    verbose: bool,
    parallel: int,
    quiet: bool = False,
):
    """Process a list of packages, optionally in parallel with a Rich progress bar."""
    results: list[dict[str, object]] = []
    total = len(packages)

    def _task(pkg: Path) -> dict[str, object]:
        return _convert_single(
            pkg,
            output_dir=output_dir,
            flake=flake,
            json_out=json_out,
            print_deps=print_deps,
            validate=validate,
            verbose=verbose,
            quiet=True,
        )

    if quiet:
        # Silent mode: no progress bar, just process
        if parallel > 1:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = [pool.submit(_task, p) for p in packages]
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for pkg in packages:
                results.append(_task(pkg))
    else:
        # Normal mode: show Rich progress bar with ETA, bar, elapsed
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Converting packages…", total=total)

            if parallel > 1:
                with ThreadPoolExecutor(max_workers=parallel) as pool:
                    fut_to_idx: dict = {}
                    for i, pkg in enumerate(packages):
                        progress.update(task_id, description=f"[blue]{pkg.name}[/blue]")
                        fut = pool.submit(_task, pkg)
                        fut_to_idx[fut] = i

                    for future in as_completed(fut_to_idx):
                        results.append(future.result())
                        progress.advance(task_id)
            else:
                for pkg in packages:
                    progress.update(task_id, description=f"[blue]{pkg.name}[/blue]")
                    results.append(_task(pkg))
                    progress.advance(task_id)

        # ── Summary table ─────────────────────────────────────────────
        table = Table(title=f"Batch results — {total} package(s)")
        table.add_column("File", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Version")
        table.add_column("Format")
        table.add_column("Status", style="bold")

        ok = err = 0
        for r in results:
            name = str(r.get("name", "-"))
            version = str(r.get("version", "-"))
            fmt = str(r.get("format", "-"))
            status = r.get("status", "error")
            p = r.get("path", "-")
            if isinstance(p, Path):
                p = p.name
            if status == "ok":
                ok += 1
                table.add_row(
                    str(p), name, version, fmt,
                    "[green]ok[/green]",
                )
            else:
                err += 1
                table.add_row(
                    str(p), name, version, fmt,
                    f"[red]{r.get('error', 'error')}[/red]",
                )

        console.print(table)
        console.print(f"[green]{ok} succeeded[/green], [red]{err} failed[/red]")


# ---------------------------------------------------------------------------
# Other commands
# ---------------------------------------------------------------------------

@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Port"),
    reload: bool = typer.Option(False, help="Auto-reload"),
):
    import uvicorn
    uvicorn.run("app2nix.server:app", host=host, port=port, reload=reload)


@app.command()
def gui():
    """Launch the Qt6 graphical interface (requires PyQt6)."""
    try:
        from app2nix.gui import run_gui
        run_gui()
    except ImportError:
        console.print("[red]PyQt6 not installed.[/red] Install with: pip install 'app2nix[gui]'")
        raise typer.Exit(1) from None


@app.command()
def cleanup(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show which packages were cleaned"),
):
    """Remove orphaned .desktop files and icons from previously uninstalled packages.

    Checks the app2nix manifest against the current Nix profile and removes
    desktop entries and icon files for packages that are no longer installed.
    """
    from app2nix.manifest import cleanup_orphaned_entries, load_manifest

    manifest = load_manifest()
    tracked = manifest.get("packages", {})
    if not tracked:
        console.print("[green]No tracked packages — nothing to clean.[/green]")
        return

    console.print(
        f"[cyan]Checking {len(tracked)} tracked package(s) against Nix profile…[/cyan]"
    )
    cleaned = cleanup_orphaned_entries()

    if cleaned:
        console.print(
            f"[green]Cleaned {cleaned} orphaned package(s).[/green]"
        )
    else:
        console.print("[green]All tracked packages are still installed — nothing to clean.[/green]")


if __name__ == "__main__":
    app()
