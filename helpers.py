"""
Funkcje pomocnicze dla aplikacji Raport Czasu Pracy.

Zawiera logikę przetwarzania danych, formatowania i kalkulacji.
Eliminuje duplikaty z głównego pliku app.py.
"""

import re
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd

from config import ENCODING_FIXES, DEFAULT_CREATIVE_FILTER_OPTIONS


# =============================================================================
# PARSOWANIE CZASU
# =============================================================================

def parse_time_to_hours(time_str: Any) -> float:
    """
    Konwertuje czas w formacie HH:MM na godziny (float).

    Obsługuje formaty:
    - "10:30" -> 10.5
    - "3:00" -> 3.0
    - 10.5 (już jako float) -> 10.5
    - None/NaN/"" -> 0.0

    Args:
        time_str: Czas jako string "HH:MM" lub liczba

    Returns:
        Czas w godzinach jako float
    """
    if pd.isna(time_str) or time_str == "":
        return 0.0

    try:
        time_str = str(time_str).strip()
        if ":" in time_str:
            parts = time_str.split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            return hours + minutes / 60
        else:
            return float(time_str)
    except Exception:
        return 0.0


def hours_to_hm_format(hours: float) -> str:
    """
    Konwertuje godziny (float) na format HH:MM.

    Args:
        hours: Godziny jako float (np. 10.5)

    Returns:
        String w formacie "HH:MM" (np. "10:30")
    """
    if pd.isna(hours) or hours == 0:
        return "0:00"

    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h}:{m:02d}"


# =============================================================================
# EKSTRAKCJA PROCENTÓW TWÓRCZOŚCI
# =============================================================================

def extract_creative_percentage(text: Any) -> Optional[int]:
    """
    Wyciąga procent pracy twórczej z tekstu.

    Obsługuje formaty:
    - "90" -> 90
    - "90%" -> 90
    - "80.5" -> 80
    - "No Procent..." -> None
    - "" -> None

    Args:
        text: Tekst zawierający procent lub pusty

    Returns:
        Procent jako int (0-100) lub None jeśli brak danych
    """
    if pd.isna(text):
        return None

    text_str = str(text).strip()

    # Sprawdź czy to "brak danych"
    if (
        text_str == ""
        or "No Procent" in text_str
        or "Brak danych" in text_str
        or text_str.lower() == "none"
        or text_str.lower() == "nan"
    ):
        return None

    # Spróbuj konwertować bezpośrednio (jeśli jest sama liczba)
    try:
        value = float(text_str)
        if 0 <= value <= 100:
            return int(value)
    except ValueError:
        pass

    # Szuka liczby w tekście (może być sama liczba lub z %)
    match = re.search(r"(\d+(?:\.\d+)?)", text_str)
    if match:
        try:
            value = float(match.group(1))
            if 0 <= value <= 100:
                return int(value)
        except ValueError:
            pass

    return None


# =============================================================================
# NAPRAWA KODOWANIA
# =============================================================================

def fix_polish_encoding(text: Any) -> Any:
    """
    Naprawia błędne kodowanie polskich znaków (UTF-8 jako Latin-1).

    Args:
        text: Tekst z potencjalnie błędnym kodowaniem

    Returns:
        Tekst z naprawionym kodowaniem
    """
    if pd.isna(text) or not isinstance(text, str):
        return text

    result = str(text)
    for wrong, correct in ENCODING_FIXES.items():
        result = result.replace(wrong, correct)
    return result


def apply_encoding_fix_to_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stosuje naprawę kodowania do wszystkich kolumn tekstowych DataFrame.

    Args:
        df: DataFrame z potencjalnie błędnym kodowaniem

    Returns:
        DataFrame z naprawionym kodowaniem
    """
    df_fixed = df.copy()
    for col in df_fixed.columns:
        if df_fixed[col].dtype == "object":
            df_fixed[col] = df_fixed[col].apply(fix_polish_encoding)
    return df_fixed


# =============================================================================
# TOP ZADANIA PER OSOBA
# =============================================================================

def get_top_task_per_person(df: pd.DataFrame) -> pd.DataFrame:
    """
    Znajduje top zadanie dla każdego użytkownika na podstawie Creative Score.

    Creative Score = creative_hours × (creative_percent / 100)
    Dla osób bez danych o twórczości - wybiera najdłuższe zadanie.

    Args:
        df: DataFrame z kolumnami: person, task, key, time_hours,
            creative_percent, creative_hours

    Returns:
        DataFrame z top zadaniem per osoba, posortowany po score
    """
    most_creative_tasks = []

    for person in sorted(df["person"].unique()):
        person_data = df[df["person"] == person]

        # Filtruj zadania z danymi o twórczości
        creative_data = person_data[person_data["creative_hours"] > 0].copy()

        if not creative_data.empty:
            # Oblicz score
            creative_data["score"] = (
                creative_data["creative_hours"]
                * creative_data["creative_percent"] / 100
            )
            best_task = creative_data.nlargest(1, "score").iloc[0]
            most_creative_tasks.append({
                "person": best_task["person"],
                "task": best_task["task"],
                "key": best_task["key"],
                "time_hours": best_task["time_hours"],
                "creative_percent": best_task["creative_percent"],
                "creative_hours": best_task["creative_hours"],
                "score": best_task["score"],
                "has_creative_data": True,
            })
        else:
            # Brak danych o twórczości - bierz najdłuższe zadanie
            best_task = person_data.nlargest(1, "time_hours").iloc[0]
            most_creative_tasks.append({
                "person": best_task["person"],
                "task": best_task["task"],
                "key": best_task["key"],
                "time_hours": best_task["time_hours"],
                "creative_percent": best_task.get("creative_percent"),
                "creative_hours": best_task.get("creative_hours", 0),
                "score": 0.0,
                "has_creative_data": False,
            })

    if not most_creative_tasks:
        return pd.DataFrame()

    result_df = pd.DataFrame(most_creative_tasks)
    return result_df.sort_values(by="score", ascending=False)


# =============================================================================
# FORMATOWANIE TABEL DO WYŚWIETLENIA
# =============================================================================

def format_display_table(df: pd.DataFrame, include_status: bool = True) -> pd.DataFrame:
    """
    Formatuje DataFrame do wyświetlenia w UI (dodaje formatowanie tekstowe).

    Args:
        df: DataFrame z danymi numerycznymi
        include_status: Czy dodać kolumnę status

    Returns:
        DataFrame z sformatowanymi wartościami tekstowymi
    """
    display_df = df.copy()

    # Formatuj godziny
    if "time_hours" in display_df.columns:
        display_df["time_hours"] = display_df["time_hours"].apply(
            lambda x: f"{x:.1f}h"
        )

    # Formatuj procent twórczości
    if "creative_percent" in display_df.columns:
        display_df["creative_percent"] = display_df["creative_percent"].apply(
            lambda x: f"{int(x)}%" if pd.notna(x) else "—"
        )

    # Formatuj godziny twórcze
    if "creative_hours" in display_df.columns:
        display_df["creative_hours"] = display_df["creative_hours"].apply(
            lambda x: f"{x:.1f}h" if x > 0 else "—"
        )

    # Formatuj score
    if "score" in display_df.columns:
        display_df["score"] = display_df["score"].apply(
            lambda x: f"{x:.2f}" if x > 0 else "—"
        )

    # Dodaj status jeśli jest kolumna has_creative_data
    if include_status and "has_creative_data" in display_df.columns:
        display_df["status"] = display_df["has_creative_data"].apply(
            lambda x: "✨ Twórcze" if x else "⏰ Brak danych (najdłuższe)"
        )

    return display_df


# =============================================================================
# PODSUMOWANIE PRACY TWÓRCZEJ
# =============================================================================

def calculate_creative_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Oblicza podsumowanie pracy twórczej per osoba.

    Args:
        df: DataFrame z danymi zadań

    Returns:
        DataFrame z podsumowaniem per osoba:
        - Łączne godziny
        - Godziny twórcze
        - % Pracy twórczej (tylko z zadań z danymi)
        - Pokrycie danymi (% zadań z przypisanym %)
    """
    # Podstawowa agregacja
    summary = (
        df.groupby("person")
        .agg({
            "time_hours": "sum",
            "creative_hours": "sum",
            "creative_percent": lambda x: x.dropna().count(),
        })
        .round(2)
    )

    # Oblicz czas TYLKO dla zadań z danymi o twórczości
    time_hours_with_data = (
        df[df["creative_percent"].notna()]
        .groupby("person")["time_hours"]
        .sum()
    )

    # % twórczości ze ZGRUPOWANYCH GODZIN (gdzie mamy dane)
    summary["creative_ratio"] = (
        summary["creative_hours"] / time_hours_with_data * 100
    ).round(1)

    # Wskaźnik pokrycia
    total_tasks = df.groupby("person").size()
    summary["coverage"] = (
        summary["creative_percent"] / total_tasks * 100
    ).round(0)

    # Wybierz i przemianuj kolumny
    summary = summary[["time_hours", "creative_hours", "creative_ratio", "coverage"]]
    summary.columns = [
        "Łączne godziny",
        "Godziny twórcze",
        "% Pracy twórczej",
        "Pokrycie danymi",
    ]

    return summary


# =============================================================================
# DYNAMICZNE FILTRY
# =============================================================================

def get_dynamic_creative_filter_options(df: pd.DataFrame) -> List[str]:
    """
    Generuje opcje filtra na podstawie unikalnych wartości w danych.

    Args:
        df: DataFrame z kolumną creative_percent

    Returns:
        Lista opcji filtra (np. ["Wszystkie", "Z danymi", "Bez danych", "100%", "90%", ...])
    """
    options = list(DEFAULT_CREATIVE_FILTER_OPTIONS)  # Kopiuj domyślne

    if "creative_percent" not in df.columns:
        return options

    # Pobierz unikalne wartości i posortuj malejąco
    unique_percents = (
        df["creative_percent"]
        .dropna()
        .unique()
    )
    unique_percents = sorted([int(p) for p in unique_percents], reverse=True)

    # Dodaj jako opcje filtra
    for percent in unique_percents:
        options.append(f"{percent}%")

    return options


# =============================================================================
# WALIDACJA STRUKTURY DANYCH
# =============================================================================

def validate_data_structure(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """
    Waliduje strukturę danych i zwraca listę problemów.

    Args:
        df: DataFrame do walidacji

    Returns:
        Tuple (issues, warnings) - krytyczne błędy i ostrzeżenia
    """
    issues = []
    warnings = []

    # Sprawdź wymagane kolumny
    required_cols = ["Level", "Users / Issues / Procent pracy twórczej"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"Brakujące kolumny: {', '.join(missing_cols)}")
        return issues, warnings  # Krytyczny błąd, nie kontynuuj

    # Sprawdź czy są dane
    if df.empty:
        issues.append("Plik jest pusty")
        return issues, warnings

    # Sprawdź poziomy
    unique_levels = df["Level"].dropna().unique()
    if 0 not in unique_levels:
        warnings.append("Brak poziomu 0 (użytkownicy) - może być problem ze strukturą")
    if 1 not in unique_levels:
        warnings.append("Brak poziomu 1 (zadania) - brak danych do analizy")

    # Sprawdź duplikaty użytkowników (Level 0)
    users = df[df["Level"] == 0]["Users / Issues / Procent pracy twórczej"].dropna()
    duplicates = users[users.duplicated()].unique()
    if len(duplicates) > 0:
        warnings.append(
            f"Wykryto duplikaty użytkowników: {', '.join(duplicates[:3])}"
            + (f" i {len(duplicates)-3} więcej" if len(duplicates) > 3 else "")
        )

    # Sprawdź czy są czasy pracy
    if "Total Time Spent" in df.columns:
        time_data = df[df["Level"] == 1]["Total Time Spent"].dropna()
        if len(time_data) == 0:
            warnings.append("Brak danych czasu pracy (Total Time Spent)")
    else:
        warnings.append(
            "Brak kolumny 'Total Time Spent' - nie będzie można obliczyć czasu pracy"
        )

    # Sprawdź procenty twórczości
    creative_data = df[df["Level"] == 2][
        "Users / Issues / Procent pracy twórczej"
    ].dropna()
    if len(creative_data) == 0:
        warnings.append("Brak danych o procentach pracy twórczej (Level 2)")

    return issues, warnings


# =============================================================================
# EXECUTIVE SUMMARY (NOWA FUNKCJA)
# =============================================================================

def generate_executive_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generuje Executive Summary - kluczowe insights z danych.

    Args:
        df: DataFrame z przetworzonymi danymi

    Returns:
        Dict z kluczowymi metrykami:
        - top_performer: osoba z najwyższym Creative Score
        - data_coverage: % zadań z przypisanym % twórczości
        - alerts: lista ostrzeżeń (osoby bez danych, anomalie)
        - avg_creative_percent: średni % twórczości
        - total_creative_hours: łączne godziny twórcze
    """
    summary = {
        "top_performer": None,
        "top_performer_score": 0.0,
        "data_coverage": 0.0,
        "alerts": [],
        "avg_creative_percent": None,
        "total_creative_hours": 0.0,
        "people_without_data": [],
    }

    if df.empty:
        return summary

    # Top performer (osoba z najwyższym sumarycznym Creative Score)
    top_tasks = get_top_task_per_person(df)
    if not top_tasks.empty:
        top_row = top_tasks.iloc[0]
        summary["top_performer"] = top_row["person"]
        summary["top_performer_score"] = top_row["score"]

    # Pokrycie danymi
    total_tasks = len(df)
    tasks_with_data = df["creative_percent"].notna().sum()
    summary["data_coverage"] = (tasks_with_data / total_tasks * 100) if total_tasks > 0 else 0

    # Średni % twórczości (tylko z zadań z danymi)
    creative_data = df["creative_percent"].dropna()
    if not creative_data.empty:
        summary["avg_creative_percent"] = creative_data.mean()

    # Łączne godziny twórcze
    summary["total_creative_hours"] = df["creative_hours"].sum()

    # Osoby bez danych o twórczości
    people_with_data = set(df[df["creative_percent"].notna()]["person"].unique())
    all_people = set(df["person"].unique())
    people_without_data = all_people - people_with_data
    summary["people_without_data"] = list(people_without_data)

    # Alerty
    if summary["data_coverage"] < 50:
        summary["alerts"].append(
            f"⚠️ Niskie pokrycie danymi: tylko {summary['data_coverage']:.0f}% zadań ma przypisany % twórczości"
        )

    if people_without_data:
        if len(people_without_data) <= 3:
            names = ", ".join(people_without_data)
            summary["alerts"].append(f"ℹ️ Osoby bez danych o twórczości: {names}")
        else:
            summary["alerts"].append(
                f"ℹ️ {len(people_without_data)} osób nie ma żadnych danych o twórczości"
            )

    # Sprawdź anomalie (osoby z bardzo dużo godzin - potencjalny burnout)
    person_hours = df.groupby("person")["time_hours"].sum()
    for person, hours in person_hours.items():
        if hours > 200:  # Więcej niż 200h w raporcie
            summary["alerts"].append(
                f"🔥 {person}: {hours:.0f}h - sprawdź czy to poprawne"
            )

    return summary
