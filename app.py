"""
Raport Czasu Pracy i Pracy Twórczej - Streamlit Dashboard

Przetwarza raporty z Jiry (hierarchiczna struktura Level 0/1/2) i worklogs,
oblicza Creative Score oraz eksportuje dane.
"""

import os

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

from helpers import (
    parse_time_to_hours,
    extract_creative_percentage,
    apply_encoding_fix_to_dataframe,
    get_top_task_per_person,
    format_display_table,
    calculate_creative_summary,
    get_dynamic_creative_filter_options,
    generate_executive_summary,
    generate_personal_stats,
    generate_personalized_insight,
    estimate_fte,
)
from export_utils import (
    export_to_csv,
    export_to_excel,
    export_worklogs_to_csv,
    export_worklogs_to_excel,
)
from config import (
    MAX_FILE_SIZE_MB,
    LARGE_FILE_WARNING_MB,
    DAY_NAMES_PL,
    DAY_ORDER,
    CHART_MIN_HEIGHT,
    CHART_ROW_HEIGHT,
)

load_dotenv()

# =============================================================================
# KONFIGURACJA STREAMLIT
# =============================================================================

st.set_page_config(
    page_title="Raport Czasu Pracy",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# PRZETWARZANIE DANYCH (CACHED)
# =============================================================================


@st.cache_data(show_spinner=False)
def process_excel_data(df: pd.DataFrame) -> pd.DataFrame:
    """Przetwarza dane z Excel do struktury raportu (Level 0/1/2)."""
    report_data = []
    current_user = None
    current_task = None

    for idx, row in df.iterrows():
        level = row["Level"]
        description = row["Users / Issues / Procent pracy twórczej"]
        key = row.get("Key", "")
        time_spent = row.get("Total Time Spent", "0:00")

        if level == 0:  # Użytkownik
            current_user = description
        elif level == 1 and current_user:  # Zadanie
            current_task = {
                "person": current_user,
                "task": description,
                "key": key if pd.notna(key) else "",
                "time_spent": time_spent,
                "time_hours": parse_time_to_hours(time_spent),
                "creative_percent": None,
                "creative_hours": 0.0,
            }
            report_data.append(current_task)
        elif level == 2 and current_task is not None and pd.notna(description):
            creative_percent = extract_creative_percentage(description)
            if creative_percent is not None:
                current_task["creative_percent"] = creative_percent
                current_task["creative_hours"] = (
                    creative_percent / 100
                ) * current_task["time_hours"]

    df_result = pd.DataFrame(report_data)

    if not df_result.empty:
        df_result["time_hours"] = df_result["time_hours"].astype(float)
        df_result["creative_hours"] = df_result["creative_hours"].astype(float)
        df_result["creative_percent"] = pd.to_numeric(
            df_result["creative_percent"], errors="coerce"
        )

    return df_result


@st.cache_data(show_spinner=False)
def process_worklogs_data(df: pd.DataFrame) -> pd.DataFrame:
    """Przetwarza dane z worklogs (płaski format z datami)."""
    df_work = df.copy()

    df_work["Start Date"] = pd.to_datetime(
        df_work["Start Date"], utc=True, errors="coerce"
    ).dt.tz_localize(None)
    df_work["time_hours"] = df_work["Time Spent"].apply(parse_time_to_hours)
    df_work["creative_percent"] = df_work["Procent pracy twórczej"].apply(
        extract_creative_percentage
    )
    df_work["creative_hours"] = (
        df_work["creative_percent"].fillna(0) / 100 * df_work["time_hours"]
    )

    df_work["person"] = df_work["Author"]
    df_work["task"] = df_work["Issue Summary"]
    df_work["key"] = df_work["Issue Key"]
    df_work["month_str"] = df_work["Start Date"].dt.strftime("%Y-%m")

    return df_work[
        [
            "person",
            "task",
            "key",
            "time_hours",
            "creative_percent",
            "creative_hours",
            "Start Date",
            "month_str",
        ]
    ]


@st.cache_data(show_spinner=False)
def aggregate_worklogs_to_report(df_worklogs: pd.DataFrame) -> pd.DataFrame:
    """Agreguje worklogs do postaci raportu głównego (per person + key + month)."""

    # Group by PERSON + TASK + MONTH - każde zadanie per osoba per miesiąc pojawia się raz
    def weighted_creative_percent(group: pd.DataFrame) -> float | None:
        valid = group.dropna(subset=["creative_percent", "time_hours"])
        if valid.empty:
            return None
        total_hours = valid["time_hours"].sum()
        if total_hours <= 0:
            return None
        weighted_sum = (valid["creative_percent"] * valid["time_hours"]).sum()
        return round(float(weighted_sum / total_hours), 1)

    # Agreguj per (person, key, month_str) - to prawidłowe!
    group_cols = (
        ["person", "key", "month_str"]
        if "month_str" in df_worklogs.columns
        else ["person", "key"]
    )

    df_agg = df_worklogs.groupby(group_cols, as_index=False).apply(
        lambda group: pd.Series(
            {
                "time_hours": group["time_hours"].sum(),
                "creative_hours": group["creative_hours"].sum(),
                "creative_percent": weighted_creative_percent(group),
                "start_date_min": group["Start Date"].min()
                if "Start Date" in group.columns
                else None,
            }
        ),
        include_groups=False,
    )

    # Dodaj task (nie ma go po groupby)
    task_mapping = df_worklogs.groupby("key")["task"].first()
    df_agg["task"] = df_agg["key"].map(task_mapping)

    # Użyj min daty jako reprezentatywnej dla zadania
    df_agg["Start Date"] = df_agg["start_date_min"]

    # Reorder columns
    if "month_str" in df_agg.columns:
        return df_agg[
            [
                "person",
                "task",
                "key",
                "time_hours",
                "creative_percent",
                "creative_hours",
                "Start Date",
                "month_str",
            ]
        ]
    else:
        return df_agg[
            [
                "person",
                "task",
                "key",
                "time_hours",
                "creative_percent",
                "creative_hours",
                "Start Date",
            ]
        ]


# =============================================================================
# AI SUMMARY (OpenRouter)
# =============================================================================

OPENROUTER_MODEL = "deepseek/deepseek-v3.2"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _anonymize_df(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Zastępuje imiona 'Osoba A', 'Osoba B', ... Zwraca (df_anon, mapping)."""
    people = sorted(df["person"].unique().tolist())
    mapping = {person: f"Osoba {chr(65 + i)}" for i, person in enumerate(people)}
    df_anon = df.copy()
    df_anon["person"] = df_anon["person"].map(mapping)
    return df_anon, mapping


def _deanonymize(text: str, mapping: dict[str, str]) -> str:
    """Podmienia anonimowe nazwy z powrotem na prawdziwe imiona.

    Obsługuje odmienione formy: 'Osoba X', 'Osoby X', 'Osobie X', 'Osobę X', 'Osobą X'.
    """
    import re

    for real, anon in mapping.items():
        letter = anon.split()[-1]  # np. "E" z "Osoba E"
        text = re.sub(
            rf"\bOsob[aąeyię]+\s+{re.escape(letter)}\b",
            real,
            text,
        )
    return text


def _data_hash(df: pd.DataFrame, month: str) -> str:
    """Fingerprint danych — zmiana hasha = nowe wywołanie AI."""
    import hashlib

    key = (
        f"{month}|{sorted(df['person'].unique().tolist())}|{df['time_hours'].sum():.1f}"
    )
    return hashlib.md5(key.encode()).hexdigest()[:10]


def _build_context_block(df_anon: pd.DataFrame, selected_month: str) -> str:
    """Buduje bogaty blok kontekstowy: dane per osoba + analiza kategorii zadań."""
    period = (
        f"Miesiąc: {selected_month}"
        if selected_month != "Wszystkie"
        else "Okres: wszystkie miesiące"
    )

    # Per-person summary
    person_lines = []
    for person, grp in df_anon.groupby("person"):
        total_h = grp["time_hours"].sum()
        creative_h = grp["creative_hours"].sum()
        avg_pct = grp["creative_percent"].mean()
        score = (grp["creative_hours"] * grp["creative_percent"].fillna(0) / 100).sum()
        person_lines.append(
            f"  - {person}: {total_h:.1f}h łącznie, {creative_h:.1f}h twórczych, "
            f"śr. {avg_pct:.0f}% kreatywności, Score: {score:.1f}"
        )

    # Category analysis via generate_executive_summary (uses same keyword logic)
    exec_summary = generate_executive_summary(df_anon)
    category_lines = []
    all_insights = (
        exec_summary.get("insights_top3_cats", [])
        + exec_summary.get("insights", [])
        + exec_summary.get("insights_team", [])
    )
    for insight in all_insights:
        # Strip emoji prefix and format as plain context
        clean = insight.strip()
        if clean:
            category_lines.append(f"  - {clean}")

    person_block = "\n".join(person_lines)
    category_block = (
        "\n".join(category_lines)
        if category_lines
        else "  (brak danych kategorycznych)"
    )

    return (
        f"{period}\n\n"
        f"Dane per osoba (zanonimizowane):\n{person_block}\n\n"
        f"Analiza automatyczna (kontekst dla AI):\n{category_block}"
    )


def call_openrouter(
    df: pd.DataFrame, selected_month: str, mode: str = "summary"
) -> tuple[str, dict[str, str]]:
    """Wysyła zanonimizowane dane do OpenRouter i zwraca (odpowiedź, mapping).

    mode: "summary" — pełne podsumowanie menedżerskie
          "observations" — lista konkretnych obserwacji z wnioskami biznesowymi
    """
    import requests

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Brak klucza OPENROUTER_API_KEY w pliku .env")

    df_anon, mapping = _anonymize_df(df)
    context = _build_context_block(df_anon, selected_month)

    if mode == "full":
        prompt = (
            "Jesteś ekspertem analizy pracy twórczej i menedżerskim doradcą. "
            "Na podstawie poniższych danych zespołu przygotuj analizę po polsku w dwóch częściach.\n\n"
            f"{context}\n\n"
            "CZĘŚĆ 1 — OBSERWACJE (6–8 punktów):\n"
            "- Każda obserwacja musi zawierać LICZBY z danych ORAZ interpretację biznesową\n"
            "- Wskazuj wzorce, ryzyka, dysproporcje, zaskakujące korelacje\n"
            "- Nie powtarzaj suchych danych — dodaj wniosek 'co to oznacza dla zespołu'\n"
            "- Używaj emoji na początku: ✅ dobry trend, ⚠️ uwaga, ⛔ ryzyko, 📉 regres, 🏆 wyróżnienie\n"
            "Format każdej obserwacji: 'emoji **Temat:** treść z liczbami i wnioskiem'\n\n"
            "Po obserwacjach wpisz dokładnie ten separator (nic więcej w tej linii):\n"
            "===REKOMENDACJE===\n\n"
            "CZĘŚĆ 2 — REKOMENDACJE (3–5 konkretnych punktów dla managera):\n"
            "- Każda rekomendacja musi być konkretna i powiązana z danymi\n"
            "- Format: '**N. Tytuł:** opis działania'\n"
            "- Nie powtarzaj obserwacji — skup się na tym CO ZROBIĆ\n"
            "NIE dodawaj żadnych innych nagłówków ani podsumowań."
        )
    elif mode == "observations":
        prompt = (
            "Jesteś ekspertem analizy pracy twórczej i menedżerskim doradcą. "
            "Na podstawie poniższych danych zespołu napisz 6–8 wnikliwych obserwacji menedżerskich po polsku.\n\n"
            f"{context}\n\n"
            "Wymagania dla obserwacji:\n"
            "- Każda obserwacja musi zawierać LICZBY z danych ORAZ interpretację biznesową\n"
            "- Wskazuj wzorce, ryzyka, dysproporcje, zaskakujące korelacje\n"
            "- Nie powtarzaj suchych danych — dodaj wniosek 'co to oznacza dla zespołu'\n"
            "- Używaj emoji na początku: ✅ dobry trend, ⚠️ uwaga, ⛔ ryzyko, 📉 regres, 🏆 wyróżnienie\n"
            "Format każdej obserwacji: 'emoji **Temat:** treść z liczbami i wnioskiem'\n"
            "NIE dodawaj nagłówków ani podsumowania — tylko lista obserwacji."
        )
    else:
        prompt = (
            "Jesteś analitykiem pracy twórczej. Przygotuj zwięzłe podsumowanie menedżerskie po polsku.\n\n"
            f"{context}\n\n"
            "Podsumowanie powinno zawierać:\n"
            "1. Ogólna ocena zespołu (2–3 zdania, liczby)\n"
            "2. Osoby wyróżniające się pozytywnie i negatywnie\n"
            "3. Rekomendacje dla managera (3–5 konkretnych punktów)\n"
            "4. Obszary ryzyka lub do poprawy\n\n"
            "Operuj liczbami z danych. Format: markdown. Bądź zwięzły."
        )

    resp = requests.post(
        OPENROUTER_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000 if mode == "full" else 1400,
        },
        timeout=60,
    )
    resp.raise_for_status()
    ai_text = resp.json()["choices"][0]["message"]["content"]
    return _deanonymize(ai_text, mapping), mapping


def _compute_team_health(df: pd.DataFrame) -> dict:
    """Oblicza syntetyczny wskaźnik zdrowia zespołu (0–100)."""
    coverage = df["creative_percent"].notna().mean() * 100
    avg_creative = (
        df.loc[df["creative_percent"].notna(), "creative_percent"].mean() or 0
    )
    scores = df.groupby("person")["creative_hours"].apply(
        lambda h: (h * df.loc[h.index, "creative_percent"].fillna(0) / 100).sum()
    )
    consistency = max(0, 100 - scores.std() * 2) if len(scores) > 1 else 100

    health = 0.35 * coverage + 0.45 * avg_creative + 0.20 * consistency
    health = min(100, max(0, health))

    if health >= 70:
        label, color = "Dobry", "#2ecc71"
    elif health >= 45:
        label, color = "Średni", "#f39c12"
    else:
        label, color = "Wymaga uwagi", "#e74c3c"

    return {
        "score": health,
        "label": label,
        "color": color,
        "coverage": coverage,
        "avg_creative": avg_creative,
    }


def render_team_health(df: pd.DataFrame):
    """Wyświetla kafelkę z syntetycznym wskaźnikiem zdrowia twórczego zespołu."""
    h = _compute_team_health(df)
    score = h["score"]
    filled = int(round(score / 10))
    bar = "█" * filled + "░" * (10 - filled)

    st.markdown(
        f"""
<div style="background:#1e1e2e;border-radius:10px;padding:16px 20px;margin-bottom:8px">
  <span style="font-size:13px;color:#aaa;text-transform:uppercase;letter-spacing:1px">Creative Health Score</span><br>
  <span style="font-size:42px;font-weight:700;color:{h["color"]}">{score:.0f}</span>
  <span style="font-size:16px;color:#aaa">/100 &nbsp;·&nbsp; {h["label"]}</span><br>
  <span style="font-family:monospace;font-size:18px;color:{h["color"]};letter-spacing:2px">{bar}</span><br>
  <span style="font-size:12px;color:#888">pokrycie {h["coverage"]:.0f}% · śr. twórczość {h["avg_creative"]:.0f}%</span>
</div>
""",
        unsafe_allow_html=True,
    )


def render_anomaly_alerts(df: pd.DataFrame):
    """Automatycznie wykrywa i wyświetla alerty o anomaliach w danych."""
    alerts = []

    # 1. Osoby z niskim pokryciem danych
    per_person = df.groupby("person")
    for person, grp in per_person:
        coverage = grp["creative_percent"].notna().mean() * 100
        if coverage < 30:
            alerts.append(
                (
                    "warning",
                    f"**{person}** ma tylko {coverage:.0f}% zadań z uzupełnionym % twórczości",
                )
            )

    # 2. Outlierzy Creative Score
    scores = df.groupby("person")["creative_hours"].apply(
        lambda h: (h * df.loc[h.index, "creative_percent"].fillna(0) / 100).sum()
    )
    if len(scores) >= 3:
        mean_s, std_s = scores.mean(), scores.std()
        for person, score in scores.items():
            if score > mean_s + 2 * std_s:
                alerts.append(
                    (
                        "info",
                        f"**{person}** wyróżnia się Creative Score {score:.1f} (śr. zespołu: {mean_s:.1f})",
                    )
                )
            elif score < mean_s - 1.5 * std_s and score < 15:
                alerts.append(
                    (
                        "warning",
                        f"**{person}** ma bardzo niski Creative Score: {score:.1f} (śr. {mean_s:.1f})",
                    )
                )

    # 3. Ogólnie niskie średnie twórczości
    avg_pct = df.loc[df["creative_percent"].notna(), "creative_percent"].mean()
    if avg_pct < 40:
        alerts.append(
            (
                "error",
                f"Średni poziom pracy twórczej w zespole wynosi tylko **{avg_pct:.0f}%**",
            )
        )

    if not alerts:
        return

    with st.expander(f"⚠️ Alerty ({len(alerts)})", expanded=True):
        for kind, msg in alerts:
            if kind == "error":
                st.error(msg)
            elif kind == "warning":
                st.warning(msg)
            else:
                st.info(msg)


# =============================================================================
# KOMPONENTY UI
# =============================================================================


def render_sidebar():
    """Renderuje sidebar z uploaderami i informacjami."""
    with st.sidebar:
        st.header("📁 Wgraj pliki")

        if st.button("🔄 Wyczyść cache", help="Użyj jeśli procenty się nie ładują"):
            st.cache_data.clear()
            st.success("✅ Cache wyzczyszczony!")

        st.markdown("---")

        st.subheader("📋 Worklogs (główne źródło)")
        worklogs_file = st.file_uploader(
            "Wgraj Worklogs (.xlsx)",
            type=["xlsx"],
            key="worklogs_file",
            help="Worklogs: Start Date, Issue Key, Time Spent, Procent pracy twórczej, Author",
        )
        with st.expander("Wymagane kolumny"):
            st.markdown(
                "- `Author` — imię i nazwisko\n"
                "- `Issue Key` — klucz zadania (np. PROJ-123)\n"
                "- `Issue Summary` — tytuł zadania\n"
                "- `Start Date` — data wpisu\n"
                "- `Time Spent` — czas (np. 2h 30m)\n"
                "- `Procent pracy twórczej` — liczba 0–100"
            )

        st.markdown("---")

        st.subheader("📊 Raport główny (opcjonalnie)")
        uploaded_file = st.file_uploader(
            "Raport Level 0/1/2 (.xlsx)",
            type=["xlsx"],
            key="main_report",
            help="Dla porównania: struktura Level 0/1/2",
        )

        # Walidacja rozmiaru
        if worklogs_file:
            file_size_mb = worklogs_file.size / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                st.error(
                    f"❌ Plik zbyt duży: {file_size_mb:.1f}MB (max {MAX_FILE_SIZE_MB}MB)"
                )
                worklogs_file = None
            elif file_size_mb > LARGE_FILE_WARNING_MB:
                st.warning(f"⚠️ Duży plik: {file_size_mb:.1f}MB")

        st.markdown("---")

        # Filtr miesiąca
        months_in_state = st.session_state.get("months_available", [])
        month_options = ["Wszystkie"] + months_in_state
        # Domyślnie wybierz najnowszy miesiąc (index 1), jeśli dostępny
        default_month_index = 1 if len(months_in_state) > 0 else 0
        selected_month = st.selectbox(
            "📅 Filtruj miesiąc",
            options=month_options,
            index=default_month_index,
            help="Filtruje Dashboard i Personal Dashboard do wybranego miesiąca.",
        )

        # Wyklucz osoby — hardcoded defaults zawsze w opcjach, nawet jeśli nie ma ich w danych
        _default_excluded = ["Justyna Kalota", "Piotr Janeczek"]
        _all_people = st.session_state.get("all_people", [])
        _options = sorted(set(_all_people) | set(_default_excluded))
        excluded_people = st.multiselect(
            "🚫 Wyklucz osoby z dashboardu",
            options=_options,
            default=_default_excluded,
            help="Osoby wykluczone nie pojawiają się w rankingach ani Personal Dashboard (nadal widoczne w metrykach głównych).",
        )

        st.markdown("---")
        st.header("ℹ️ Informacje")
        st.markdown(
            """
        **Creative Score:**
        `godz_twórcze × (% / 100)`

        | Wynik | Interpretacja |
        |-------|---------------|
        | < 15  | Niski         |
        | 15–50 | Średni        |
        | > 50  | Wysoki        |
        """
        )

    return worklogs_file, uploaded_file, excluded_people, selected_month


def render_metrics(
    df: pd.DataFrame, selected_month: str = "Wszystkie", excluded_count: int = 0
):
    """Renderuje główne metryki na górze strony."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("👥 Liczba osób", df["person"].nunique())

    with col2:
        st.metric("📋 Liczba zadań", len(df))

    with col3:
        total_hours = df["time_hours"].sum()
        st.metric("⏰ Łączne godziny", f"{total_hours:.1f}h")

    with col4:
        creative_tasks = df["creative_percent"].notna().sum()
        st.metric("🎨 Zadania z %", creative_tasks)

    # Pokaż zakres danych gdy wybrano "Wszystkie"
    caption_parts = []
    if selected_month == "Wszystkie" and "month_str" in df.columns:
        months_in_df = sorted(df["month_str"].dropna().unique())
        if len(months_in_df) > 1:
            caption_parts.append(
                f"📅 Dane zbiorcze za {len(months_in_df)} miesięcy: "
                f"{months_in_df[0]} – {months_in_df[-1]}"
            )
        elif len(months_in_df) == 1:
            caption_parts.append(f"📅 Dane za: {months_in_df[0]}")
    if excluded_count > 0:
        caption_parts.append(f"{excluded_count} os. wykluczone z sidebara")
    if caption_parts:
        st.caption(" · ".join(caption_parts))


def _render_ai_observation_tiles(text: str):
    """Parsuje odpowiedź AI i wyświetla każdą obserwację jako kafelek st.info()."""

    # Rozdziel linie, każda niepusta linia zaczynająca się od emoji lub "- " to osobna obserwacja
    lines = [ln.strip().lstrip("- ").strip() for ln in text.splitlines()]
    observations = [ln for ln in lines if ln and not ln.startswith("#")]

    # Wyświetl w dwóch kolumnach jak rule-based
    col_a, col_b = st.columns(2)
    for i, obs in enumerate(observations):
        with col_a if i % 2 == 0 else col_b:
            # Dobierz typ kafelka na podstawie emoji
            if any(c in obs[:4] for c in ("⛔", "🔴")):
                st.error(obs)
            elif any(c in obs[:4] for c in ("⚠️", "📉")):
                st.warning(obs)
            elif any(c in obs[:4] for c in ("✅", "🏆", "💪")):
                st.success(obs)
            else:
                st.info(obs)


def render_executive_summary(
    df: pd.DataFrame, selected_month: str = "Wszystkie", show_ai: bool = True
):
    """Renderuje Executive Summary - kluczowe insights jako tabele."""
    summary = generate_executive_summary(df)

    st.markdown("## 📋 Executive Summary")

    num_people = df["person"].nunique()
    avg_creative_hours_per_person = (
        summary["total_creative_hours"] / num_people if num_people > 0 else 0
    )
    avg_total_hours_per_person = (
        summary["total_hours"] / num_people if num_people > 0 else 0
    )

    # Normalizacja score po etacie (w tle — wpływa na top/bottom performer)
    _person_hours = df.groupby("person")["time_hours"].sum()
    _fte_map = estimate_fte(_person_hours)
    _part_timers = [p for p, v in _fte_map.items() if v["is_part_time"]]

    # Policz znormalizowane score per osoba
    _df_s = df[df["creative_percent"].notna()].copy()
    _df_s["_ts"] = _df_s["creative_hours"] * _df_s["creative_percent"] / 100
    _raw_scores = _df_s.groupby("person")["_ts"].sum()
    _norm_scores = pd.Series(
        {
            p: s / _fte_map.get(p, {"fte_ratio": 1.0})["fte_ratio"]
            for p, s in _raw_scores.items()
        }
    ).sort_values(ascending=False)

    # Top / bottom performer na podstawie znormalizowanych score
    top_performer_norm = _norm_scores.index[0] if not _norm_scores.empty else None
    top_performer_score_norm = _norm_scores.iloc[0] if not _norm_scores.empty else 0.0
    bottom_performer_norm = _norm_scores.index[-1] if len(_norm_scores) > 1 else None
    bottom_performer_score_norm = (
        _norm_scores.iloc[-1] if len(_norm_scores) > 1 else None
    )

    # --- Sekcja 1: Zespół ---
    st.markdown("#### 👥 Zespół")
    t1, t2, t3, t4 = st.columns(4)

    with t1:
        st.metric("👤 Liczba osób", num_people)

    with t2:
        st.metric(
            "⏰ Śr. godziny / osoba",
            f"{avg_total_hours_per_person:.1f}h",
        )

    with t3:
        st.metric(
            "✨ Śr. godz. twórcze / osoba",
            f"{avg_creative_hours_per_person:.1f}h",
        )

    with t4:
        if summary["avg_creative_percent"]:
            st.metric(
                "🎨 Śr. % twórczości",
                f"{summary['avg_creative_percent']:.0f}%",
                delta=f"pokrycie: {summary['data_coverage']:.0f}%",
            )
        else:
            st.metric("🎨 Śr. % twórczości", "—")

    st.markdown("#### 🏆 Wyróżnienia indywidualne")

    # Najwyższy % twórczości
    prod = summary.get("productivity_table")
    best_creative_pct_person = None
    best_creative_pct_val = None
    most_hours_row = None
    if prod is not None and not prod.empty:
        valid_pct = prod[prod["% Pracy twórczej"].notna()]
        if not valid_pct.empty:
            best_idx = valid_pct["% Pracy twórczej"].idxmax()
            best_creative_pct_person = valid_pct.loc[best_idx, "Osoba"]
            best_creative_pct_val = valid_pct.loc[best_idx, "% Pracy twórczej"]
        most_hours_row = prod.loc[prod["Łącznie [h]"].idxmax()]

    i1, i2, i3, i4 = st.columns(4)

    with i1:
        if top_performer_norm:
            st.metric(
                "🥇 Najwyższy Creative Score",
                top_performer_norm,
                delta=f"Score: {top_performer_score_norm:.1f}",
            )
        else:
            st.metric("🥇 Najwyższy Creative Score", "—")

    with i2:
        if bottom_performer_norm:
            st.metric(
                "📉 Najniższy Creative Score",
                bottom_performer_norm,
                delta=f"Score: {bottom_performer_score_norm:.1f}",
                delta_color="inverse",
            )
        else:
            st.metric("📉 Najniższy Creative Score", "—")

    with i3:
        if best_creative_pct_person:
            st.metric(
                "🎨 Najwyższy % twórczości",
                best_creative_pct_person,
                delta=f"{best_creative_pct_val:.0f}%",
            )
        else:
            st.metric("🎨 Najwyższy % twórczości", "—")

    with i4:
        if most_hours_row is not None:
            st.metric(
                "⏱️ Najwięcej godzin",
                most_hours_row["Osoba"],
                delta=f"{most_hours_row['Łącznie [h]']:.1f}h",
            )
        else:
            st.metric("⏱️ Najwięcej godzin", "—")

    _caption = "💡 **Śr. % twórczości** jest ważony godzinami."
    if _part_timers:
        _caption += f" Score znormalizowany proporcjonalnie do wymiaru etatu ({', '.join(_part_timers)})."
    st.caption(_caption)

    # Dynamiczne insighty — struktura: top 3 kategorie + 2 najbardziej znaczące + 1-2 teamowe
    top3 = summary.get("insights_top3_cats", [])
    other_cats = summary.get("insights", [])
    team = summary.get("insights_team", [])

    has_any = top3 or other_cats or team
    if has_any:
        _has_ai = bool(os.getenv("OPENROUTER_API_KEY", "").strip()) and show_ai
        _has_ai_result = "ai_full" in st.session_state and show_ai

        obs_col, btn_col = st.columns([6, 2])
        with obs_col:
            st.markdown(
                "### 🤖 Kluczowe obserwacje"
                if _has_ai_result
                else "### Kluczowe obserwacje"
            )
        with btn_col:
            if _has_ai:
                _btn_label = (
                    "🔄 Odśwież analizę" if _has_ai_result else "✨ Analizuj z AI"
                )
                if st.button(_btn_label, key="refresh_obs", use_container_width=True):
                    with st.spinner("Analizuję dane..."):
                        try:
                            _full_text, _ = call_openrouter(
                                df, selected_month, mode="full"
                            )
                            st.session_state["ai_full"] = _full_text
                            st.session_state["ai_full_hash"] = _data_hash(
                                df, selected_month
                            )
                            # Wyczyść stare klucze z poprzedniej wersji
                            st.session_state.pop("ai_observations", None)
                            st.session_state.pop("ai_summary", None)
                        except Exception as _exc:
                            st.warning(f"AI niedostępne: {_exc}")

        if _has_ai_result:
            # Podziel odpowiedź na obserwacje i rekomendacje
            _raw = st.session_state["ai_full"]
            _parts = _raw.split("===REKOMENDACJE===")
            _obs_part = _parts[0].strip()
            _rec_part = _parts[1].strip() if len(_parts) > 1 else ""

            _render_ai_observation_tiles(_obs_part)

            if _rec_part:
                st.markdown("---")
                st.markdown("### 💡 Rekomendacje dla managera")
                st.markdown(_rec_part)
        else:

            def _severity(text: str) -> int:
                if "⛔" in text:
                    return 4
                if "⚠️" in text or "📉" in text:
                    return 3
                if "📋" in text:
                    return 2
                return 1

            secondary = sorted(other_cats, key=_severity, reverse=True)[:2]
            team_sel = sorted(team, key=_severity, reverse=True)[:2]
            visible = top3 + secondary + team_sel

            col_a, col_b = st.columns(2)
            for i, insight in enumerate(visible):
                with col_a if i % 2 == 0 else col_b:
                    st.info(insight)

            remaining_all = (
                sorted(other_cats, key=_severity, reverse=True)[2:]
                + sorted(team, key=_severity, reverse=True)[2:]
            )
            if remaining_all:
                with st.expander(f"Pozostałe obserwacje ({len(remaining_all)})"):
                    col_c, col_d = st.columns(2)
                    for i, insight in enumerate(remaining_all):
                        with col_c if i % 2 == 0 else col_d:
                            st.info(insight)

    # Tabele z danymi
    st.markdown("---")

    # PODSUMOWANIE PRACY TWÓRCZEJ
    st.markdown("### 🎯 Podsumowanie pracy twórczej")
    creative_summary = calculate_creative_summary(df)
    st.dataframe(
        creative_summary,
        column_config={
            "Łączne godziny": st.column_config.NumberColumn(format="%.1f h"),
            "Godziny twórcze": st.column_config.NumberColumn(format="%.1f h"),
            "% Pracy twórczej": st.column_config.NumberColumn(format="%.1f%%"),
            "Pokrycie danymi": st.column_config.NumberColumn(format="%.0f%%"),
        },
        width="stretch",
        hide_index=False,
    )
    st.caption(
        "**Jak liczymy % Pracy twórczej:** "
        "Godziny twórcze ÷ Łączne godziny (tylko dla zadań z przypisanym % twórczości)."
    )

    # Wykres godzin: łączne vs twórcze per osoba
    if not creative_summary.empty:
        chart_df = creative_summary.reset_index().rename(
            columns={
                "index": "person",
                "Łączne godziny": "total",
                "Godziny twórcze": "creative",
            }
        )
        chart_df = chart_df.sort_values("total", ascending=True)
        fig_cs = go.Figure()
        fig_cs.add_trace(
            go.Bar(
                y=chart_df["person"],
                x=chart_df["total"],
                name="Łączne godziny",
                orientation="h",
                marker_color="#4a4a6a",
            )
        )
        fig_cs.add_trace(
            go.Bar(
                y=chart_df["person"],
                x=chart_df["creative"],
                name="Godziny twórcze",
                orientation="h",
                marker=dict(
                    color=chart_df["creative"], colorscale="Plasma", showscale=False
                ),
            )
        )
        fig_cs.update_layout(
            barmode="overlay",
            height=max(CHART_MIN_HEIGHT, len(chart_df) * CHART_ROW_HEIGHT),
            xaxis_title="Godziny",
            yaxis_title="",
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_cs, width="stretch")

    # EFEKTYWNOŚĆ
    if summary["efficiency_table"] is not None:
        st.markdown("### ⚡ Analiza efektywności")
        eff_df = summary["efficiency_table"].copy()

        # Formatowanie
        eff_df["Średni % twórczości"] = eff_df["Średni % twórczości"].apply(
            lambda x: f"{x:.0f}%" if pd.notna(x) else "—"
        )

        st.dataframe(eff_df, width="stretch", hide_index=False)
        st.caption(
            "**Jak liczymy:**\n"
            "- Średni % twórczości: Zwykła średnia arytmetyczna % dla wszystkich zadań w danej kategorii\n"
            "(np. dla 'Długie zadania': bierzemy wszystkie taski ≥10h i liczymy ich średni % twórczości)"
        )

    # WSPÓŁPRACA
    if summary["collaboration_table"] is not None:
        st.markdown("### 🤝 Współpraca w zespole")
        collab_df = summary["collaboration_table"].copy()

        st.dataframe(collab_df, width="stretch", hide_index=True)
        st.caption("Najczęstsze pary współpracujące nad wspólnymi zadaniami")

    # DODATKOWE STATYSTYKI
    with st.expander("📊 Dodatkowe statystyki", expanded=False):
        # PRODUKTYWNOŚĆ
        if summary["productivity_table"] is not None:
            st.markdown("#### 📊 Produktywność zespołu")
            prod_df = summary["productivity_table"].copy()

            # Formatowanie
            prod_df["Łącznie [h]"] = prod_df["Łącznie [h]"].apply(lambda x: f"{x:.1f}")
            prod_df["Twórcze [h]"] = prod_df["Twórcze [h]"].apply(lambda x: f"{x:.1f}")
            prod_df["% Pracy twórczej"] = prod_df["% Pracy twórczej"].apply(
                lambda x: f"{x:.0f}%" if pd.notna(x) else "—"
            )
            prod_df["Creative Score"] = prod_df["Creative Score"].apply(
                lambda x: f"{x:.1f}" if pd.notna(x) else "—"
            )
            prod_df["Średnia [h/zadanie]"] = prod_df["Średnia [h/zadanie]"].apply(
                lambda x: f"{x:.1f}"
            )

            st.dataframe(prod_df, width="stretch", hide_index=False)
            st.caption(
                "**Ranking per osoba — metryki produktywności i jakości:**\n"
                "- **Liczba zadań:** ile zadań osoba realizowała\n"
                "- **Łącznie [h]:** suma wszystkich godzin\n"
                "- **Twórcze [h]:** suma godzin faktycznie twórczych (wkład w wartość)\n"
                "- **% Pracy twórczej:** jaki procent czasu to była praca twórcza (średnia ważona godzinami)\n"
                "- **Creative Score:** suma (creative_hours × creative_% / 100) ze wszystkich zadań — identyczna formuła jak w Rankingu\n"
                "- **Średnia [h/zadanie]:** jak szybko osoba załatwia sprawy (efektywność)\n\n"
                "**Tabela sortowana po Creative Score** — ten sam ranking co w Executive Summary i Rankingu."
            )


def render_top_tasks_table(df: pd.DataFrame):
    """Renderuje tabelę i wykres Top Zadań per osoba."""
    st.markdown("## 🎯 Ranking Creative Score")

    top_tasks_df = get_top_task_per_person(df)

    if top_tasks_df.empty:
        st.info("Brak danych do wyświetlenia")
        return

    # Normalizacja score po etacie — w tle, bez widocznych kolumn FTE
    person_total_hours = df.groupby("person")["time_hours"].sum()
    fte_map = estimate_fte(person_total_hours)
    part_time_people = [p for p, v in fte_map.items() if v["is_part_time"]]

    top_tasks_df = top_tasks_df.copy()
    top_tasks_df["fte_ratio"] = top_tasks_df["person"].map(
        lambda p: fte_map.get(p, {}).get("fte_ratio", 1.0)
    )
    top_tasks_df["score_normalized"] = (
        top_tasks_df["total_score"] / top_tasks_df["fte_ratio"]
    )

    top_tasks_df_sorted = top_tasks_df.sort_values("score_normalized", ascending=False)

    # Formatuj do wyświetlenia
    display_df = format_display_table(top_tasks_df_sorted)
    display_df["score_normalized"] = top_tasks_df_sorted["score_normalized"].apply(
        lambda x: f"{x:.1f}"
    )

    display_cols = [
        "person",
        "score_normalized",
        "task",
        "key",
        "time_hours",
        "creative_percent",
        "creative_hours",
        "score",
        "status",
    ]
    display_names = [
        "👤 Osoba",
        "🏆 Creative Score",
        "📋 Najlepsze zadanie",
        "🔑 Klucz",
        "⏰ Czas",
        "🎨 %",
        "✨ Godz. twórcze",
        "💎 Score zadania",
        "📊 Typ",
    ]

    st.dataframe(
        display_df[display_cols]
        .rename(columns=dict(zip(display_cols, display_names)))
        .reset_index(drop=True),
        hide_index=True,
        width="stretch",
    )

    _caption = "**Creative Score** = suma (creative_hours × creative_% / 100) ze wszystkich zadań."
    if part_time_people:
        _fte_labels = ", ".join(
            f"{p} (~{fte_map[p]['fte_label']} etatu)" for p in part_time_people
        )
        _caption += f" Wynik wyrównany proporcjonalnie do pełnego etatu: {_fte_labels}."
    st.caption(_caption)

    # Wykres
    fig = px.bar(
        top_tasks_df_sorted,
        x="score_normalized",
        y="person",
        orientation="h",
        title="Ranking Creative Score",
        labels={"score_normalized": "Creative Score", "person": "Osoba"},
        color="score_normalized",
        color_continuous_scale="Plasma",
        hover_data={
            "score_normalized": ":.1f",
            "total_score": ":.1f",
            "time_hours": True,
            "creative_hours": True,
            "creative_percent": True,
        },
        category_orders={"person": top_tasks_df_sorted["person"].tolist()},
    )
    fig.update_layout(
        height=max(CHART_MIN_HEIGHT, len(top_tasks_df_sorted) * CHART_ROW_HEIGHT),
        xaxis_title="Creative Score",
        yaxis_title="",
        coloraxis_colorbar_title="Score",
    )
    st.plotly_chart(fig, width="stretch")


def render_detailed_data(df: pd.DataFrame):
    """Renderuje szczegółowe dane z filtrami i wykresami."""
    st.markdown("## 🔍 Szczegółowe dane")

    # Filtry
    col1, col2, col3 = st.columns(3)

    with col1:
        selected_person = st.selectbox(
            "👤 Wybierz osobę:",
            ["Wszystkie"] + sorted(df["person"].unique().tolist()),
        )

    with col2:
        # Dynamiczne opcje filtra
        filter_options = get_dynamic_creative_filter_options(df)
        creative_filter = st.selectbox(
            "🎨 Filtruj po pracy twórczej:",
            filter_options,
        )

    with col3:
        search_term = st.text_input("🔍 Szukaj w zadaniach:", "")

    # Filtrowanie
    df_filtered = df.copy()

    if selected_person != "Wszystkie":
        df_filtered = df_filtered[df_filtered["person"] == selected_person]

    if creative_filter != "Wszystkie":
        if creative_filter == "Z danymi":
            df_filtered = df_filtered[df_filtered["creative_percent"].notna()]
        elif creative_filter == "Bez danych":
            df_filtered = df_filtered[df_filtered["creative_percent"].isna()]
        else:
            percent_val = int(creative_filter.replace("%", ""))
            df_filtered = df_filtered[df_filtered["creative_percent"] == percent_val]

    if search_term:
        df_filtered = df_filtered[
            df_filtered["task"].str.contains(search_term, case=False, na=False)
            | df_filtered["key"].str.contains(search_term, case=False, na=False)
        ]

    # Tabela
    COLUMN_OPTIONS = {
        "👤 Osoba": "person",
        "📋 Zadanie": "task",
        "🔑 Klucz": "key",
        "⏰ Czas": "time_display",
        "🎨 %": "creative_percent_display",
        "✨ Godz. twórcze": "creative_hours_display",
    }
    selected_cols = st.multiselect(
        "Kolumny:",
        options=list(COLUMN_OPTIONS.keys()),
        default=list(COLUMN_OPTIONS.keys()),
        key="detail_columns",
    )
    if not selected_cols:
        selected_cols = list(COLUMN_OPTIONS.keys())

    display_df = df_filtered.copy()
    display_df["time_hours"] = display_df["time_hours"].astype(float)
    display_df["creative_hours"] = display_df["creative_hours"].astype(float)
    display_df["creative_percent"] = pd.to_numeric(
        display_df["creative_percent"], errors="coerce"
    )
    display_df["creative_percent_display"] = display_df["creative_percent"].apply(
        lambda x: f"{int(x)}%" if pd.notna(x) else "Brak danych"
    )
    display_df["creative_hours_display"] = display_df["creative_hours"].apply(
        lambda x: f"{x:.1f}h" if pd.notna(x) else "Brak danych"
    )
    display_df["time_display"] = display_df["time_hours"].apply(lambda x: f"{x:.1f}h")

    columns_to_show = [COLUMN_OPTIONS[c] for c in selected_cols]
    col_config = {
        "person": st.column_config.TextColumn("👤 Osoba", width="medium"),
        "task": st.column_config.TextColumn("📋 Zadanie", width="large"),
        "key": st.column_config.TextColumn("🔑 Klucz", width="small"),
        "time_display": st.column_config.TextColumn("⏰ Czas", width="small"),
        "creative_percent_display": st.column_config.TextColumn("🎨 %", width="small"),
        "creative_hours_display": st.column_config.TextColumn(
            "✨ Godz. twórcze", width="small"
        ),
    }

    st.dataframe(
        display_df[columns_to_show],
        column_config={k: v for k, v in col_config.items() if k in columns_to_show},
        width="stretch",
        hide_index=True,
    )

    return df_filtered, display_df


def render_charts(df_filtered: pd.DataFrame):
    """Renderuje wykresy analityczne."""
    with st.expander("📊 Wykresy analityczne", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Czas pracy na osobę**")
            person_hours = (
                df_filtered.groupby("person")["time_hours"]
                .sum()
                .sort_values(ascending=True)
            )

            fig1 = px.bar(
                x=person_hours.values,
                y=person_hours.index,
                orientation="h",
                title="Łączne godziny pracy",
                labels={"x": "Godziny", "y": "Osoba"},
            )
            fig1.update_layout(height=400)
            st.plotly_chart(fig1, width="stretch")

        with col2:
            st.markdown("**Rozkład pracy twórczej**")
            creative_data = df_filtered.dropna(subset=["creative_percent"])
            if not creative_data.empty:
                # Grupowanie w przedziały
                def categorize_creative(pct):
                    if pct == 0:
                        return "0%"
                    elif pct <= 20:
                        return "1-20%"
                    elif pct <= 40:
                        return "21-40%"
                    elif pct <= 60:
                        return "41-60%"
                    elif pct <= 80:
                        return "61-80%"
                    else:
                        return "81-100%"

                creative_data_copy = creative_data.copy()
                creative_data_copy["category"] = creative_data_copy[
                    "creative_percent"
                ].apply(categorize_creative)
                creative_counts = creative_data_copy["category"].value_counts()

                # Sortuj kategorie
                category_order = [
                    "0%",
                    "1-20%",
                    "21-40%",
                    "41-60%",
                    "61-80%",
                    "81-100%",
                ]
                creative_counts = creative_counts.reindex(
                    [c for c in category_order if c in creative_counts.index]
                )

                fig2 = px.pie(
                    values=creative_counts.values,
                    names=creative_counts.index,
                    title="Zadania według poziomu twórczości",
                )
                fig2.update_traces(textposition="inside", textinfo="percent+label")
                fig2.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig2, width="stretch")
            else:
                st.info("Brak danych o pracy twórczej.")

        # Dodatkowe wykresy
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Godziny twórcze per osoba i poziom**")

            creative_data = df_filtered.dropna(subset=["creative_percent"])
            if not creative_data.empty and len(creative_data) > 0:
                # Kategoryzuj % twórczości
                def categorize_creative(pct):
                    if pct <= 20:
                        return "0-20%"
                    elif pct <= 40:
                        return "21-40%"
                    elif pct <= 60:
                        return "41-60%"
                    elif pct <= 80:
                        return "61-80%"
                    else:
                        return "81-100%"

                creative_data_copy = creative_data.copy()
                creative_data_copy["category"] = creative_data_copy[
                    "creative_percent"
                ].apply(categorize_creative)

                # Suma godzin twórczych per osoba i kategoria
                heatmap_data = (
                    creative_data_copy.groupby(["person", "category"])["creative_hours"]
                    .sum()
                    .reset_index()
                )

                category_order = ["0-20%", "21-40%", "41-60%", "61-80%", "81-100%"]

                heatmap_pivot = heatmap_data.pivot(
                    index="person", columns="category", values="creative_hours"
                ).fillna(0)

                # Reorder columns
                heatmap_pivot = heatmap_pivot.reindex(
                    columns=[c for c in category_order if c in heatmap_pivot.columns]
                )

                fig_heatmap = px.imshow(
                    heatmap_pivot,
                    labels=dict(
                        x="Poziom twórczości", y="Osoba", color="Godz. twórcze"
                    ),
                    x=heatmap_pivot.columns,
                    y=heatmap_pivot.index,
                    color_continuous_scale="Plasma",
                    aspect="auto",
                )
                fig_heatmap.update_layout(height=400)
                st.plotly_chart(fig_heatmap, width="stretch")
            else:
                st.info("Brak danych do heatmapy")

        with col2:
            st.markdown("**Czas pracy vs Czas twórczy**")
            comparison_data = (
                df_filtered.groupby("person")
                .agg({"time_hours": "sum", "creative_hours": "sum"})
                .reset_index()
            )
            comparison_data.columns = ["Osoba", "Łączny czas", "Czas twórczy"]

            fig_comparison = go.Figure()
            fig_comparison.add_trace(
                go.Bar(
                    name="Łączny czas",
                    x=comparison_data["Osoba"],
                    y=comparison_data["Łączny czas"],
                    marker_color="lightblue",
                )
            )
            fig_comparison.add_trace(
                go.Bar(
                    name="Czas twórczy",
                    x=comparison_data["Osoba"],
                    y=comparison_data["Czas twórczy"],
                    marker_color="darkblue",
                )
            )
            fig_comparison.update_layout(
                barmode="group",
                height=400,
                yaxis_title="Godziny",
                xaxis_title="Osoba",
            )
            st.plotly_chart(fig_comparison, width="stretch")


def render_export_section(df_filtered: pd.DataFrame, creative_summary: pd.DataFrame):
    """Renderuje sekcję eksportu danych."""
    st.markdown("## 📥 Eksport danych")

    col1, col2 = st.columns(2)

    # Przygotuj kolumny do eksportu
    export_columns = [
        "person",
        "task",
        "key",
        "time_hours",
        "creative_percent",
        "creative_hours",
    ]
    export_names = [
        "Osoba",
        "Zadanie",
        "Klucz",
        "Czas (h)",
        "Procent twórczości",
        "Godziny twórcze",
    ]

    with col1:
        csv_data, csv_filename = export_to_csv(
            df_filtered, export_columns, export_names
        )
        st.download_button(
            label="📋 Pobierz CSV",
            data=csv_data,
            file_name=csv_filename,
            mime="text/csv",
            width="stretch",
        )

    with col2:
        excel_buffer, excel_filename = export_to_excel(df_filtered, creative_summary)
        st.download_button(
            label="📊 Pobierz Excel (2 arkusze)",
            data=excel_buffer,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )


def render_worklogs_section(df_worklogs_by_month: dict, months_available: list):
    """Renderuje sekcję analizy worklogs."""
    st.markdown("## 📋 Analizy per Miesiąc (Worklogs)")

    selected_month = st.selectbox(
        "Wybierz miesiąc:",
        months_available,
        help="Analiza pełna miesiąca lub okresu",
    )

    if selected_month not in df_worklogs_by_month:
        return

    month_data = df_worklogs_by_month[selected_month]

    # Agreguj dla statystyk (każde zadanie per osoba pojawia się raz)
    month_data_agg = aggregate_worklogs_to_report(month_data)

    # Oblicz range dat
    start_date = month_data["Start Date"].min()
    end_date = month_data["Start Date"].max()

    # Sprawdź kompletność miesiąca
    month_obj = pd.to_datetime(selected_month + "-01")
    first_day = month_obj.replace(day=1)
    last_day = (month_obj + pd.DateOffset(months=1)).replace(day=1) - pd.Timedelta(
        days=1
    )

    is_complete = (
        start_date.date() <= first_day.date() and end_date.date() >= last_day.date()
    )
    status = "✅ Pełny miesiąc" if is_complete else "⚠️ Część miesiąca"

    # Nagłówek
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.write(
            f"**Okres:** {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
        )
    with col2:
        st.write(f"**Status:** {status}")
    with col3:
        st.write(f"**Dni:** {(end_date - start_date).days + 1}")

    # Statystyki
    with st.expander("📈 Statystyki miesiąca", expanded=True):
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)

        total_hours = month_data_agg["time_hours"].sum()
        working_days = month_data["Start Date"].dt.date.nunique()
        creative_hours = month_data_agg["creative_hours"].sum()
        total_tasks = len(month_data_agg)
        tasks_with_data = month_data_agg["creative_percent"].notna().sum()
        data_coverage = (tasks_with_data / total_tasks * 100) if total_tasks > 0 else 0
        avg_task_hours = total_hours / total_tasks if total_tasks > 0 else 0
        creative_hours_ratio = (
            creative_hours / total_hours * 100 if total_hours > 0 else 0
        )
        top3_hours = (
            month_data_agg.nlargest(3, "time_hours")["time_hours"].sum()
            if total_tasks > 0
            else 0
        )
        focus_index = top3_hours / total_hours * 100 if total_hours > 0 else 0

        with stat_col1:
            st.metric("⏰ Łączne godziny", f"{total_hours:.1f}h")

        with stat_col2:
            avg_per_day = total_hours / working_days if working_days > 0 else 0
            st.metric(
                "📅 Średnio/dzień", f"{avg_per_day:.1f}h", delta=f"{working_days} dni"
            )

        with stat_col3:
            avg_creative_pct = (
                (creative_hours / total_hours * 100) if total_hours > 0 else 0
            )
            st.metric("🎨 Średni %", f"{avg_creative_pct:.0f}%")

        with stat_col4:
            st.metric("👥 Osób", month_data_agg["person"].nunique())

        extra_col1, extra_col2, extra_col3, extra_col4 = st.columns(4)

        with extra_col1:
            st.metric("📊 Pokrycie danymi", f"{data_coverage:.0f}%")

        with extra_col2:
            st.metric("🎯 Fokus Top3 (udział)", f"{focus_index:.0f}%")

        with extra_col3:
            st.metric("⏱️ Średnia h/zadanie", f"{avg_task_hours:.1f}h")

        with extra_col4:
            st.metric("💠 Udział godzin twórczych", f"{creative_hours_ratio:.0f}%")

    # Executive Summary dla miesiąca (bez AI — analiza AI tylko na głównym Dashboard)
    st.markdown("---")
    render_executive_summary(month_data_agg, show_ai=False)
    st.markdown("---")

    # Timeline
    st.markdown("### 📊 Timeline")
    timeline_data = month_data.copy()
    timeline_data["date"] = timeline_data["Start Date"].dt.date
    daily_person = (
        timeline_data.groupby(["date", "person"])["time_hours"].sum().reset_index()
    )
    daily_person = daily_person.sort_values("date")

    fig_timeline = px.bar(
        daily_person,
        x="date",
        y="time_hours",
        color="person",
        title=f"Rozkład godzin - {selected_month}",
        labels={"time_hours": "Godziny", "date": "Data", "person": "Osoba"},
        barmode="stack",
    )
    fig_timeline.update_layout(height=400, hovermode="x unified")
    st.plotly_chart(fig_timeline, width="stretch")

    # Top zadania per osoba
    st.markdown("### 🎯 Top zadanie per osoba")
    top_tasks_month = get_top_task_per_person(month_data_agg)

    if not top_tasks_month.empty:
        display_df = format_display_table(top_tasks_month)
        display_df["status"] = display_df.get("has_creative_data", True).apply(
            lambda x: "✨ Twórcze" if x else "⏰ Najdłuższe"
        )

        st.dataframe(
            display_df[
                [
                    "person",
                    "task",
                    "key",
                    "time_hours",
                    "creative_percent",
                    "creative_hours",
                    "score",
                    "status",
                ]
            ].rename(
                columns={
                    "person": "👤 Osoba",
                    "task": "📋 Zadanie",
                    "key": "🔑 Klucz",
                    "time_hours": "⏰ Czas",
                    "creative_percent": "🎨 %",
                    "creative_hours": "✨ Godz.",
                    "score": "🏆 Score",
                    "status": "📊 Typ",
                }
            ),
            hide_index=True,
            width="stretch",
        )

    # Rozkład po dniach tygodnia
    st.markdown("### 📅 Rozkład tygodniowy")
    timeline_data["day_name"] = timeline_data["Start Date"].dt.day_name()

    daily_weekday = timeline_data.groupby("day_name")["time_hours"].agg(["sum", "mean"])
    daily_weekday = daily_weekday.reindex(
        [d for d in DAY_ORDER if d in daily_weekday.index]
    )
    daily_weekday.index = [DAY_NAMES_PL[d] for d in daily_weekday.index]

    col1, col2 = st.columns(2)

    with col1:
        fig_day_total = px.bar(
            x=daily_weekday.index,
            y=daily_weekday["sum"],
            title="Łączne godziny per dzień",
            labels={"x": "Dzień", "y": "Godziny"},
        )
        fig_day_total.update_layout(height=350)
        st.plotly_chart(fig_day_total, width="stretch")

    with col2:
        fig_day_avg = px.bar(
            x=daily_weekday.index,
            y=daily_weekday["mean"],
            title="Średnio godzin per dzień",
            labels={"x": "Dzień", "y": "Średnia"},
            color_discrete_sequence=["#2ca02c"],
        )
        fig_day_avg.update_layout(height=350)
        st.plotly_chart(fig_day_avg, width="stretch")

    # Wykresy analityczne
    st.markdown("---")
    with st.expander("📊 Wykresy analityczne", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Czas pracy na osobę**")
            person_hours = (
                month_data.groupby("person")["time_hours"]
                .sum()
                .sort_values(ascending=True)
            )

            fig1 = px.bar(
                x=person_hours.values,
                y=person_hours.index,
                orientation="h",
                title="Łączne godziny pracy",
                labels={"x": "Godziny", "y": "Osoba"},
            )
            fig1.update_layout(height=400)
            st.plotly_chart(fig1, width="stretch")

        with col2:
            st.markdown("**Rozkład pracy twórczej**")
            creative_data = month_data.dropna(subset=["creative_percent"])
            if not creative_data.empty:

                def categorize_creative(pct):
                    if pct == 0:
                        return "0%"
                    elif pct <= 20:
                        return "1-20%"
                    elif pct <= 40:
                        return "21-40%"
                    elif pct <= 60:
                        return "41-60%"
                    elif pct <= 80:
                        return "61-80%"
                    else:
                        return "81-100%"

                creative_data_copy = creative_data.copy()
                creative_data_copy["category"] = creative_data_copy[
                    "creative_percent"
                ].apply(categorize_creative)
                creative_counts = creative_data_copy["category"].value_counts()

                category_order = [
                    "0%",
                    "1-20%",
                    "21-40%",
                    "41-60%",
                    "61-80%",
                    "81-100%",
                ]
                creative_counts = creative_counts.reindex(
                    [c for c in category_order if c in creative_counts.index]
                )

                fig2 = px.pie(
                    values=creative_counts.values,
                    names=creative_counts.index,
                    title="Zadania według poziomu twórczości",
                )
                fig2.update_traces(textposition="inside", textinfo="percent+label")
                fig2.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig2, width="stretch")
            else:
                st.info("Brak danych o pracy twórczej.")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Godziny twórcze per osoba i poziom**")
            creative_data = month_data.dropna(subset=["creative_percent"])
            if not creative_data.empty and len(creative_data) > 0:

                def categorize_creative(pct):
                    if pct <= 20:
                        return "0-20%"
                    elif pct <= 40:
                        return "21-40%"
                    elif pct <= 60:
                        return "41-60%"
                    elif pct <= 80:
                        return "61-80%"
                    else:
                        return "81-100%"

                creative_data_copy = creative_data.copy()
                creative_data_copy["category"] = creative_data_copy[
                    "creative_percent"
                ].apply(categorize_creative)

                heatmap_data = (
                    creative_data_copy.groupby(["person", "category"])["creative_hours"]
                    .sum()
                    .reset_index()
                )

                category_order = ["0-20%", "21-40%", "41-60%", "61-80%", "81-100%"]

                heatmap_pivot = heatmap_data.pivot(
                    index="person", columns="category", values="creative_hours"
                ).fillna(0)

                heatmap_pivot = heatmap_pivot.reindex(
                    columns=[c for c in category_order if c in heatmap_pivot.columns]
                )

                fig_heatmap = px.imshow(
                    heatmap_pivot,
                    labels=dict(
                        x="Poziom twórczości", y="Osoba", color="Godz. twórcze"
                    ),
                    x=heatmap_pivot.columns,
                    y=heatmap_pivot.index,
                    color_continuous_scale="Plasma",
                    aspect="auto",
                )
                fig_heatmap.update_layout(height=400)
                st.plotly_chart(fig_heatmap, width="stretch")
            else:
                st.info("Brak danych do heatmapy")

        with col2:
            st.markdown("**Czas pracy vs Czas twórczy**")
            comparison_data = (
                month_data.groupby("person")
                .agg({"time_hours": "sum", "creative_hours": "sum"})
                .reset_index()
            )
            comparison_data.columns = ["Osoba", "Łączny czas", "Czas twórczy"]

            fig_comparison = go.Figure()
            fig_comparison.add_trace(
                go.Bar(
                    name="Łączny czas",
                    x=comparison_data["Osoba"],
                    y=comparison_data["Łączny czas"],
                    marker_color="lightblue",
                )
            )
            fig_comparison.add_trace(
                go.Bar(
                    name="Czas twórczy",
                    x=comparison_data["Osoba"],
                    y=comparison_data["Czas twórczy"],
                    marker_color="darkblue",
                )
            )
            fig_comparison.update_layout(
                barmode="group",
                height=400,
                yaxis_title="Godziny",
                xaxis_title="Osoba",
            )
            st.plotly_chart(fig_comparison, width="stretch")

    # Eksport worklogs
    st.markdown("### 📥 Eksport miesiąca")
    col1, col2 = st.columns(2)

    with col1:
        csv_data, csv_filename = export_worklogs_to_csv(
            month_data, selected_month, start_date, end_date
        )
        st.download_button(
            label=f"📋 CSV - {selected_month}",
            data=csv_data,
            file_name=csv_filename,
            mime="text/csv",
        )

    with col2:
        excel_buffer, excel_filename = export_worklogs_to_excel(
            month_data, selected_month, start_date, end_date
        )
        st.download_button(
            label=f"📊 Excel - {selected_month}",
            data=excel_buffer,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def render_personal_dashboard(df: pd.DataFrame):
    """Renderuje Personal Dashboard dla wybranego użytkownika."""
    st.markdown("##  👤 Personal Dashboard")

    # Debug - pokaż ile użytkowników dostępnych
    if df.empty:
        st.error("❌ Brak danych do wyświetlenia!")
        return

    # Sprawdź czy dane mają month_str (z worklogs)
    has_months = "month_str" in df.columns

    # Filtry góra
    col_person, col_month = st.columns([2, 1])

    with col_person:
        people_list = sorted(df["person"].unique())

        if not people_list:
            st.info("Brak danych użytkowników")
            return

        st.caption(f"👥 Dostępni użytkownicy: {len(people_list)}")
        selected_person = st.selectbox(
            "👤 Wybierz użytkownika",
            options=people_list,
            key="personal_dashboard_person_selector",
        )

    with col_month:
        if has_months:
            months_available = sorted(df["month_str"].dropna().unique(), reverse=True)
            selected_month = st.selectbox(
                "📅 Okres",
                options=["Wszystkie"] + months_available,
                key="personal_dashboard_month_selector",
            )
        else:
            st.info("💡 Brak podziału na miesiące")
            selected_month = "Wszystkie"

    if not selected_person:
        return

    # Filtruj dane
    df_filtered = df[df["person"] == selected_person].copy()
    if has_months and selected_month != "Wszystkie":
        df_filtered = df_filtered[df_filtered["month_str"] == selected_month]

    # Generuj statystyki
    stats = generate_personal_stats(df_filtered, selected_person)

    # Info o okresie
    if selected_month == "Wszystkie":
        if has_months:
            st.warning(
                "⚠️ **Uwaga:** Statystyki i koszty dotyczą CAŁEGO okresu danych (wszystkie miesiące razem), nie jednego miesiąca!"
            )
        else:
            st.info("ℹ️ Statystyki dotyczą całego okresu danych w pliku.")
    else:
        st.success(f"✅ Statystyki dla miesiąca: **{selected_month}**")

    st.markdown(f"### 📊 Statystyki dla: **{selected_person}**")
    st.markdown("---")

    # METRYKI GŁÓWNE
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(label="📅 Liczba zadań", value=stats["num_tasks"])

    with col2:
        st.metric(label="⏰ Łączne godziny", value=f"{stats['total_hours']:.1f}h")

    with col3:
        st.metric(label="✨ Godziny twórcze", value=f"{stats['creative_hours']:.1f}h")

    with col4:
        if stats["creative_percent_avg"] is not None:
            st.metric(
                label="🎨 Średnia twórczość",
                value=f"{stats['creative_percent_avg']:.0f}%",
            )
        else:
            st.metric(label="🎨 Średnia twórczość", value="—")

    st.markdown("---")

    # JAKOŚĆ DANYCH I FOKUS
    st.markdown("### 📌 Jakość danych i fokus")
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

    with kpi_col1:
        st.metric(label="⏱️ Średnia h/zadanie", value=f"{stats['avg_task_hours']:.1f}h")

    with kpi_col2:
        st.metric(label="📊 Pokrycie danymi", value=f"{stats['data_coverage']:.0f}%")

    with kpi_col3:
        if stats["creative_percent_std"] is not None:
            st.metric(
                label="📉 Odchylenie % twórczości",
                value=f"{stats['creative_percent_std']:.1f}%",
            )
        else:
            st.metric(label="📉 Odchylenie % twórczości", value="—")

    with kpi_col4:
        st.metric(label="🎯 Fokus Top3 (udział)", value=f"{stats['focus_index']:.0f}%")

    st.markdown("---")

    # CREATIVE SCORE
    st.markdown("### 🏆 Creative Score")
    st.metric(
        label="Creative Score (suma wszystkich zadań)",
        value=f"{stats['creative_score']:.1f}",
        help="Suma (creative_hours × creative_% / 100) ze wszystkich zadań",
    )

    st.markdown("---")

    # PERSONALIZOWANY INSIGHT
    insight = generate_personalized_insight(
        stats["categories_breakdown"],
        stats["total_hours"],
        stats["creative_percent_avg"],
    )
    st.info(insight)

    st.markdown("---")

    with st.expander("💰 Kalkulator kosztów pracy (opcjonalne)", expanded=False):
        col_salary, col_hours = st.columns(2)

        with col_salary:
            brutto_salary = st.number_input(
                "Wynagrodzenie brutto miesięczne (PLN)",
                min_value=0.0,
                value=10000.0,
                step=500.0,
                key=f"salary_{selected_person}",
            )

        with col_hours:
            monthly_hours = st.number_input(
                "Godzin roboczych miesięcznie",
                min_value=1,
                value=168,
                step=1,
                help="Standardowo: 168h (21 dni × 8h), opcjonalnie: 160h lub 176h",
                key=f"hours_{selected_person}",
            )

        if brutto_salary > 0 and monthly_hours > 0:
            hourly_rate = brutto_salary / monthly_hours
            st.info(f"💵 **Koszt godzinowy:** {hourly_rate:.2f} PLN/h (brutto)")

            # Oblicz koszty
            # Jeśli wybrano konkretny miesiąc - koszt = pełne wynagrodzenie miesięczne
            # Jeśli "Wszystkie" - koszt = godziny * stawka
            if selected_month != "Wszystkie":
                total_cost = brutto_salary
                # Creative cost proporcjonalnie
                creative_cost = (
                    (stats["creative_hours"] / stats["total_hours"] * brutto_salary)
                    if stats["total_hours"] > 0
                    else 0
                )
            else:
                total_cost = stats["total_hours"] * hourly_rate
                creative_cost = stats["creative_hours"] * hourly_rate

            # Analiza najwartościowszych i najmniej wartościowych zadań
            most_valuable_task = None
            least_valuable_task = None

            if not df_filtered.empty and stats["total_hours"] > 0:
                tasks_with_value = df_filtered.copy()

                # Oblicz koszt dla każdego zadania
                if selected_month != "Wszystkie":
                    tasks_with_value["task_cost"] = (
                        tasks_with_value["time_hours"] / stats["total_hours"]
                    ) * brutto_salary
                else:
                    tasks_with_value["task_cost"] = (
                        tasks_with_value["time_hours"] * hourly_rate
                    )

                # Oblicz creative score (wartość twórcza)
                tasks_with_value["task_score"] = (
                    tasks_with_value["creative_hours"]
                    * tasks_with_value["creative_percent"]
                    / 100
                )

                # Filtruj zadania z danymi o twórczości (creative_percent > 0)
                valuable_tasks = tasks_with_value[
                    (tasks_with_value["creative_percent"].notna())
                    & (tasks_with_value["creative_percent"] > 0)
                ].copy()

                # Jeśli brak zadań z twórczością, szukaj w zadaniach z czasem > 0
                if valuable_tasks.empty:
                    valuable_tasks = tasks_with_value[
                        tasks_with_value["time_hours"] > 0
                    ].copy()
                    use_score = False
                else:
                    use_score = True

                if not valuable_tasks.empty:
                    # Zaawansowane metryki biznesowe

                    # Value Density = creative_score / cost (wartość twórcza per PLN)
                    valuable_tasks["value_density"] = valuable_tasks.apply(
                        lambda row: (
                            row["task_score"] / row["task_cost"]
                            if row["task_cost"] > 0
                            else 0
                        ),
                        axis=1,
                    )

                    # Business Impact = creative_score × creative_percent/100 (całkowita wartość biznesowa)
                    valuable_tasks["business_impact"] = (
                        valuable_tasks["task_score"]
                        * valuable_tasks["creative_percent"]
                        / 100
                    )

                    # Non-creative Cost = cost × (1 - creative_percent/100)
                    valuable_tasks["non_creative_cost"] = valuable_tasks[
                        "task_cost"
                    ] * (1 - valuable_tasks["creative_percent"] / 100)

                    # Opportunity Loss = hours × (1 - creative_percent/100)
                    valuable_tasks["opportunity_loss"] = valuable_tasks[
                        "time_hours"
                    ] * (1 - valuable_tasks["creative_percent"] / 100)

                    # Najwartościowsze = najwyższy Business Impact (największa wartość biznesowa)
                    most_valuable_idx = valuable_tasks["business_impact"].idxmax()
                    most_valuable_task = {
                        "task": valuable_tasks.loc[most_valuable_idx, "task"],
                        "key": valuable_tasks.loc[most_valuable_idx, "key"]
                        if "key" in valuable_tasks.columns
                        else "—",
                        "hours": valuable_tasks.loc[most_valuable_idx, "time_hours"],
                        "creative_percent": valuable_tasks.loc[
                            most_valuable_idx, "creative_percent"
                        ],
                        "cost": valuable_tasks.loc[most_valuable_idx, "task_cost"],
                        "score": valuable_tasks.loc[most_valuable_idx, "task_score"],
                        "business_impact": valuable_tasks.loc[
                            most_valuable_idx, "business_impact"
                        ],
                        "value_density": valuable_tasks.loc[
                            most_valuable_idx, "value_density"
                        ],
                        "creative_cost": (
                            valuable_tasks.loc[most_valuable_idx, "task_cost"]
                            * valuable_tasks.loc[most_valuable_idx, "creative_percent"]
                            / 100
                        ),
                    }

                    # Najmniej wartościowe = najwyższy Non-creative Cost (największy drain budżetu na nietwórcze)
                    least_valuable_idx = valuable_tasks["non_creative_cost"].idxmax()

                    least_valuable_task = {
                        "task": valuable_tasks.loc[least_valuable_idx, "task"],
                        "key": valuable_tasks.loc[least_valuable_idx, "key"]
                        if "key" in valuable_tasks.columns
                        else "—",
                        "hours": valuable_tasks.loc[least_valuable_idx, "time_hours"],
                        "creative_percent": valuable_tasks.loc[
                            least_valuable_idx, "creative_percent"
                        ]
                        if "creative_percent" in valuable_tasks.columns
                        else 0,
                        "cost": valuable_tasks.loc[least_valuable_idx, "task_cost"],
                        "score": valuable_tasks.loc[least_valuable_idx, "task_score"]
                        if use_score
                        else 0,
                        "non_creative_cost": valuable_tasks.loc[
                            least_valuable_idx, "non_creative_cost"
                        ],
                        "opportunity_loss": valuable_tasks.loc[
                            least_valuable_idx, "opportunity_loss"
                        ],
                        "creative_cost": (
                            valuable_tasks.loc[least_valuable_idx, "task_cost"]
                            * valuable_tasks.loc[least_valuable_idx, "creative_percent"]
                            / 100
                        ),
                    }

            # Info o okresie
            if selected_month == "Wszystkie":
                st.caption(
                    f"⚠️ Wynagrodzenie ({brutto_salary:,.0f} PLN) to stawka **miesięczna**, "
                    f"ale statystyki poniżej dotyczą **całego okresu** ({stats['total_hours']:.1f}h z wielu miesięcy). "
                    f"Wybierz konkretny miesiąc z listy powyżej, żeby zobaczyć koszty miesięczne."
                )
            else:
                st.caption(
                    f"✅ Koszt dla miesiąca **{selected_month}**: pełne wynagrodzenie miesięczne ({brutto_salary:,.0f} PLN). "
                    f"Przepracowano {stats['total_hours']:.1f}h z norm {monthly_hours}h, "
                    f"w tym {stats['creative_hours']:.1f}h twórczych."
                )

            col_cost1, col_cost2 = st.columns(2)

            with col_cost1:
                if selected_month == "Wszystkie":
                    help_text = (
                        f"Obliczony dla {stats['total_hours']:.1f}h z wybranego okresu"
                    )
                else:
                    help_text = f"Pełne wynagrodzenie miesięczne za {selected_month}"
                st.metric(
                    label="💸 Koszt całkowity czasu pracy",
                    value=f"{total_cost:,.2f} PLN",
                    help=help_text,
                )

            with col_cost2:
                if selected_month == "Wszystkie":
                    help_text = (
                        f"Koszt {stats['creative_hours']:.1f}h faktycznie twórczych"
                    )
                else:
                    help_text = (
                        f"{stats['creative_hours']:.1f}h twórczych / {stats['total_hours']:.1f}h łącznie = {stats['creative_hours'] / stats['total_hours'] * 100:.0f}% wynagrodzenia"
                        if stats["total_hours"] > 0
                        else "Brak godzin"
                    )
                st.metric(
                    label="💎 Wartość pracy twórczej",
                    value=f"{creative_cost:,.2f} PLN",
                    help=help_text,
                )

            # Dodatkowe KPI kosztowe
            extra_cost_col1, extra_cost_col2 = st.columns(2)
            non_creative_cost_total = total_cost - creative_cost
            cost_per_creative_hour = (
                creative_cost / stats["creative_hours"]
                if stats["creative_hours"] > 0
                else 0
            )
            waste_ratio = (
                non_creative_cost_total / total_cost * 100 if total_cost > 0 else 0
            )

            with extra_cost_col1:
                st.metric(
                    label="💸 Koszt 1h twórczej",
                    value=f"{cost_per_creative_hour:,.2f} PLN/h",
                )

            with extra_cost_col2:
                st.metric(
                    label="🧯 Udział nietwórczy (koszt)", value=f"{waste_ratio:.0f}%"
                )

            st.markdown("---")

            # Najbardziej i najmniej wartościowe zadanie
            if most_valuable_task or least_valuable_task:
                st.markdown("### 🎯 Zaawansowana analiza wartości zadań")

                col_exp, col_cheap = st.columns(2)

                with col_exp:
                    if most_valuable_task:
                        st.markdown("#### 💎 Najwyższa wartość biznesowa")
                        st.markdown(f"**{most_valuable_task['task']}**")

                        # Extrahuj key z tytułu jeśli tam jest (format "XXX-123: ...")
                        task_title = most_valuable_task["task"]
                        if ":" in task_title:
                            extracted_key = task_title.split(":")[0].strip()
                        else:
                            extracted_key = most_valuable_task["key"]
                        st.caption(f"🔑 {extracted_key}")

                        # Górny rząd metryk
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            st.metric(
                                label="Business Impact",
                                value=f"{most_valuable_task['business_impact']:.2f}",
                                help="creative_score × (creative_percent/100)",
                            )
                        with col_m2:
                            st.metric(
                                label="Value Density",
                                value=f"{most_valuable_task['value_density']:.3f}",
                                help="creative value per PLN spent",
                            )

                        # Środkowy rząd metryk
                        col_m3, col_m4 = st.columns(2)
                        with col_m3:
                            st.metric(
                                label="Creative Score",
                                value=f"{most_valuable_task['score']:.2f}",
                            )
                        with col_m4:
                            st.metric(
                                label="Koszt twórczej pracy",
                                value=f"{most_valuable_task['creative_cost']:,.0f} PLN",
                            )

                        st.caption(
                            f"⏱️ Czas: {most_valuable_task['hours']:.1f}h | "
                            f"🎨 Twórczość: {most_valuable_task['creative_percent']:.0f}% | "
                            f"💸 Koszt całkowity: {most_valuable_task['cost']:,.0f} PLN"
                        )

                with col_cheap:
                    if least_valuable_task:
                        st.markdown("#### ⚠️ Największy drain budżetu")
                        st.markdown(f"**{least_valuable_task['task']}**")

                        # Extrahuj key z tytułu jeśli tam jest
                        task_title = least_valuable_task["task"]
                        if ":" in task_title:
                            extracted_key = task_title.split(":")[0].strip()
                        else:
                            extracted_key = least_valuable_task["key"]
                        st.caption(f"🔑 {extracted_key}")

                        # Górny rząd metryk
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            st.metric(
                                label="Koszt bez wartości",
                                value=f"{least_valuable_task['non_creative_cost']:,.0f} PLN",
                                help="cost × (1 - creative_percent/100)",
                            )
                        with col_m2:
                            st.metric(
                                label="Zmarnowane godziny",
                                value=f"{least_valuable_task['opportunity_loss']:.1f}h",
                                help="hours × (1 - creative_percent/100)",
                            )

                        # Środkowy rząd metryk
                        col_m3, col_m4 = st.columns(2)
                        with col_m3:
                            if least_valuable_task["creative_cost"] > 0:
                                st.metric(
                                    label="Koszt pracy twórczej",
                                    value=f"{least_valuable_task['creative_cost']:,.0f} PLN",
                                )
                            else:
                                st.metric(label="Koszt pracy twórczej", value="0 PLN")
                        with col_m4:
                            st.metric(
                                label="Split kosztów",
                                value=f"{(1 - least_valuable_task['creative_percent'] / 100) * 100:.0f}% drain",
                            )

                        st.caption(
                            f"⏱️ Czas: {least_valuable_task['hours']:.1f}h | "
                            f"🎨 Twórczość: {least_valuable_task['creative_percent']:.0f}% | "
                            f"💸 Koszt całkowity: {least_valuable_task['cost']:,.0f} PLN"
                        )

            st.markdown("---")

            # Koszty per kategoria
            if stats["categories_breakdown"]:
                st.markdown("### 📋 Koszty per kategoria zadań")

                categories_cost_data = []
                for cat, data in stats["categories_breakdown"].items():
                    if selected_month != "Wszystkie":
                        # Dla konkretnego miesiąca - proporcjonalnie do udziału godzin
                        cat_cost = (
                            (data["hours"] / stats["total_hours"] * brutto_salary)
                            if stats["total_hours"] > 0
                            else 0
                        )
                        creative_cat_cost = (
                            (
                                data["creative_hours"]
                                / stats["total_hours"]
                                * brutto_salary
                            )
                            if stats["total_hours"] > 0
                            else 0
                        )
                    else:
                        # Dla wszystkich miesięcy - godziny * stawka
                        cat_cost = data["hours"] * hourly_rate
                        creative_cat_cost = data["creative_hours"] * hourly_rate

                    categories_cost_data.append(
                        {
                            "Kategoria": cat,
                            "Liczba zadań": data["count"],
                            "Godziny": data["hours"],
                            "Koszt [PLN]": cat_cost,
                            "Godz. twórcze": data["creative_hours"],
                            "Wartość twórcza [PLN]": creative_cat_cost,
                        }
                    )

                if categories_cost_data:
                    cost_df = pd.DataFrame(categories_cost_data)
                    cost_df = cost_df.sort_values("Koszt [PLN]", ascending=False)

                    # Formatuj
                    cost_df_display = cost_df.copy()
                    cost_df_display["Godziny"] = cost_df_display["Godziny"].apply(
                        lambda x: f"{x:.1f}h"
                    )
                    cost_df_display["Koszt [PLN]"] = cost_df_display[
                        "Koszt [PLN]"
                    ].apply(lambda x: f"{x:,.2f}")
                    cost_df_display["Godz. twórcze"] = cost_df_display[
                        "Godz. twórcze"
                    ].apply(lambda x: f"{x:.1f}h")
                    cost_df_display["Wartość twórcza [PLN]"] = cost_df_display[
                        "Wartość twórcza [PLN]"
                    ].apply(lambda x: f"{x:,.2f}")

                    st.dataframe(cost_df_display, width="stretch", hide_index=True)

                    if selected_month != "Wszystkie":
                        st.caption(
                            f"✅ Koszty per kategoria obliczone proporcjonalnie do udziału godzin. "
                            f"Suma kosztów wszystkich kategorii = {brutto_salary:,.0f} PLN (pełne wynagrodzenie miesięczne)."
                        )
                    else:
                        st.caption(
                            "⚠️ Koszty obliczone jako (godziny × stawka godzinowa) dla całego okresu. "
                            "Wybierz konkretny miesiąc powyżej, żeby zobaczyć podział wynagrodzenia miesięcznego."
                        )

                    # Wykres kosztów
                    fig_cost = px.bar(
                        cost_df,
                        x="Koszt [PLN]",
                        y="Kategoria",
                        orientation="h",
                        title="Koszt pracy per kategoria",
                        labels={"Koszt [PLN]": "Koszt (PLN)", "Kategoria": ""},
                        color="Koszt [PLN]",
                        color_continuous_scale="Plasma",
                    )
                    fig_cost.update_layout(height=400)
                    st.plotly_chart(fig_cost, width="stretch")

        st.markdown("---")

    # TOP ZADANIA
    if stats["top_tasks_df"] is not None and not stats["top_tasks_df"].empty:
        st.markdown("### 🎯 Top 10 zadań (według Creative Score)")

        top_tasks_display = stats["top_tasks_df"].copy()
        top_tasks_display["time_hours"] = top_tasks_display["time_hours"].apply(
            lambda x: f"{x:.1f}h"
        )
        top_tasks_display["creative_percent"] = top_tasks_display[
            "creative_percent"
        ].apply(lambda x: f"{int(x)}%")
        top_tasks_display["creative_hours"] = top_tasks_display["creative_hours"].apply(
            lambda x: f"{x:.1f}h"
        )
        top_tasks_display["task_score"] = top_tasks_display["task_score"].apply(
            lambda x: f"{x:.2f}"
        )

        top_tasks_display.columns = [
            "📋 Zadanie",
            "🔑 Klucz",
            "⏰ Czas",
            "🎨 %",
            "✨ Godz. twórcze",
            "💎 Score",
        ]

        st.dataframe(top_tasks_display, width="stretch", hide_index=True)


def render_help_tab():
    """Renderuje zakładkę pomocy."""
    st.markdown("## ❓ Pomoc")

    st.markdown(
        """
    ### Jak korzystać z aplikacji

    1. **Wgraj plik główny** (struktura Level 0/1/2):
       - Level 0: Nazwisko użytkownika
       - Level 1: Zadanie + czas
       - Level 2: % pracy twórczej

    2. **Opcjonalnie wgraj worklogs** - dane z datami dla analizy trendu

    3. **Przeglądaj wyniki:**
       - Executive Summary - kluczowe insights
       - Ranking Creative Score - najlepsza kombinacja czasu i kreatywności
       - Szczegółowe dane - filtruj i szukaj

    ### Kalkulacje

    - **Godziny twórcze** = czas × (% twórczości / 100)
    - **Creative Score** = godz. twórcze × (% twórczości / 100)
      - Nagradza wysokie zaangażowanie + wysoką kreatywność

    ### Eksport

    - **CSV** - prosty format do dalszej analizy
    - **Excel** - 2 arkusze: szczegóły + podsumowanie per osoba
    """
    )

    st.markdown("### Przykładowa struktura danych")
    example_data = pd.DataFrame(
        {
            "Level": [0, 1, 2, 1, 2],
            "Users / Issues / Procent pracy twórczej": [
                "Jan Kowalski",
                "Implementacja modułu",
                "90",
                "Testowanie",
                "50",
            ],
            "Key": ["", "PROJ-123", "", "PROJ-124", ""],
            "Total Time Spent": ["", "10:00", "", "5:30", ""],
        }
    )
    st.dataframe(example_data, width="stretch")


# =============================================================================
# GŁÓWNA FUNKCJA
# =============================================================================


def main():
    st.title("📊 Raport Czasu Pracy i Pracy Twórczej")

    # Sidebar
    worklogs_file, uploaded_file, excluded_people, selected_month = render_sidebar()

    if worklogs_file is None:
        st.info("👈 Wgraj plik Worklogs w panelu bocznym aby rozpocząć analizę.")
        render_help_tab()
        return

    try:
        # ===================================================================
        # WORKLOGS - GŁÓWNE ŹRÓDŁO DANYCH
        # ===================================================================

        with st.spinner("📋 Wczytuję worklogs..."):
            df_worklogs_raw = pd.read_excel(worklogs_file, engine="openpyxl")
            df_worklogs_raw = apply_encoding_fix_to_dataframe(df_worklogs_raw)

        # Przetwórz worklogs
        with st.spinner("⚙️ Przetwarzam worklogs..."):
            df_worklogs = process_worklogs_data(df_worklogs_raw)

        if df_worklogs.empty:
            st.error("❌ Nie udało się załadować danych z worklogs.")
            return

        # Agreguj worklogs do postaci "raport główny" (bez dat)
        with st.spinner("📊 Agreguję dane..."):
            df_processed_full = aggregate_worklogs_to_report(df_worklogs)

        if df_processed_full.empty:
            st.error("❌ Nie udało się zagregować danych.")
            return

        st.session_state["all_people"] = sorted(
            df_processed_full["person"].unique().tolist()
        )

        st.success(
            f"✅ Załadowano {len(df_worklogs)} wpisów worklogs ({len(df_processed_full)} unikatowych zadań)"
        )

        # Filtruj wykluczone osoby TYLKO DLA DASHBOARDU (nie dla metryk)
        df_processed = df_processed_full[
            ~df_processed_full["person"].isin(excluded_people)
        ]

        # ===================================================================
        # OPCJONALNIE: PORÓWNANIE Z RAPORTEM GŁÓWNYM (TOTALS)
        # ===================================================================

        if uploaded_file is not None:
            with st.spinner("📂 Wczytuję raport Level 0/1/2 (opcjonalnie)..."):
                df_totals_raw = pd.read_excel(uploaded_file, engine="openpyxl")
                df_totals_raw = apply_encoding_fix_to_dataframe(df_totals_raw)

            # Sprawdź strukturę
            required_columns = ["Level", "Users / Issues / Procent pracy twórczej"]
            if all(col in df_totals_raw.columns for col in required_columns):
                df_totals_raw["Level"] = (
                    pd.to_numeric(df_totals_raw["Level"], errors="coerce")
                    .fillna(0)
                    .astype(int)
                )

                with st.spinner("⚙️ Przetwarzam raport..."):
                    df_totals = process_excel_data(df_totals_raw)

                if not df_totals.empty:
                    st.info(f"ℹ️ Raport Level 0/1/2 zawiera {len(df_totals)} zadań")
                    # Możemy tutaj dodać porównanie jeśli chcemy
            else:
                st.warning("⚠️ Raport nie ma wymaganej struktury Level 0/1/2")

        # ===================================================================
        # AGREGACJA PER MIESIĄC (Z WORKLOGS)
        # ===================================================================

        df_worklogs_by_month = {}
        months_available = []

        if not df_worklogs.empty:
            # Trzymaj surowe worklogi per miesiąc (NIE AGREGUJ)
            # Agregacja będzie robiona lokalnie tam gdzie jest potrzebna
            df_worklogs_by_month = {
                month: group.copy() for month, group in df_worklogs.groupby("month_str")
            }
            months_available = sorted(df_worklogs_by_month.keys(), reverse=True)
            st.session_state["months_available"] = months_available

        # Filtr miesiąca z sidebar (zastosowany na df_processed)
        if selected_month != "Wszystkie" and "month_str" in df_processed.columns:
            df_processed = df_processed[df_processed["month_str"] == selected_month]

        # METRYKI (zawsze widoczne) - zgodne z dashboardem
        render_metrics(
            df_processed, selected_month, excluded_count=len(excluded_people)
        )
        st.markdown("---")

        # TABS - porządek: Dashboard → Worklogs (jeśli dostępne) → Personal Dashboard → Pomoc
        if months_available:
            tabs = ["📊 Dashboard", "📋 Worklogs", "👤 Personal Dashboard", "❓ Pomoc"]
        else:
            tabs = ["📊 Dashboard", "👤 Personal Dashboard", "❓ Pomoc"]
        tab_objects = st.tabs(tabs)

        # TAB 0: DASHBOARD
        with tab_objects[0]:
            # Team Health + Anomalie (góra strony)
            col_health, col_alerts = st.columns([1, 2])
            with col_health:
                render_team_health(df_processed)
            with col_alerts:
                render_anomaly_alerts(df_processed)
            st.markdown("---")

            # Executive Summary
            render_executive_summary(df_processed, selected_month)
            st.markdown("---")

            # Ranking Creative Score
            render_top_tasks_table(df_processed)
            st.markdown("---")

            # Szczegółowe dane
            df_filtered, display_df = render_detailed_data(df_processed)

            # Wykresy
            render_charts(df_filtered)
            st.markdown("---")

            # Eksport (z pełnym datasetem, bez filtrów dashboard)
            creative_summary_full = calculate_creative_summary(df_processed_full)
            render_export_section(df_processed_full, creative_summary_full)

        # TAB 1: WORKLOGS (jeśli dostępne)
        if months_available:
            with tab_objects[1]:
                # Filtruj wykluczone osoby z worklogs per miesiąc
                df_worklogs_by_month_filtered = {
                    month: df[~df["person"].isin(excluded_people)].copy()
                    for month, df in df_worklogs_by_month.items()
                }
                render_worklogs_section(df_worklogs_by_month_filtered, months_available)

        # TAB 2 (lub 1): PERSONAL DASHBOARD
        personal_tab_index = 2 if months_available else 1
        with tab_objects[personal_tab_index]:
            # ZAWSZE używaj zagregowanych danych!
            # df_worklogs zawiera duplikaty (surowe worklogi)
            # Użyj df_processed_full które już mają zagregowane (person, key)
            df_for_personal = df_processed_full.copy()
            # Filtruj wykluczone osoby
            df_for_personal = df_for_personal[
                ~df_for_personal["person"].isin(excluded_people)
            ].copy()

            # Debug info
            if df_for_personal.empty:
                st.error("❌ Brak danych po filtracji!")
                st.info(f"Processed rows: {len(df_processed_full)}")

            render_personal_dashboard(df_for_personal)

        # TAB 3 (lub 2): POMOC
        help_tab_index = 3 if months_available else 2
        with tab_objects[help_tab_index]:
            render_help_tab()

    except Exception as e:
        st.error(f"❌ Błąd: {str(e)}")
        with st.expander("🐞 Szczegóły techniczne"):
            import traceback

            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
