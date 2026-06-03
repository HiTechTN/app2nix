# Roadmap — app2nix v3.1.0

> **Status** : Planning  
> **Target** : ~9 semaines  
> **Version actuelle** : v3.0.2 (189 unit tests, 113 integration tests, 89% coverage)

---

## 🎯 Objectifs v3.1.0

Transformer app2nix d'un outil de conversion individuel en une plateforme de conversion de masse, avec un Rust CLI performant et une expérience web enrichie.

---

## M1 — Batch CLI + Nouveaux formats (2 semaines)

### Features
| Feature | Description | Priorité |
|---------|-------------|----------|
| **Batch conversion** | `app2nix convert *.deb` — convertir plusieurs paquets en une commande | 🔥 Haute |
| **.zip support** | Nouvel analyseur pour archives ZIP (très courant) | 🔥 Haute |
| **.7z support** | Nouvel analyseur pour archives 7-Zip | 🟡 Moyenne |
| **Progress bar** | Barre de progression pour les conversions batch | 🟡 Moyenne |

### Livrables
- [ ] Modifier `cli.py` pour accepter des glob patterns et des répertoires
- [ ] Créer `src/app2nix/core/analyzers/zipfile_analyzer.py`
- [ ] Créer `src/app2nix/core/analyzers/sevenz_analyzer.py`
- [ ] Ajouter tests unitaires pour les nouveaux analyseurs
- [ ] Mettre à jour `SUPPORTED_FORMATS` dans `analyzer.py`

---

## M2 — WebSocket Progress + Batch Web UI (2 semaines)

### Features
| Feature | Description | Priorité |
|---------|-------------|----------|
| **WebSocket progress** | Temps réel pour la conversion via le web UI | 🔥 Haute |
| **Batch web UI** | Upload multiple + file queue dans le converter web | 🔥 Haute |
| **File queue** | Gestion d'attente pour les conversions multiples | 🟡 Moyenne |

### Livrables
- [ ] Ajouter `websockets` aux dépendances
- [ ] Implémenter WebSocket endpoint dans `server.py`
- [ ] Ajouter UI queue dans `static/index.html`
- [ ] Tests d'intégration pour WebSocket
- [ ] Documentation API WebSocket

---

## M3 — Rust CLI Pipeline Complet (3 semaines)

### Features
| Feature | Description | Priorité |
|---------|-------------|----------|
| **Rust CLI v2** | Pipeline complet: detect→extract→analyze→patch→generate | 🔥 Haute |
| **Benchmark suite** | Comparer Python vs Rust (temps, mémoire) | 🟡 Moyenne |
| **Plugin system** | Activer le crate `plugins/` pour analyseurs custom | 🟡 Moyenne |

### Livrables
- [ ] Finaliser `crates/cli/src/main.rs` avec pipeline complet
- [ ] Implémenter tous les traits du pipeline dans les crates
- [ ] Benchmark: `cargo bench` avec critères
- [ ] Tests d'intégration Rust
- [ ] Documentation rustdoc

---

## M4 — Dependency Graph + NixOS Config (1 semaine)

### Features
| Feature | Description | Priorité |
|---------|-------------|----------|
| **Dependency graph** | Visualisation arbre des dépendances (CLI + web) | 🟡 Moyenne |
| **NixOS config integration** | Auto-générer le snippet `environment.systemPackages` | 🟡 Moyenne |

### Livrables
- [ ] Commande `app2nix graph package.deb`
- [ ] Sortie DOT/ASCII pour le graph
- [ ] Template NixOS `configuration.nix` snippet
- [ ] Tests pour la génération de graph

---

## M5 — Qualité & Écosystème (1 semaine)

### Features
| Feature | Description | Priorité |
|---------|-------------|----------|
| **Couverture 85%** | Tests GUI (InstallWorker, SudoDialog), pipeline Rust | 🟡 Moyenne |
| **Multi-arch Docker** | Images arm64 + amd64 sur GHCR | 🟢 Basse |
| **CHANGELOG.md** | Historique complet depuis v1.0.0 | ✅ Fait |

### Livrables
- [ ] Tests GUI pour InstallWorker et SudoPasswordDialog
- [ ] Dockerfile multi-arch avec `docker buildx`
- [ ] CI/CD pour builds multi-arch

---

## 📊 Estimation

```
M1: Batch CLI + .zip/.7z          → 2 semaines
M2: WebSocket + Batch Web UI      → 2 semaines
M3: Rust CLI pipeline complet     → 3 semaines
M4: Dependency graph + NixOS      → 1 semaine
M5: Tests 85% + Docker multi-arch → 1 semaine
                                   ─────────────
Total                              → 9 semaines
```

## 📈 Métriques cibles v3.1.0

| Métrique | v3.0.2 | Objectif v3.1.0 |
|----------|--------|-----------------|
| Unit tests | 189 | 250+ |
| Integration tests | 113 | 150+ |
| Coverage | 89% | 85%+ (maintained) |
| Formats supportés | 8 | 10+ |
| CLI commands | 3 (convert, serve, gui) | 5+ (convert, serve, gui, graph, batch) |
| Rust crates | 12 | 12 (finalized) |

---

## 🔗 Liens utiles

- [Release v3.0.2](https://github.com/HiTechTN/app2nix/releases/tag/v3.0.2)
- [GitHub Issues](https://github.com/HiTechTN/app2nix/issues)
- [Documentation](https://hitechtn.github.io/app2nix/)
