#!/usr/bin/env python3
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="app2nix",
    help="Convert Linux packages to NixOS expressions",
    rich_markup_mode="rich",
)
console = Console()


@app.command()
def convert(
    package: Path = typer.Argument(..., help="Package file (.deb, .rpm, .AppImage, ...)"),
    output_dir: Path = typer.Option(Path("."), "--output-dir", "-d", help="Output directory"),
    flake: bool = typer.Option(False, "--flake", "-f", help="Also generate flake.nix"),
    json_out: bool = typer.Option(False, "--json", help="Output JSON descriptor"),
    print_deps: bool = typer.Option(False, "--print-deps", help="Only print dependencies"),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Validate generated Nix"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    from app2nix.config import settings
    from app2nix.core.analyzer import UniversalAnalyzer
    from app2nix.core.generator import NixGenerator
    from app2nix.core.resolver import DependencyResolver

    if not package.exists():
        console.print(f"[red]File not found:[/red] {package}")
        raise typer.Exit(1)

    with console.status(f"[bold cyan]Analyzing {package.name}..."):
        analyzer = UniversalAnalyzer()
        info = analyzer.analyze(str(package))

    if print_deps:
        resolver = DependencyResolver(settings.cache_db.expanduser())
        resolved, unresolved = resolver.resolve_all(info.dependencies)

        table = Table(title=f"Dependencies for {info.name}")
        table.add_column("Library", style="cyan")
        table.add_column("Nixpkg", style="green")
        table.add_column("Status", style="bold")

        for lib, nix in zip(info.dependencies, resolved, strict=False):
            table.add_row(lib, nix, "OK")
        for lib in unresolved:
            table.add_row(lib, "-", "[red]unknown[/red]")

        console.print(table)
        return

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
        out_path = output_dir / f"{info.name}.json"
        out_path.write_text(json.dumps(json_result, indent=2))
        console.print(f"[green]Generated:[/green] {out_path}")
        return

    with console.status("[bold cyan]Generating Nix expression..."):
        generator = NixGenerator()
        result = generator.generate_default_nix(info)

        if validate and result.validation_error:
            console.print(Panel(
                f"[yellow]Validation warning:[/yellow]\n{result.validation_error}",
                title="Nix Validation",
            ))

    output_dir.mkdir(parents=True, exist_ok=True)
    nix_path = output_dir / "default.nix"
    nix_path.write_text(result.nix_content)
    console.print(f"[green]Generated:[/green] {nix_path}")

    if flake:
        flake_result = generator.generate_flake_nix(info)
        flake_path = output_dir / "flake.nix"
        flake_path.write_text(flake_result.nix_content)
        console.print(f"[green]Generated:[/green] {flake_path}")

    if result.unresolved_deps:
        console.print(Panel(
            "\n".join(f"  {d}" for d in result.unresolved_deps),
            title=f"[yellow]{len(result.unresolved_deps)} unresolved dependencies[/yellow]",
            subtitle="Consider adding to the dependency map",
        ))

    if verbose:
        console.print(Panel(
            f"Name: {info.name}\nVersion: {info.version}\n"
            f"Format: {info.format}\nArch: {info.architecture}\n"
            f"Libraries: {len(info.dependencies)}\n"
            f"Resolved: {len(info.dependencies) - len(result.unresolved_deps)}",
            title="Package Info",
        ))


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
    except ImportError as e:
        console.print(f"[red]PyQt6 not installed.[/red] Install with: pip install 'app2nix[gui]'")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
