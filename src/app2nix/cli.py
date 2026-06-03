#!/usr/bin/env python3
from __future__ import annotations

import glob as _glob
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="app2nix",
    help="Convert Linux packages to NixOS expressions",
    rich_markup_mode="rich",
)
console = Console()


_GLOB_CHARS = set("*?[")


def _resolve_packages(raw: list[str]) -> list[Path]:
    """Expand glob patterns and return a sorted list of unique, existing files.

    Literal paths (without glob characters) are always included so that
    the "File not found" error fires later.  Glob patterns that match
    nothing are silently dropped.
    """
    seen: set[Path] = set()
    result: list[Path] = []
    for pattern in raw:
        has_glob = bool(_GLOB_CHARS & set(pattern))
        expanded = _glob.glob(pattern, recursive=False)
        if expanded:
            for match in expanded:
                p = Path(match).resolve()
                if p.is_file() and p not in seen:
                    seen.add(p)
                    result.append(p)
        elif not has_glob:
            # Literal path — include so the 'not found' error fires later
            p = Path(pattern).resolve()
            if p not in seen:
                seen.add(p)
                result.append(p)
    return sorted(result)


def _convert_single(
    package: Path,
    output_dir: Path,
    *,
    flake: bool = False,
    json_out: bool = False,
    print_deps: bool = False,
    validate: bool = True,
    verbose: bool = False,
    quiet: bool = False,
) -> tuple[bool, str]:
    """Convert a single package.  Returns (success, message).

    When *quiet* is ``True``, all Rich console output is suppressed
    (useful during parallel batch execution).
    """
    from app2nix.core.analyzer import UniversalAnalyzer
    from app2nix.core.generator import NixGenerator
    from app2nix.core.resolver import DependencyResolver

    _print = (lambda *a, **kw: None) if quiet else console.print
    _panel = (lambda *a, **kw: None) if quiet else (lambda *a, **kw: _print(Panel(*a, **kw)))

    if not package.exists():
        msg = f"File not found: {package}"
        _print(f"[red]{msg}[/red]")
        return False, msg

    try:
        analyzer = UniversalAnalyzer()
        info = analyzer.analyze(str(package))
    except Exception as exc:
        msg = f"Analysis failed for {package.name}: {exc}"
        _print(f"[red]{msg}[/red]")
        return False, msg

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

        _print(table)
        return True, f"{info.name}: deps printed"

    if json_out:
        import json

        from app2nix.core.resolver import DEP_MAP
        nix_deps = []
        for d in info.dependencies:
            nix_deps.append(DEP_MAP.get(d[3:] if d.startswith("lib") else d, f"#{d}"))
        json_result = {
            "name": info.name,
            "version": info.version,
            "architecture": info.architecture,
            "dependencies": nix_deps,
            "libraries": info.dependencies,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{info.name}.json"
        out_path.write_text(json.dumps(json_result, indent=2))
        _print(f"[green]Generated:[/green] {out_path}")
        return True, f"{info.name}: JSON generated"

    try:
        generator = NixGenerator()
        result = generator.generate_default_nix(info)

        if validate and result.validation_error:
            _panel(
                f"[yellow]Validation warning:[/yellow]\n{result.validation_error}",
                title="Nix Validation",
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        nix_path = output_dir / "default.nix"
        nix_path.write_text(result.nix_content)
        _print(f"[green]Generated:[/green] {nix_path}")

        if flake:
            flake_result = generator.generate_flake_nix(info)
            flake_path = output_dir / "flake.nix"
            flake_path.write_text(flake_result.nix_content)
            _print(f"[green]Generated:[/green] {flake_path}")

        if result.unresolved_deps:
            _panel(
                "\n".join(f"  {d}" for d in result.unresolved_deps),
                title=f"[yellow]{len(result.unresolved_deps)} unresolved dependencies[/yellow]",
                subtitle="Consider adding to the dependency map",
            )

        if verbose:
            _panel(
                f"Name: {info.name}\nVersion: {info.version}\n"
                f"Format: {info.format}\nArch: {info.architecture}\n"
                f"Libraries: {len(info.dependencies)}\n"
                f"Resolved: {len(info.dependencies) - len(result.unresolved_deps)}",
                title="Package Info",
            )

        n_unresolved = len(result.unresolved_deps)
        msg = f"{info.name} v{info.version}"
        if n_unresolved:
            msg += f" ({n_unresolved} unresolved)"
        return True, msg

    except Exception as exc:
        msg = f"Generation failed for {package.name}: {exc}"
        _print(f"[red]{msg}[/red]")
        return False, msg


@app.command()
def convert(
    packages: list[str] = typer.Argument(
        ..., help="Package file(s) or glob pattern(s) (.deb, .rpm, .AppImage, ...)"
    ),
    output_dir: Path = typer.Option(Path("."), "--output-dir", "-d", help="Output directory"),
    flake: bool = typer.Option(False, "--flake", "-f", help="Also generate flake.nix"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON descriptor"),
    print_deps: bool = typer.Option(False, "--print-deps", help="Only print dependencies"),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Validate generated Nix"),
    parallel: int = typer.Option(1, "--parallel", "-j", help="Number of parallel workers (batch mode)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Convert one or more Linux packages to Nix expressions.

    Supports glob patterns: ``app2nix convert *.deb``
    Multiple files are processed in one go, each getting its own subdirectory.
    Use ``--parallel N`` to convert packages in parallel.
    """
    resolved = _resolve_packages(packages)

    if not resolved:
        console.print("[red]No matching packages found.[/red]")
        raise typer.Exit(1)

    is_batch = len(resolved) > 1

    if is_batch:
        console.print(f"\n[bold cyan]📦 Batch convert: {len(resolved)} packages[/bold cyan]\n")

    succeeded = 0
    failed = 0
    results: list[tuple[str, bool, str]] = []  # (filename, ok, message)

    use_parallel = is_batch and parallel > 1

    if use_parallel:
        console.print(f"\n[bold cyan]⚡ Parallel mode: {parallel} workers[/bold cyan]\n")

        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {}
            for pkg in resolved:
                pkg_out = output_dir / pkg.stem
                future = pool.submit(
                    _convert_single,
                    pkg, pkg_out,
                    flake=flake, json_out=json_out,
                    print_deps=print_deps, validate=validate,
                    verbose=verbose,
                    quiet=True,
                )
                futures[future] = pkg.name

            for future in as_completed(futures):
                pkg_name = futures[future]
                try:
                    ok, msg = future.result()
                except Exception as exc:
                    ok, msg = False, f"{pkg_name}: {exc}"
                if ok:
                    succeeded += 1
                else:
                    failed += 1
                results.append((pkg_name, ok, msg))
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=not is_batch,
        ) as progress:
            task = progress.add_task("Converting...", total=len(resolved)) if is_batch else None

            for pkg in resolved:
                if is_batch:
                    pkg_out = output_dir / pkg.stem
                    progress.update(task, description=f"Analyzing {pkg.name}...")
                else:
                    pkg_out = output_dir

                ok, msg = _convert_single(
                    pkg,
                    pkg_out,
                    flake=flake,
                    json_out=json_out,
                    print_deps=print_deps,
                    validate=validate,
                    verbose=verbose,
                )

                if ok:
                    succeeded += 1
                else:
                    failed += 1
                results.append((pkg.name, ok, msg))

                if is_batch:
                    progress.advance(task)

    # --- Summary for batch mode ---
    if is_batch:
        console.print()
        summary = Table(title="Batch Conversion Summary")
        summary.add_column("Package", style="cyan")
        summary.add_column("Status", justify="center")
        summary.add_column("Details")

        for name, ok, msg in results:
            status = "[green]✓[/green]" if ok else "[red]✗[/red]"
            summary.add_row(name, status, msg)

        console.print(summary)
        console.print(
            f"\n[bold]Result: [/bold]"
            f"[green]{succeeded} succeeded[/green], "
            f"[red]{failed} failed[/red] "
            f"out of {len(resolved)} total"
        )

        if failed > 0:
            raise typer.Exit(1)
    elif failed > 0:
        raise typer.Exit(1)


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


if __name__ == "__main__":
    app()
