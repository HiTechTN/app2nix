LIGHT = {
    "name": "light",
    "bg": "#f0f2f5",
    "card_bg": "white",
    "card_border": "#e5e7eb",
    "text_primary": "#1a1a2e",
    "text_secondary": "#64748b",
    "text_muted": "#94a3b8",
    "input_bg": "white",
    "input_border": "#d1d5db",
    "input_focus": "#3b82f6",
    "header_start": "#1e3a5f",
    "header_end": "#2d4f8c",
    "header_text": "white",
    "header_subtitle": "#93b4e6",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "success": "#1a6b3c",
    "success_hover": "#15803d",
    "btn_sec_bg": "#f0f2f5",
    "btn_sec_text": "#374151",
    "btn_sec_border": "#d1d5db",
    "btn_sec_hover": "#e5e7eb",
    "code_bg": "#1e1e2e",
    "code_text": "#cdd6f4",
    "tab_bg": "#f8f9fa",
    "tab_text": "#64748b",
    "tab_selected": "#3b82f6",
    "status_bg": "#1e293b",
    "status_text": "#94a3b8",
    "menu_bg": "#1e293b",
    "menu_text": "#e2e8f0",
    "menu_hover": "#3b82f6",
    "progress_bg": "#e5e7eb",
    "separator": "#e5e7eb",
}

DARK = {
    "name": "dark",
    "bg": "#0f172a",
    "card_bg": "#1e293b",
    "card_border": "#334155",
    "text_primary": "#e2e8f0",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "input_bg": "#1e293b",
    "input_border": "#475569",
    "input_focus": "#60a5fa",
    "header_start": "#0f172a",
    "header_end": "#1e293b",
    "header_text": "#f1f5f9",
    "header_subtitle": "#94a3b8",
    "accent": "#60a5fa",
    "accent_hover": "#3b82f6",
    "success": "#22c55e",
    "success_hover": "#16a34a",
    "btn_sec_bg": "#334155",
    "btn_sec_text": "#e2e8f0",
    "btn_sec_border": "#475569",
    "btn_sec_hover": "#475569",
    "code_bg": "#0f172a",
    "code_text": "#a5f3fc",
    "tab_bg": "#1e293b",
    "tab_text": "#94a3b8",
    "tab_selected": "#60a5fa",
    "status_bg": "#0f172a",
    "status_text": "#64748b",
    "menu_bg": "#1e293b",
    "menu_text": "#e2e8f0",
    "menu_hover": "#60a5fa",
    "progress_bg": "#334155",
    "separator": "#334155",
}

ALL = {"light": LIGHT, "dark": DARK}
_cur = LIGHT

def set(t: str):
    global _cur
    if t in ALL:
        _cur = ALL[t]

def get() -> dict:
    return _cur

def name() -> str:
    return _cur["name"]
