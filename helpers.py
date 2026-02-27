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

    Sortuje po SUMIE score'ów wszystkich zadań osoby (Total Score),
    żeby być spójnym z Top Performer i Produktywnością zespołu.

    Args:
        df: DataFrame z kolumnami: person, task, key, time_hours,
            creative_percent, creative_hours

    Returns:
        DataFrame z top zadaniem per osoba, posortowany po total_score
    """
    most_creative_tasks = []

    # Najpierw oblicz Total Score dla każdej osoby (suma score'ów ze wszystkich zadań)
    person_total_scores = {}
    for person in df["person"].unique():
        person_creative = df[
            (df["person"] == person) & (df["creative_percent"].notna())
        ].copy()
        if not person_creative.empty:
            person_creative["task_score"] = (
                person_creative["creative_hours"]
                * person_creative["creative_percent"]
                / 100
            )
            person_total_scores[person] = person_creative["task_score"].sum()
        else:
            person_total_scores[person] = 0.0

    for person in sorted(df["person"].unique()):
        person_data = df[df["person"] == person]

        # Filtruj zadania z danymi o twórczości
        creative_data = person_data[person_data["creative_hours"] > 0].copy()

        if not creative_data.empty:
            # Oblicz score dla każdego zadania
            creative_data["score"] = (
                creative_data["creative_hours"]
                * creative_data["creative_percent"]
                / 100
            )
            best_task = creative_data.nlargest(1, "score").iloc[0]
            most_creative_tasks.append(
                {
                    "person": best_task["person"],
                    "task": best_task["task"],
                    "key": best_task["key"],
                    "time_hours": best_task["time_hours"],
                    "creative_percent": best_task["creative_percent"],
                    "creative_hours": best_task["creative_hours"],
                    "score": best_task["score"],
                    "total_score": person_total_scores[person],
                    "has_creative_data": True,
                }
            )
        else:
            # Brak danych o twórczości - bierz najdłuższe zadanie
            best_task = person_data.nlargest(1, "time_hours").iloc[0]
            most_creative_tasks.append(
                {
                    "person": best_task["person"],
                    "task": best_task["task"],
                    "key": best_task["key"],
                    "time_hours": best_task["time_hours"],
                    "creative_percent": best_task.get("creative_percent"),
                    "creative_hours": best_task.get("creative_hours", 0),
                    "score": 0.0,
                    "total_score": person_total_scores[person],
                    "has_creative_data": False,
                }
            )

    if not most_creative_tasks:
        return pd.DataFrame()

    result_df = pd.DataFrame(most_creative_tasks)
    # Sortuj po Total Score (suma wszystkich zadań osoby) - spójnie z Top Performer
    return result_df.sort_values(by="total_score", ascending=False)


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
        display_df["time_hours"] = display_df["time_hours"].apply(lambda x: f"{x:.1f}h")

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

    # Formatuj total_score
    if "total_score" in display_df.columns:
        display_df["total_score"] = display_df["total_score"].apply(
            lambda x: f"{x:.1f}" if x > 0 else "—"
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
        .agg(
            {
                "time_hours": "sum",
                "creative_hours": "sum",
                "creative_percent": lambda x: x.dropna().count(),
            }
        )
        .round(2)
    )

    # Oblicz czas TYLKO dla zadań z danymi o twórczości
    time_hours_with_data = (
        df[df["creative_percent"].notna()].groupby("person")["time_hours"].sum()
    )

    # % twórczości ze ZGRUPOWANYCH GODZIN (gdzie mamy dane)
    summary["creative_ratio"] = (
        summary["creative_hours"] / time_hours_with_data * 100
    ).round(1)

    # Wskaźnik pokrycia
    total_tasks = df.groupby("person").size()
    summary["coverage"] = (summary["creative_percent"] / total_tasks * 100).round(0)

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
    unique_percents = df["creative_percent"].dropna().unique()
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
    Generuje Executive Summary - kluczowe insights z danych jako tabele.

    Args:
        df: DataFrame z przetworzonymi danymi

    Returns:
        Dict z kluczowymi metrykami i tabelami:
        - top_performer: osoba z najwyższym Creative Score
        - data_coverage: % zadań z przypisanym % twórczości
        - productivity_table: DataFrame z metrykami produktywności
        - efficiency_table: DataFrame z metrykami efektywności
        - collaboration_table: DataFrame ze współpracą (opcjonalnie)
        - insights: lista dynamicznych opisów
    """
    summary = {
        "top_performer": None,
        "top_performer_score": 0.0,
        "data_coverage": 0.0,
        "avg_creative_percent": None,
        "total_creative_hours": 0.0,
        "people_without_data": [],
        "productivity_table": None,
        "efficiency_table": None,
        "collaboration_table": None,
        "insights": [],  # pozostałe insighty kategorii
        "insights_top3_cats": [],  # top 3 kategorie — zawsze wyświetlane
        "insights_team": [],  # insighty poziomu osobowego/teamowego
    }

    if df.empty:
        return summary

    # Top performer (osoba z najwyższym sumarycznym Creative Score)
    # Creative Score = suma (creative_hours × creative_percent / 100) ze wszystkich zadań
    df_with_score = df[df["creative_percent"].notna()].copy()
    df_with_score["task_score"] = (
        df_with_score["creative_hours"] * df_with_score["creative_percent"] / 100
    )
    person_creative_score = (
        df_with_score.groupby("person")["task_score"].sum().sort_values(ascending=False)
    )
    if not person_creative_score.empty:
        summary["top_performer"] = person_creative_score.index[0]
        summary["top_performer_score"] = person_creative_score.iloc[0]

    # Pokrycie danymi
    total_tasks = len(df)
    tasks_with_data = df["creative_percent"].notna().sum()
    summary["data_coverage"] = (
        (tasks_with_data / total_tasks * 100) if total_tasks > 0 else 0
    )

    # Średni % twórczości - ważony godzinami per osoba
    avg_creative_by_person = []
    for person in df["person"].unique():
        person_df = df[df["person"] == person]
        person_creative = person_df[person_df["creative_percent"].notna()]
        if not person_creative.empty:
            total_hours = person_creative["time_hours"].sum()
            if total_hours > 0:
                weighted_avg = (
                    person_creative["creative_percent"] * person_creative["time_hours"]
                ).sum() / total_hours
                avg_creative_by_person.append(weighted_avg)

    if avg_creative_by_person:
        summary["avg_creative_percent"] = sum(avg_creative_by_person) / len(
            avg_creative_by_person
        )

    # Łączne godziny twórcze
    summary["total_creative_hours"] = df["creative_hours"].sum()

    # Osoby bez danych o twórczości
    people_with_data = set(df[df["creative_percent"].notna()]["person"].unique())
    all_people = set(df["person"].unique())
    people_without_data = all_people - people_with_data
    summary["people_without_data"] = list(people_without_data)

    # ==========================================
    # TABELA 1: PRODUKTYWNOŚĆ (per osoba)
    # ==========================================
    productivity_data = []
    creative_data = df[df["creative_percent"].notna()]

    for person in df["person"].unique():
        person_df = df[df["person"] == person]
        person_creative = person_df[person_df["creative_percent"].notna()]

        total_hours = person_df["time_hours"].sum()
        total_creative_hours = person_df["creative_hours"].sum()
        num_tasks = len(person_df)

        # % Pracy twórczej (ważona godzinami - identycznie jak calculate_creative_summary)
        time_hours_with_data = person_df[person_df["creative_percent"].notna()][
            "time_hours"
        ].sum()
        if time_hours_with_data > 0 and not person_creative.empty:
            creative_ratio = total_creative_hours / time_hours_with_data * 100
        else:
            creative_ratio = None

        # Creative Score (suma score'ów z zadań: creative_hours × creative_percent / 100)
        if not person_creative.empty:
            person_creative_with_score = person_creative.copy()
            person_creative_with_score["task_score"] = (
                person_creative_with_score["creative_hours"]
                * person_creative_with_score["creative_percent"]
                / 100
            )
            creative_score = person_creative_with_score["task_score"].sum()
        else:
            creative_score = None

        # Średnia godzin/zadanie (efektywność)
        avg_hours_per_task = total_hours / num_tasks if num_tasks > 0 else 0

        productivity_data.append(
            {
                "Osoba": person,
                "Liczba zadań": num_tasks,
                "Łącznie [h]": total_hours,
                "Twórcze [h]": total_creative_hours,
                "% Pracy twórczej": creative_ratio,
                "Creative Score": creative_score,
                "Średnia [h/zadanie]": avg_hours_per_task,
            }
        )

    if productivity_data:
        prod_df = pd.DataFrame(productivity_data)
        # Sortuj po Creative Score (zgodnie z Rankingiem)
        prod_df = prod_df.sort_values("Creative Score", ascending=False)
        summary["productivity_table"] = prod_df

        # Dynamiczne insighty
        max_hours_person = prod_df.iloc[0]
        avg_hours = prod_df["Łącznie [h]"].mean()
        std_hours = prod_df["Łącznie [h]"].std()

        if max_hours_person["Łącznie [h]"] > avg_hours + std_hours:
            summary["insights_team"].append(
                f"📊 **Dominacja godzinowa:** {max_hours_person['Osoba']} realizuje {max_hours_person['Łącznie [h]']:.0f}h "
                f"({max_hours_person['Łącznie [h]']/avg_hours:.1f}× średniej zespołu, "
                f"+{max_hours_person['Łącznie [h]'] - avg_hours:.0f}h ponad benchmark)."
            )

        # Najwyższy średni % twórczości
        prod_with_creative = prod_df[prod_df["% Pracy twórczej"].notna()].copy()
        if not prod_with_creative.empty:
            top_creative = prod_with_creative.iloc[
                prod_with_creative["% Pracy twórczej"].argmax()
            ]
            if top_creative["% Pracy twórczej"] >= 70:
                summary["insights_team"].append(
                    f"🏆 **Lider kreatywności:** {top_creative['Osoba']} — {top_creative['% Pracy twórczej']:.0f}% średniego poziomu twórczości "
                    f"({top_creative['Twórcze [h]']:.0f}h twórczych). Konsekwentnie wysoka jakość pracy."
                )

    # ==========================================
    # TABELA 2: EFEKTYWNOŚĆ (analiza zadań)
    # ==========================================
    efficiency_data = []

    # Długie vs krótkie zadania
    long_tasks = df[df["time_hours"] >= 10]
    short_tasks = df[df["time_hours"] <= 5]

    if not long_tasks.empty:
        long_creative = long_tasks[long_tasks["creative_percent"].notna()][
            "creative_percent"
        ].mean()
        efficiency_data.append(
            {
                "Kategoria": "Długie zadania (≥10h)",
                "Liczba": len(long_tasks),
                "Średni % twórczości": (
                    long_creative if pd.notna(long_creative) else None
                ),
            }
        )

    if not short_tasks.empty:
        short_creative = short_tasks[short_tasks["creative_percent"].notna()][
            "creative_percent"
        ].mean()
        efficiency_data.append(
            {
                "Kategoria": "Krótkie zadania (≤5h)",
                "Liczba": len(short_tasks),
                "Średni % twórczości": (
                    short_creative if pd.notna(short_creative) else None
                ),
            }
        )

    # Rozkład twórczości
    high_creative = creative_data[creative_data["creative_percent"] >= 80]
    medium_creative = creative_data[
        (creative_data["creative_percent"] >= 40)
        & (creative_data["creative_percent"] < 80)
    ]
    low_creative = creative_data[creative_data["creative_percent"] < 40]

    efficiency_data.extend(
        [
            {
                "Kategoria": "Wysoka twórczość (≥80%)",
                "Liczba": len(high_creative),
                "Średni % twórczości": (
                    high_creative["creative_percent"].mean()
                    if not high_creative.empty
                    else None
                ),
            },
            {
                "Kategoria": "Średnia twórczość (40-79%)",
                "Liczba": len(medium_creative),
                "Średni % twórczości": (
                    medium_creative["creative_percent"].mean()
                    if not medium_creative.empty
                    else None
                ),
            },
            {
                "Kategoria": "Niska twórczość (<40%)",
                "Liczba": len(low_creative),
                "Średni % twórczości": (
                    low_creative["creative_percent"].mean()
                    if not low_creative.empty
                    else None
                ),
            },
        ]
    )

    if efficiency_data:
        eff_df = pd.DataFrame(efficiency_data)
        summary["efficiency_table"] = eff_df

        # Dynamiczne insighty
        if not long_tasks.empty and not short_tasks.empty:
            long_avg = long_tasks[long_tasks["creative_percent"].notna()][
                "creative_percent"
            ].mean()
            short_avg = short_tasks[short_tasks["creative_percent"].notna()][
                "creative_percent"
            ].mean()

            if pd.notna(long_avg) and pd.notna(short_avg):
                diff = abs(long_avg - short_avg)
                if diff > 15:
                    if long_avg > short_avg:
                        summary["insights_team"].append(
                            f"📋 **Złożoność koreluje z kreatywnością:** Zadania długie (≥10h) są o {diff:.0f} pp bardziej twórcze "
                            f"({long_avg:.0f}% vs {short_avg:.0f}%). Złożone projekty wymagają więcej oryginalnego myślenia."
                        )
                    else:
                        summary["insights_team"].append(
                            f"📋 **Zadania krótkie bardziej twórcze:** Różnica {diff:.0f} pp ({short_avg:.0f}% vs {long_avg:.0f}%). "
                            f"Zadania czasochłonne mogą być zdominowane przez rutynowe wykonanie."
                        )

        # Analiza rozkładu
        if not creative_data.empty:
            high_pct = len(high_creative) / len(creative_data) * 100
            low_pct = len(low_creative) / len(creative_data) * 100

            # Progresja dla zespołu programistycznego (wyższe standardy)
            if high_pct >= 75:
                summary["insights_team"].append(
                    f"📈 **Wysoka wartość twórcza:** {high_pct:.0f}% zadań osiąga ≥80% twórczości. "
                    f"Zespół operuje w obszarze innowacji i budowania wartości — optymalne zaangażowanie."
                )
            elif high_pct >= 60:
                summary["insights_team"].append(
                    f"✅ **Zrównoważona struktura pracy:** {high_pct:.0f}% zadań to praca twórcza/techniczna. "
                    f"Dobry balans między rozwojem nowych funkcji a maintenance."
                )
            elif high_pct >= 45:
                summary["insights_team"].append(
                    f"⚠️ **Wysoki udział pracy rutynowej:** {high_pct:.0f}% zadań twórczych, {low_pct:.0f}% poniżej 40%. "
                    f"Zbyt duży udział tech-debtu i supportu — warto zrewidować backlog."
                )
            elif high_pct >= 30:
                summary["insights_team"].append(
                    f"📉 **Niski wskaźnik twórczości:** Tylko {high_pct:.0f}% zadań powyżej progu 80%. "
                    f"Budżet czasu przesuwa się w stronę supportu i hotfixów kosztem nowego development."
                )
            else:
                summary["insights_team"].append(
                    f"⛔ **Dominacja pracy reaktywnej:** Zaledwie {high_pct:.0f}% zadań ma istotny komponent twórczy. "
                    f"Zespół w trybie fire-fighting — konieczna pilna redukcja tech-debtu."
                )

        # ==========================================
        # ANALIZA KONCENTRACJI CZASU (NOWY INSIGHT)
        # ==========================================
        if not df.empty:
            person_hours = df.groupby("person")["time_hours"].sum()
            total_hours = person_hours.sum()

            # Jaki procent czasu spędzają 2 osoby?
            top_2_pct = (
                (person_hours.nlargest(2).sum() / total_hours * 100)
                if total_hours > 0
                else 0
            )

            if top_2_pct >= 70:
                summary["insights_team"].append(
                    f"⚠️ **Koncentracja zasobów:** Dwie osoby realizują {top_2_pct:.0f}% wszystkich godzin. "
                    f"Model silnie oparty na kluczowych profilach — ryzyko operacyjne w przypadku niedostępności."
                )
            elif top_2_pct >= 50:
                summary["insights_team"].append(
                    f"📊 **Umiarkowana koncentracja:** Dwie osoby pokrywają {top_2_pct:.0f}% czasu zespołu. "
                    f"Rozsądny podział przy zachowaniu elastyczności operacyjnej."
                )
            elif (
                person_hours.std() / person_hours.mean() > 0.5
                if person_hours.mean() > 0
                else False
            ):
                summary["insights_team"].append(
                    f"📊 **Nierównomierne obciążenie:** Wysokie odchylenie godzin między członkami zespołu. "
                    f"Rekomendowane: przegląd alokacji zadań pod kątem zrównoważenia pojemności."
                )

        # ==========================================
        # ANALIZA JAKOŚCI DANYCH (NOWY INSIGHT)
        # ==========================================
        if not df.empty:
            total_rows = len(df)
            rows_with_pct = df["creative_percent"].notna().sum()
            data_coverage = (rows_with_pct / total_rows * 100) if total_rows > 0 else 0

            if data_coverage >= 90:
                summary["insights_team"].append(
                    f"✅ **Kompletność danych: {data_coverage:.0f}%** — wysoka wiarygodność analiz, wyniki można traktować jako reprezentatywne."
                )
            elif data_coverage >= 70:
                summary["insights_team"].append(
                    f"✅ **Pokrycie danych: {data_coverage:.0f}%** — wystarczające dla rzetelnych wniosków, uzupełnienie brakujących wartości poprawi precyzję kolejnych raportów."
                )
            elif data_coverage >= 50:
                summary["insights_team"].append(
                    f"⚠️ **Pokrycie danych: {data_coverage:.0f}%** — znaczna część zadań bez wskaźnika twórczości, wyniki należy interpretować z ostrożnością."
                )
            else:
                summary["insights_team"].append(
                    f"⛔ **Pokrycie danych: {data_coverage:.0f}%** — zbyt mało danych dla wiarygodnej analizy, uzupełnienie wskaźników twórczości jest priorytetem."
                )

        # ==========================================
        # ANALIZA KONSEKWENCJI PRACY TWÓRCZEJ (NOWY INSIGHT)
        # ==========================================
        if not df.empty and not df[df["creative_percent"].notna()].empty:
            creative_df = df[df["creative_percent"].notna()].copy()

            # Czy osoby o wysokiej twórczości mają niskie godziny (efektywne)?
            high_creative_people = creative_df[creative_df["creative_percent"] >= 70][
                "person"
            ].unique()

            if len(high_creative_people) > 0:
                high_creative_hours = df[df["person"].isin(high_creative_people)][
                    "time_hours"
                ].mean()
                all_people_hours = df["time_hours"].mean()

                if high_creative_hours < all_people_hours * 0.8:
                    summary["insights_team"].append(
                        f"📋 **Niewykorzystany potencjał:** Osoby z najwyższą twórczością realizują średnio {high_creative_hours:.1f}h na zadanie wobec {all_people_hours:.1f}h w zespole — zwiększenie ich zaangażowania może poprawić łączną wartość dostarczoną."
                    )
                elif high_creative_hours > all_people_hours * 1.2:
                    summary["insights_team"].append(
                        f"⚠️ **Przeciążenie kluczowych osób:** Pracownicy o wysokiej twórczości realizują {high_creative_hours:.1f}h/zadanie przy średniej {all_people_hours:.1f}h — rekomendowane przejrzenie alokacji zadań rutynowych."
                    )

    # ==========================================
    # TABELA 3: WSPÓŁPRACA (opcjonalnie)
    # ==========================================
    if "key" in df.columns:
        collaboration_data = []
        key_people_count = df.groupby("key")["person"].nunique()
        shared_tasks = key_people_count[key_people_count > 1]

        if len(shared_tasks) > 0:
            # Zbierz dane o współpracy
            pairs = {}
            for key in shared_tasks.index:
                people = sorted(df[df["key"] == key]["person"].unique())
                if len(people) == 2:
                    pair = tuple(people)
                    pairs[pair] = pairs.get(pair, 0) + 1

            if pairs:
                for pair, count in sorted(
                    pairs.items(), key=lambda x: x[1], reverse=True
                )[:5]:
                    collaboration_data.append(
                        {
                            "Osoba 1": pair[0],
                            "Osoba 2": pair[1],
                            "Wspólnych zadań": count,
                        }
                    )

                if collaboration_data:
                    collab_df = pd.DataFrame(collaboration_data)
                    summary["collaboration_table"] = collab_df

                    # Dynamiczny insight
                    top_pair = collaboration_data[0]
                    if top_pair["Wspólnych zadań"] >= 5:
                        summary["insights"].append(
                            f"**{top_pair['Osoba 1']}** i **{top_pair['Osoba 2']}** współpracują najczęściej "
                            f"({top_pair['Wspólnych zadań']} wspólnych zadań). Silna współpraca może oznaczać dobrą synergię zespołową."
                        )

    # ==========================================
    # ANALIZA KATEGORII ZADAŃ (jeśli dostępna)
    # ==========================================
    if "task" in df.columns:
        _add_category_insights(df, summary)

    return summary


def _add_category_insights(df: pd.DataFrame, summary: Dict[str, Any]) -> None:
    """
    Analizuje kategorie zadań. Top 3 kategorie (wg godzin) trafiają do insights_top3_cats,
    pozostałe do insights. Każdy insight to jedno zdanie opisowe.
    """
    keywords = {
        "Bug/Hotfix": [
            "bug",
            "hotfix",
            "crash",
            "błąd",
            "error",
            "problem z",
            "niezgodność",
            "uszkodz",
            "awaria",
            "napr",
            "fix",
        ],
        "Code Review": [
            "review",
            "pull request",
            "pr ",
            "feedback code",
            "sprawdzenie kodu",
            "code review",
        ],
        "Testing": [
            "test",
            "qa",
            "validation",
            "weryfikacja",
            "acceptance",
            "e2e",
            "unit",
            "testowani",
            "testy",
        ],
        "Development": [
            "feature",
            "implement",
            "develop",
            "build",
            "funkcj",
            "kod",
            "refactor",
            "wdrożeni",
            "stworz",
            "endpoint",
            "komponent",
            "obsług",
            "logik",
            "edycj",
            "popraw",
            "ulepsz",
            "improve",
            "edycja",
        ],
        "DevOps/Infrastructure": [
            "deploy",
            "deployment",
            "ci/cd",
            "ci ",
            "cd ",
            "pipeline",
            "gitlab-ci",
            "docker",
            "kubernetes",
            "infra",
            "serwer",
            "baza danych",
            "monitoring",
            "logging",
            "konfiguruj",
            "infrastructure",
            "środowisk",
        ],
        "Analysis/Design": [
            "analiz",
            "przegląd",
            "diagram",
            "design",
            "dokumentuj",
            "architektur",
            "zapoznani",
            "sprawdz",
            "research",
            "badani",
            "ocen",
            "koncepj",
            "wymagan",
        ],
        "Training/Learning": [
            "szkoleni",
            "webinar",
            "training",
            "workshop",
            "moduł",
            "kurs",
            "nauk",
            "edukacj",
            "certifikacj",
            "copilot",
            "samoszkoleni",
        ],
        "Meetings": [
            "spotkani",
            "meeting",
            "call",
            "standup",
            "daily",
            "retro",
            "retrospectiv",
            "planning",
            "refinement",
            "grooming",
            "sesj",
            "briefing",
            "sync",
            "kick-off",
            "komitet",
            "posiedzeni",
            "dyskusj",
            "scrum",
        ],
        "Administration/Support": [
            "administraj",
            "support",
            "help desk",
            "help ",
            "incident",
            "zgłoszeni",
            "obsług",
            "wsparci",
            "mail",
            "telefon",
            "biuro",
            "dostęp",
            "uprawni",
            "konto",
            "papierologi",
        ],
    }

    categories_data = {}
    for cat, kws in keywords.items():
        mask = df["task"].str.lower().str.contains("|".join(kws), na=False)
        if mask.sum() > 0:
            category_df = df[mask]
            category_hours = (
                category_df["time_hours"].sum()
                if "time_hours" in category_df.columns
                else 0
            )
            creative_mask = category_df["creative_percent"].notna()
            avg_creative = (
                category_df[creative_mask]["creative_percent"].mean()
                if creative_mask.sum() > 0
                else 0
            )
            categories_data[cat] = {
                "hours": category_hours,
                "avg_creative": avg_creative,
                "count": int(mask.sum()),
            }

    if not categories_data:
        return

    total_hours = sum(c["hours"] for c in categories_data.values())
    if total_hours <= 0:
        return

    # Wyznacz top 3 kategorie według godzin
    sorted_cats = sorted(
        categories_data.items(), key=lambda x: x[1]["hours"], reverse=True
    )
    top3_names = {cat for cat, _ in sorted_cats[:3]}

    def _route(cat_name: str, text: str) -> None:
        """Wstawia insight do właściwej listy: top3 → insights_top3_cats, reszta → insights."""
        if cat_name in top3_names:
            summary["insights_top3_cats"].append(text)
        else:
            summary["insights"].append(text)

    # ===== DEVELOPMENT =====
    if "Development" in categories_data:
        dev = categories_data["Development"]
        p = dev["hours"] / total_hours * 100
        c = dev["avg_creative"]
        h = dev["hours"]
        if c >= 75:
            txt = f"✅ **Development ({h:.0f}h, {p:.0f}%):** Zespół skupia się głównie na budowaniu nowych rozwiązań ({c:.0f}% twórczości) — świetny fundament dla produktu."
        elif c >= 60:
            txt = f"✅ **Development ({h:.0f}h, {p:.0f}%):** Dobrze balansujecie między nowymi funkcjami a utrzymaniem systemu ({c:.0f}% twórczości)."
        elif c >= 45:
            txt = f"⚠️ **Development ({h:.0f}h, {p:.0f}%):** Dużo czasu na naprawy — twórczość {c:.0f}% może spowalniać tempo nowych funkcji."
        elif c >= 30:
            txt = f"📉 **Development ({h:.0f}h, {p:.0f}%):** Zespół ugrzęzł w naprawach — twórczość {c:.0f}% oznacza, że roadmap musi czekać."
        elif c >= 15:
            txt = f"⛔ **Development ({h:.0f}h, {p:.0f}%):** Kryzys — zespół wciągnięty w naprawy ({c:.0f}% twórczości), rozwój produktu praktycznie wstrzymany."
        else:
            txt = f"🔴 **Development ({h:.0f}h, {p:.0f}%):** Stan krytyczny — zespół całkowicie pochłonięty naprawami ({c:.0f}% twórczości), zero czasu na innowacje."
        _route("Development", txt)

    # ===== DEVOPS/INFRASTRUCTURE =====
    if "DevOps/Infrastructure" in categories_data:
        devops = categories_data["DevOps/Infrastructure"]
        p = devops["hours"] / total_hours * 100
        c = devops["avg_creative"]
        h = devops["hours"]
        if p >= 25:
            if c >= 55:
                txt = f"✅ **DevOps ({h:.0f}h, {p:.0f}%):** Wykonujecie znaczną pracę architektoniczną ({c:.0f}% twórczości) — daleko poza konfigurację, rzeczywisty wkład w system."
            else:
                txt = f"⚠️ **DevOps ({h:.0f}h, {p:.0f}%):** Bardzo dużo czasu na infrastrukturę ({c:.0f}% twórczości) — warto przeanalizować, co się da zautomatyzować."
        elif p >= 15:
            if c >= 45:
                txt = f"✅ **DevOps ({h:.0f}h, {p:.0f}%):** Solidny udział pracy architektonicznej ({c:.0f}% twórczości) — dobrze zaplanowana infrastruktura."
            else:
                txt = f"✅ **DevOps ({h:.0f}h, {p:.0f}%):** Infrastruktura na stabilnym poziomie — proporcjonalny nakład do potrzeb systemu."
        elif p >= 8:
            txt = f"📋 **DevOps ({h:.0f}h, {p:.0f}%):** Umiarkowany nakład na infrastrukturę — utrzymujemy status quo bez zmian architektonicznych."
        else:
            txt = f"⚠️ **DevOps ({h:.0f}h, {p:.0f}%):** Minimalny czas na infrastrukturę — uważajcie na zaległości techniczne, które mogą się nagromadzić."
        _route("DevOps/Infrastructure", txt)

    # ===== TESTING =====
    if "Testing" in categories_data:
        test = categories_data["Testing"]
        p = test["hours"] / total_hours * 100
        c = test["avg_creative"]
        h = test["hours"]
        if p >= 22:
            if c >= 55:
                txt = f"✅ **Testing ({h:.0f}h, {p:.0f}%):** Testujecie inteligentnie ({c:.0f}% twórczości) — widać automatyzację i zaawansowane podejście do QA."
            else:
                txt = f"✅ **Testing ({h:.0f}h, {p:.0f}%):** Duży nacisk na jakość ({c:.0f}% twórczości) — warto monitorować wpływ na tempo wydań."
        elif p >= 12:
            txt = f"⚠️ **Testing ({h:.0f}h, {p:.0f}%):** Solidny poziom testowania — potencjał wzrostu automatyzacji bez obniżania velocity."
        elif p >= 6:
            txt = f"📋 **Testing ({h:.0f}h, {p:.0f}%):** Umiarkowane testowanie — utrzymujemy poziom jakości przy szybkim tempie."
        else:
            txt = f"⛔ **Testing ({h:.0f}h, {p:.0f}%):** Zbyt mało testowania — wysokie ryzyko niezauważonych defektów w produkcji."
        _route("Testing", txt)

    # ===== ANALYSIS/DESIGN =====
    if "Analysis/Design" in categories_data:
        analysis = categories_data["Analysis/Design"]
        p = analysis["hours"] / total_hours * 100
        c = analysis["avg_creative"]
        h = analysis["hours"]
        if p >= 25:
            if c >= 50:
                txt = f"✅ **Analiza i projektowanie ({h:.0f}h, {p:.0f}%):** Zespół projektuje solidnie przed kodowaniem ({c:.0f}% twórczości) — zmniejsza błędy i przemieszanie kodu."
            else:
                txt = f"⚠️ **Analiza i projektowanie ({h:.0f}h, {p:.0f}%):** Dużo czasu na analizę ({c:.0f}% twórczości) — sprawdzcie, czy przekłada się na lepsze decyzje implementacyjne."
        elif p >= 12:
            if c >= 35:
                txt = f"✅ **Analiza i projektowanie ({h:.0f}h, {p:.0f}%):** Rozsądny nakład z kreatywnym wkładem ({c:.0f}% twórczości) — dobrze zaplanowany proces."
            else:
                txt = f"✅ **Analiza i projektowanie ({h:.0f}h, {p:.0f}%):** Wystarczające przygotowanie przed kodowaniem — stabilny proces."
        elif p >= 6:
            txt = f"📋 **Analiza i projektowanie ({h:.0f}h, {p:.0f}%):** Minimalna analiza — szybkoś vs. jakość, obserwujcie błędy w kodzie."
        else:
            txt = f"⚠️ **Analiza i projektowanie ({h:.0f}h, {p:.0f}%):** Prawie bez projektowania — uważajcie na drogi refaktoryzacji później."
        _route("Analysis/Design", txt)

    # ===== TRAINING/LEARNING =====
    if "Training/Learning" in categories_data:
        train = categories_data["Training/Learning"]
        p = train["hours"] / total_hours * 100
        c = train["avg_creative"]
        h = train["hours"]
        if p >= 20:
            txt = f"📈 **Szkolenia ({h:.0f}h, {p:.0f}%):** Duży nacisk na naukę zespołu — świetnie dla długoterminowego rozwoju, ale obserwujcie wpływ na terminowość dostarczeń."
        elif p >= 12:
            txt = f"✅ **Szkolenia ({h:.0f}h, {p:.0f}%):** Solidny poziom inwestycji w rozwój — zespół regularnie się uczy nowych umiejętności."
        elif p >= 6:
            txt = f"✅ **Szkolenia ({h:.0f}h, {p:.0f}%):** Umiarkowany nacisk na naukę — kultura ciągłego rozwoju jest obecna."
        elif p >= 2:
            txt = f"📋 **Szkolenia ({h:.0f}h, {p:.0f}%):** Minimalne czasy na naukę — zespół utrzymuje obecne umiejętności, ale bez wzrostu."
        elif p >= 0.5:
            txt = f"⚠️ **Szkolenia ({h:.0f}h, {p:.0f}%):** Prawie żaden czas na naukę — brak formalnych inwestycji w rozwój."
        else:
            txt = f"⛔ **Szkolenia ({h:.0f}h, {p:.0f}%):** Całkowity brak czasu na naukę — zespół będzie starzał się technicznie."
        _route("Training/Learning", txt)

    # ===== MEETINGS =====
    if "Meetings" in categories_data:
        meetings = categories_data["Meetings"]
        p = meetings["hours"] / total_hours * 100
        h = meetings["hours"]
        if p >= 25:
            txt = f"⛔ **Spotkania ({h:.0f}h, {p:.0f}%):** Prawie czwarta część czasu w spotkaniach — pilne przeanalizować ilość i format komunikacji."
        elif p >= 20:
            txt = f"⛔ **Spotkania ({h:.0f}h, {p:.0f}%):** Prawie piąta część czasu w spotkaniach — warto zrewidować plan komunikacji."
        elif p >= 12:
            txt = f"⚠️ **Spotkania ({h:.0f}h, {p:.0f}%):** Sporo spotkań — może warto przesunąć część na asynchroniczne?"
        elif p >= 7:
            txt = f"📋 **Spotkania ({h:.0f}h, {p:.0f}%):** Koordynacja na średnim poziomie — obserwujcie, żeby nie rósł czas spotkań."
        elif p >= 3:
            txt = f"✅ **Spotkania ({h:.0f}h, {p:.0f}%):** Dobrze — synchronizacja bez przytłaczania kalendarzy."
        else:
            txt = f"✅ **Spotkania ({h:.0f}h, {p:.0f}%):** Prawie w pełni asynchronicznie — zespół ma czas na fokus."
        _route("Meetings", txt)

    # ===== ADMINISTRATION/SUPPORT =====
    if "Administration/Support" in categories_data:
        admin = categories_data["Administration/Support"]
        p = admin["hours"] / total_hours * 100
        h = admin["hours"]
        if p >= 18:
            txt = f"⛔ **Administracja i support ({h:.0f}h, {p:.0f}%):** Znaczna część czasu na obsługę operacyjną — coś blokuje pracę wytwórczą."
        elif p >= 12:
            txt = f"⚠️ **Administracja i support ({h:.0f}h, {p:.0f}%):** Dużo na administrację — sprawdzcie, co się da zautomatyzować lub delegować."
        elif p >= 6:
            txt = f"✅ **Administracja i support ({h:.0f}h, {p:.0f}%):** Administracja na standardowym poziomie — bez przesady."
        else:
            txt = f"✅ **Administracja i support ({h:.0f}h, {p:.0f}%):** Procesy są sprawne — mało czasu na obsługę operacyjną."
        _route("Administration/Support", txt)

    # ===== BUG/HOTFIX =====
    if "Bug/Hotfix" in categories_data:
        bug = categories_data["Bug/Hotfix"]
        p = bug["hours"] / total_hours * 100
        h = bug["hours"]
        if p >= 18:
            txt = f"⛔ **Bugfixy ({h:.0f}h, {p:.0f}%):** Prawie piąta część czasu na naprawy — coś jest nie tak z jakością lub długiem technicznym."
        elif p >= 10:
            txt = f"⚠️ **Bugfixy ({h:.0f}h, {p:.0f}%):** Sporo czasu na hotfixy — sprawdzcie przyczyny i wzmocnijcie QA."
        elif p >= 5:
            txt = f"📋 **Bugfixy ({h:.0f}h, {p:.0f}%):** Normalne dla aktywnie rozwijanego projektu — proporcjonalny nakład."
        else:
            txt = f"✅ **Bugfixy ({h:.0f}h, {p:.0f}%):** Mało bugów — system jest stabilny."
        _route("Bug/Hotfix", txt)

    # ===== CODE REVIEW =====
    if "Code Review" in categories_data:
        review = categories_data["Code Review"]
        p = review["hours"] / total_hours * 100
        h = review["hours"]
        if p >= 12:
            txt = f"⚠️ **Code review ({h:.0f}h, {p:.0f}%):** Dużo czasu na review — może zmiany są złożone albo warto popracować na standardach kodu."
        elif p >= 5:
            txt = f"✅ **Code review ({h:.0f}h, {p:.0f}%):** Porządne przeglądy kodu — bez przesady."
        else:
            txt = f"⚠️ **Code review ({h:.0f}h, {p:.0f}%):** Mało review — uważajcie na dług techniczny."
        _route("Code Review", txt)

    # ===== NADRZĘDNY INSIGHT: TOP 3 KATEGORIE =====
    if len(sorted_cats) >= 3:
        top3_list = sorted_cats[:3]
        total_top3_hours = sum(cat[1]["hours"] for cat in top3_list)
        total_top3_pct = (
            (total_top3_hours / total_hours * 100) if total_hours > 0 else 0
        )

        top3_txt = "💼 **Rozkład czasu — top 3 grupy zadań:\n"
        for cat_name, cat_data in top3_list:
            cat_pct = (cat_data["hours"] / total_hours * 100) if total_hours > 0 else 0
            top3_txt += f"  • {cat_name}: {cat_data['hours']:.0f}h ({cat_pct:.0f}%)\n"
        top3_txt += f"Razem: {total_top3_hours:.0f}h ({total_top3_pct:.0f}%)** — wyznaczają strategiczny kierunek zespołu."

        summary["insights_top3_cats"].insert(0, top3_txt)


# =============================================================================
# PERSONAL DASHBOARD (NOWA FUNKCJA)
# =============================================================================


def generate_personal_stats(df: pd.DataFrame, person_name: str) -> Dict[str, Any]:
    """
    Generuje statystyki personalne dla jednego użytkownika.

    Args:
        df: DataFrame z wszystkimi danymi
        person_name: Imię i nazwisko użytkownika

    Returns:
        Dict z kluczowymi metrykami:
        - total_hours: Łączne godziny
        - creative_hours: Godziny twórcze
        - creative_percent_avg: Średni % twórczości (ważony godzinami)
        - num_tasks: Liczba zadań
        - creative_score: Creative Score (suma task_score)
        - top_tasks_df: DataFrame z top zadaniami
        - categories_breakdown: Dict z rozkladem po kategoriach
    """
    stats = {
        "total_hours": 0.0,
        "creative_hours": 0.0,
        "creative_percent_avg": None,
        "num_tasks": 0,
        "creative_score": 0.0,
        "top_tasks_df": None,
        "categories_breakdown": {},
    }

    # Filtruj dane dla użytkownika
    person_df = df[df["person"] == person_name].copy()

    if person_df.empty:
        return stats

    # Podstawowe metryki
    stats["total_hours"] = person_df["time_hours"].sum()
    stats["creative_hours"] = person_df["creative_hours"].sum()
    stats["num_tasks"] = len(person_df)

    # Średni % twórczości (ważony godzinami)
    person_creative = person_df[person_df["creative_percent"].notna()]
    if not person_creative.empty:
        total_creative_task_hours = person_creative["time_hours"].sum()
        if total_creative_task_hours > 0:
            weighted_avg = (
                person_creative["creative_percent"] * person_creative["time_hours"]
            ).sum() / total_creative_task_hours
            stats["creative_percent_avg"] = weighted_avg

    # Creative Score
    if not person_creative.empty:
        person_creative["task_score"] = (
            person_creative["creative_hours"]
            * person_creative["creative_percent"]
            / 100
        )
        stats["creative_score"] = person_creative["task_score"].sum()

    # Top zadania (posortowane po creative_hours)
    person_with_score = person_df[person_df["creative_percent"].notna()].copy()
    if not person_with_score.empty:
        person_with_score["task_score"] = (
            person_with_score["creative_hours"]
            * person_with_score["creative_percent"]
            / 100
        )
        top_tasks = person_with_score.nlargest(10, "task_score")[
            [
                "task",
                "key",
                "time_hours",
                "creative_percent",
                "creative_hours",
                "task_score",
            ]
        ].copy()
        stats["top_tasks_df"] = top_tasks

    # Kategorie zadań (jeśli kolumna task istnieje)
    if "task" in person_df.columns:
        stats["categories_breakdown"] = _categorize_personal_tasks(person_df)

    return stats


def _categorize_personal_tasks(person_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Kategoryzuje zadania użytkownika - IDENTYCZNE kategorie jak w analyze_data.py."""
    keywords = {
        "Bug/Hotfix": [
            "bug",
            "hotfix",
            "crash",
            "błąd",
            "error",
            "problem z",
            "niezgodność",
            "uszkodz",
            "awaria",
            "napr",
            "fix",
        ],
        "Code Review": [
            "review",
            "pull request",
            "pr ",
            "feedback code",
            "sprawdzenie kodu",
            "code review",
        ],
        "Testing": [
            "test",
            "qa",
            "validation",
            "weryfikacja",
            "acceptance",
            "e2e",
            "unit",
            "testowani",
            "testy",
        ],
        "Development/Implementacja": [
            "feature",
            "implement",
            "develop",
            "build",
            "funkcj",
            "kod",
            "refactor",
            "wdrożeni",
            "stworz",
            "endpoint",
            "komponent",
            "obsług",
            "logik",
            "edycj",
            "popraw",
            "ulepsz",
            "improve",
            "edycja",
        ],
        "Analiza/Design": [
            "analiz",
            "przegląd",
            "diagram",
            "design",
            "dokumentuj",
            "architektur",
            "zapoznani",
            "sprawdz",
            "research",
            "badani",
            "ocen",
            "koncepj",
            "wymagan",
        ],
        "DevOps/Infrastruktura": [
            "deploy",
            "deployment",
            "ci/cd",
            "ci ",
            "cd ",
            "pipeline",
            "gitlab-ci",
            "docker",
            "kubernetes",
            "infra",
            "serwer",
            "baza danych",
            "monitoring",
            "logging",
            "konfiguruj",
            "infrastructure",
            "środowisk",
        ],
        "Szkolenia/Uczenie": [
            "szkoleni",
            "webinar",
            "training",
            "workshop",
            "moduł",
            "kurs",
            "nauk",
            "edukacj",
            "certyfikacj",
            "copilot",
            "samoszkoleni",
        ],
        "Administracja/Support": [
            "administraj",
            "support",
            "help desk",
            "help ",
            "incident",
            "zgłoszeni",
            "obsług",
            "wsparci",
            "mail",
            "telefon",
            "biuro",
            "dostęp",
            "uprawni",
            "konto",
        ],
        "Spotkania/Sesje": [
            "spotkani",
            "meeting",
            "call",
            "standup",
            "daily",
            "retro",
            "retrospectiv",
            "planning",
            "refinement",
            "grooming",
            "sesj",
            "briefing",
            "sync",
            "kick-off",
            "komitet",
            "posiedzeni",
            "dyskusj",
            "scrum",
        ],
    }

    categories_data = {}

    for cat, kws in keywords.items():
        mask = person_df["task"].str.lower().str.contains("|".join(kws), na=False)
        if mask.sum() > 0:
            cat_df = person_df[mask]
            categories_data[cat] = {
                "hours": cat_df["time_hours"].sum(),
                "creative_hours": cat_df["creative_hours"].sum(),
                "count": int(mask.sum()),
            }

    return categories_data
