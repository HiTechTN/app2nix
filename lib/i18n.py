import json
from pathlib import Path

_dir = Path(__file__).resolve().parent.parent / "translations"
_current = "en"
_strings: dict[str, str] = {}
_fallback: dict[str, str] = {}

def _load_english():
    global _fallback
    p = _dir / "en.json"
    if p.exists():
        _fallback = json.loads(p.read_text(encoding="utf-8"))

def load(lang: str) -> bool:
    global _current, _strings
    p = _dir / f"{lang}.json"
    if not p.exists():
        return False
    _strings = json.loads(p.read_text(encoding="utf-8"))
    _current = lang
    return True

def tr(key: str, default: str = "") -> str:
    val = _strings.get(key)
    if val is not None:
        return val
    val = _fallback.get(key)
    if val is not None:
        return val
    return default or key

def lang() -> str:
    return _current

def available() -> list[tuple[str, str]]:
    names = {"en": "English", "fr": "Français", "ar": "العربية"}
    result = []
    if _dir.exists():
        for f in sorted(_dir.iterdir()):
            if f.suffix == ".json":
                result.append((f.stem, names.get(f.stem, f.stem)))
    return result

def is_rtl() -> bool:
    return _current == "ar"

_load_english()
