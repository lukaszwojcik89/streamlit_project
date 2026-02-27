"""
Konfiguracja i stałe dla aplikacji Raport Czasu Pracy.

Centralizuje wszystkie "magic numbers", progi kolorów, etykiety i szerokości kolumn.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

# =============================================================================
# PROGI KOLORÓW DLA PROCENTÓW TWÓRCZOŚCI
# =============================================================================

# Progi dla kolorowania komórek w Excel i UI
# Format: (próg_górny, kolor_hex)
CREATIVE_PERCENT_THRESHOLDS: List[Tuple[int, str]] = [
    (50, "FFE6E6"),   # Czerwony (0-50%)
    (80, "FFFFCC"),   # Żółty (51-80%)
    (100, "E6FFE6"),  # Zielony (81-100%)
]

# Kolory dla Excel (openpyxl PatternFill)
EXCEL_COLORS = {
    "header_bg": "2F5597",
    "header_font": "FFFFFF",
    "border": "E0E0E0",
    "red_fill": "FFE6E6",
    "yellow_fill": "FFFFCC",
    "green_fill": "E6FFE6",
}

# =============================================================================
# SZEROKOŚCI KOLUMN EXCEL
# =============================================================================

EXCEL_COLUMN_WIDTHS = {
    "osoba": 25,
    "zadanie": 50,
    "klucz": 15,
    "czas": 12,
    "czas_h": 12,
    "procent": 18,
    "godziny_tworcze": 18,
    "godziny_tworcze_h": 18,
}

# Mapowanie kolumn do liter Excel
EXCEL_COLUMN_LETTERS = {
    "A": "osoba",
    "B": "zadanie",
    "C": "klucz",
    "D": "czas",
    "E": "czas_h",
    "F": "procent",
    "G": "godziny_tworcze",
    "H": "godziny_tworcze_h",
}

# =============================================================================
# ETYKIETY UI (POLSKIE)
# =============================================================================

# Nagłówki tabel z emotkami
TABLE_HEADERS_WITH_EMOJI = {
    "person": "👤 Osoba",
    "task": "📋 Zadanie",
    "key": "🔑 Klucz",
    "time_hours": "⏰ Czas",
    "creative_percent": "🎨 %",
    "creative_hours": "✨ Godz. twórcze",
    "score": "🏆 Score",
    "status": "📊 Typ",
}

# Nagłówki tabel bez emotek (do eksportu)
TABLE_HEADERS_PLAIN = {
    "person": "Osoba",
    "task": "Zadanie",
    "key": "Klucz",
    "time_hours": "Czas",
    "time_hours_numeric": "Czas (h)",
    "creative_percent": "Procent twórczości",
    "creative_hours": "Godziny twórcze",
    "creative_hours_numeric": "Godziny twórcze (h)",
}

# Statusy zadań
TASK_STATUS_LABELS = {
    "creative": "✨ Twórcze",
    "no_data_longest": "⏰ Brak danych (najdłuższe)",
    "no_data": "⏰ Najdłuższe",
}

# =============================================================================
# FILTRY PRACY TWÓRCZEJ
# =============================================================================

# Domyślne opcje filtrów (statyczne) - ZASTĄPIONE dynamicznymi w helpers.py
DEFAULT_CREATIVE_FILTER_OPTIONS = [
    "Wszystkie",
    "Z danymi",
    "Bez danych",
]

# =============================================================================
# POLSKIE NAZWY DNI TYGODNIA
# =============================================================================

DAY_NAMES_PL = {
    "Monday": "Poniedziałek",
    "Tuesday": "Wtorek",
    "Wednesday": "Środa",
    "Thursday": "Czwartek",
    "Friday": "Piątek",
    "Saturday": "Sobota",
    "Sunday": "Niedziela",
}

DAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# =============================================================================
# MAPA NAPRAWY KODOWANIA POLSKICH ZNAKÓW
# =============================================================================

ENCODING_FIXES = {
    "Ä…": "ą",
    "Ä": "Ą",
    "Ä‡": "ć",
    "Ć": "Ć",
    "Ĺ‚": "ł",
    "Ĺ": "Ł",
    "Ĺ›": "ś",
    "Ĺš": "Ś",
    "ĹĽ": "ż",
    "Ĺ»": "Ż",
    "Ĺş": "ź",
    "Ĺą": "Ź",
    "Ă³": "ó",
    'Ă"': "Ó",
    "Ĺ„": "ń",
    "Ĺƒ": "Ń",
    "Ä™": "ę",
    "Äś": "Ę",
    # Typowe błędne słowa
    "moĹĽliwoĹ›Ä‡": "możliwość",
    "dodaÄ‡": "dodać",
    "hiperĹ‚Ä…cze": "hiperłącze",
    "czcionki/tĹ‚a": "czcionki/tła",
}

# =============================================================================
# LIMITY I WALIDACJA
# =============================================================================

MAX_FILE_SIZE_MB = 50
LARGE_FILE_WARNING_MB = 10

# =============================================================================
# STAŁE WYKRESÓW
# =============================================================================

CHART_MIN_HEIGHT = 300
CHART_ROW_HEIGHT = 40  # Wysokość na jeden wiersz w wykresach poziomych

# Palety kolorów
CHART_COLOR_SCALES = {
    "creative_score": "Viridis",
    "default": "Blues",
}

# =============================================================================
# DATACLASSES DLA TYPOWANIA
# =============================================================================

@dataclass
class CreativeThreshold:
    """Próg kolorystyczny dla procentu twórczości."""
    max_percent: int
    color_hex: str
    label: str


def get_color_for_percent(percent: float) -> str:
    """Zwraca kolor hex dla danego procentu twórczości."""
    if percent <= 50:
        return EXCEL_COLORS["red_fill"]
    elif percent <= 80:
        return EXCEL_COLORS["yellow_fill"]
    else:
        return EXCEL_COLORS["green_fill"]
