"""
Raport Czasu Pracy i Pracy Twórczej - Streamlit Dashboard

Przetwarza raporty z Jiry (hierarchiczna struktura Level 0/1/2) i worklogs,
oblicza Creative Score oraz eksportuje dane.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from helpers import (
    parse_time_to_hours,
    hours_to_hm_format,
    extract_creative_percentage,
    fix_polish_encoding,
    apply_encoding_fix_to_dataframe,
    get_top_task_per_person,
    format_display_table,
    calculate_creative_summary,
    get_dynamic_creative_filter_options,
    validate_data_structure,
    generate_executive_summary,
    generate_personal_stats,
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
    TABLE_HEADERS_WITH_EMOJI,
    TABLE_HEADERS_PLAIN,
    DAY_NAMES_PL,
    DAY_ORDER,
    CHART_MIN_HEIGHT,
    CHART_ROW_HEIGHT,
)

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

    df_work["Start Date"] = pd.to_datetime(df_work["Start Date"], errors="coerce")
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
    """Agreguje worklogs do postaci raportu głównego (per person + key)."""
    # Group by PERSON + TASK - każda osoba ma osobny wpis dla każdego zadania
    def weighted_creative_percent(group: pd.DataFrame) -> float | None:
        valid = group.dropna(subset=["creative_percent", "time_hours"])
        if valid.empty:
            return None
        total_hours = valid["time_hours"].sum()
        if total_hours <= 0:
            return None
        weighted_sum = (valid["creative_percent"] * valid["time_hours"]).sum()
        return round(float(weighted_sum / total_hours), 1)

    df_agg = df_worklogs.groupby(["person", "key"], as_index=False).apply(
        lambda group: pd.Series(
            {
                "time_hours": group["time_hours"].sum(),
                "creative_hours": group["creative_hours"].sum(),
                "creative_percent": weighted_creative_percent(group),
            }
        ),
        include_groups=False,
    )

    # Dodaj task (nie ma go po groupby)
    task_mapping = df_worklogs.groupby("key")["task"].first()
    df_agg["task"] = df_agg["key"].map(task_mapping)

    # Reorder columns
    return df_agg[["person", "task", "key", "time_hours", "creative_percent", "creative_hours"]]


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

        st.subheader("� Worklogs (główne źródło)")
        worklogs_file = st.file_uploader(
            "Wgraj Worklogs (.xlsx)",
            type=["xlsx"],
            key="worklogs_file",
            help="Worklogs: Start Date, Issue Key, Time Spent, Procent pracy twórczej, Author",
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
        st.header("ℹ️ Informacje")
        st.markdown(
            """
        **Worklogs zawiera:**
        - Issue Key i Summary
        - Author (osoba)
        - Time Spent (czas pracy)
        - Start Date (data)
        - Procent pracy twórczej
        - Issue Type (Story, Bug, Task)
        - Issue Status (Gotowe, W toku)
        - Components (moduł)

        **Creative Score:**
        `godz_twórcze × (% / 100)`
        """
        )

    return worklogs_file, uploaded_file


def render_metrics(df: pd.DataFrame):
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


def render_executive_summary(df: pd.DataFrame):
    """Renderuje Executive Summary - kluczowe insights jako tabele."""
    summary = generate_executive_summary(df)

    st.markdown("## 📋 Executive Summary")

    col1, col2, col3 = st.columns(3)

    with col1:
        if summary["top_performer"]:
            st.metric(
                "🏆 Top Performer (Creative Score)",
                summary["top_performer"],
                delta=f"Score: {summary['top_performer_score']:.1f}",
            )
        else:
            st.metric("🏆 Top Performer", "—")

    with col2:
        st.metric(
            "📊 Pokrycie danymi",
            f"{summary['data_coverage']:.0f}%",
            delta=f"{summary['total_creative_hours']:.1f}h twórczych",
        )

    with col3:
        if summary["avg_creative_percent"]:
            st.metric(
                "🎨 Średni % (ważony godzinami)",
                f"{summary['avg_creative_percent']:.0f}%",
            )
        else:
            st.metric("🎨 Średni % (ważony godzinami)", "—")

    st.caption(
        "💡 **Wyjaśnienie % twórczości:** Metryka na górze jest ważona godzinami (osoby pracujące mniej nie zaniżają wyniku), "
        "tabela Produktywności pokazuje proste średnie per osoba. Różnice są normalne!"
    )

    # Dynamiczne insighty — struktura: top 3 kategorie + 2 najbardziej znaczące + 1-2 teamowe
    top3 = summary.get("insights_top3_cats", [])
    other_cats = summary.get("insights", [])
    team = summary.get("insights_team", [])

    has_any = top3 or other_cats or team
    if has_any:
        st.markdown("### Kluczowe obserwacje")

        def _severity(text: str) -> int:
            if "⛔" in text:
                return 4
            if "⚠️" in text or "📉" in text:
                return 3
            if "📋" in text:
                return 2
            return 1

        # Top 2 z kolejnych kategorii (poza top 3) — wg wagi
        secondary = sorted(other_cats, key=_severity, reverse=True)[:2]
        # Top 2 z insightów teamowych — wg wagi
        team_sel = sorted(team, key=_severity, reverse=True)[:2]

        visible = top3 + secondary + team_sel

        col_a, col_b = st.columns(2)
        for i, insight in enumerate(visible):
            with col_a if i % 2 == 0 else col_b:
                st.info(insight)

        # Expander z resztą
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
        use_container_width=True,
        hide_index=False,
    )
    st.caption(
        "**Jak liczymy % Pracy twórczej:** "
        "Godziny twórcze ÷ Łączne godziny (tylko dla zadań z przypisanym % twórczości)."
    )

    # EFEKTYWNOŚĆ
    if summary["efficiency_table"] is not None:
        st.markdown("### ⚡ Analiza efektywności")
        eff_df = summary["efficiency_table"].copy()

        # Formatowanie
        eff_df["Średni % twórczości"] = eff_df["Średni % twórczości"].apply(
            lambda x: f"{x:.0f}%" if pd.notna(x) else "—"
        )

        st.dataframe(eff_df, use_container_width=True, hide_index=False)
        st.caption(
            "**Jak liczymy:**\n"
            "- Średni % twórczości: Zwykła średnia arytmetyczna % dla wszystkich zadań w danej kategorii\n"
            "(np. dla 'Długie zadania': bierzemy wszystkie taski ≥10h i liczymy ich średni % twórczości)"
        )

    # WSPÓŁPRACA
    if summary["collaboration_table"] is not None:
        st.markdown("### 🤝 Współpraca w zespole")
        collab_df = summary["collaboration_table"].copy()

        st.dataframe(collab_df, use_container_width=True, hide_index=True)
        st.caption("Najczęstsze pary współpracujące nad wspólnymi zadaniami")

    # DODATKOWE STATYSTYKI
    with st.expander("📊 Dodatkowe statystyki", expanded=True):
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

            st.dataframe(prod_df, use_container_width=True, hide_index=False)
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
    st.caption(
        "**Ranking osób według Total Score** (suma score'ów ze wszystkich zadań osoby) — "
        "spójny z Top Performer i Produktywnością zespołu. "
        "Tabela pokazuje najlepsze pojedyncze zadanie każdej osoby."
    )

    top_tasks_df = get_top_task_per_person(df)

    if top_tasks_df.empty:
        st.info("Brak danych do wyświetlenia")
        return

    # Formatuj do wyświetlenia
    display_df = format_display_table(top_tasks_df)

    display_cols = [
        "person",
        "total_score",
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
        "🏆 Total Score",
        "📋 Najlepsze zadanie",
        "🔑 Klucz",
        "⏰ Czas",
        "🎨 %",
        "✨ Godz. twórcze",
        "💎 Score zadania",
        "📊 Typ",
    ]

    st.dataframe(
        display_df[display_cols].rename(columns=dict(zip(display_cols, display_names))).reset_index(drop=True),
        hide_index=True,
        use_container_width=True,
    )
    
    st.caption(
        "**Jak czytać tabelę:**\n\n"
        "- **Total Score** = suma score'ów ze wszystkich zadań osoby (używana do rankingu) — identyczna wartość jak w Top Performer\n"
        "- **Score zadania** = creative_hours × creative_% / 100 dla tego konkretnego zadania\n"
        "- Tabela pokazuje najlepsze pojedyncze zadanie każdej osoby, ale ranking jest według Total Score"
    )

    # Wykres - zachowaj kolejność rankingu
    fig = px.bar(
        top_tasks_df,
        x="total_score",
        y="person",
        orientation="h",
        title="Total Creative Score — suma ze wszystkich zadań osoby",
        labels={"total_score": "Total Score", "person": "Osoba"},
        color="total_score",
        color_continuous_scale="Viridis",
        hover_data={"total_score": ":.1f", "score": ":.2f", "time_hours": True, "creative_hours": True, "creative_percent": True},
        category_orders={"person": top_tasks_df["person"].tolist()},  # Zachowaj kolejność rankingu
    )
    fig.update_layout(
        height=max(CHART_MIN_HEIGHT, len(top_tasks_df) * CHART_ROW_HEIGHT),
        xaxis_title="Total Creative Score (suma wszystkich zadań)",
        yaxis_title="",
        coloraxis_colorbar_title="Total Score",
    )
    st.plotly_chart(fig, width='stretch')


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
    st.markdown("**📋 Tabela danych**")

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

    columns_to_show = [
        "person",
        "task",
        "key",
        "time_display",
        "creative_percent_display",
        "creative_hours_display",
    ]

    st.dataframe(
        display_df[columns_to_show],
        column_config={
            "person": st.column_config.TextColumn("👤 Osoba", width="medium"),
            "task": st.column_config.TextColumn("📋 Zadanie", width="large"),
            "key": st.column_config.TextColumn("🔑 Klucz", width="small"),
            "time_display": st.column_config.TextColumn("⏰ Czas", width="small"),
            "creative_percent_display": st.column_config.TextColumn(
                "🎨 %", width="small"
            ),
            "creative_hours_display": st.column_config.TextColumn(
                "✨ Godz. twórcze", width="small"
            ),
        },
        width='stretch',
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
            st.plotly_chart(fig1, width='stretch')

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
                st.plotly_chart(fig2, width='stretch')
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
                st.plotly_chart(fig_heatmap, width='stretch')
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
            st.plotly_chart(fig_comparison, width='stretch')


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
            width='stretch',
        )

    with col2:
        excel_buffer, excel_filename = export_to_excel(df_filtered, creative_summary)
        st.download_button(
            label="📊 Pobierz Excel (2 arkusze)",
            data=excel_buffer,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
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
    status = "✅ Pełny miesiąc" if is_complete else f"⚠️ Część miesiąca"

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

        total_hours = month_data["time_hours"].sum()
        working_days = month_data["Start Date"].dt.date.nunique()
        creative_hours = month_data["creative_hours"].sum()

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
            st.metric("👥 Osób", month_data["person"].nunique())

    # Executive Summary dla miesiąca
    st.markdown("---")
    render_executive_summary(month_data)
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
    st.plotly_chart(fig_timeline, width='stretch')

    # Top zadania per osoba
    st.markdown("### 🎯 Top zadanie per osoba")
    top_tasks_month = get_top_task_per_person(month_data)

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
            width='stretch',
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
        st.plotly_chart(fig_day_total, width='stretch')

    with col2:
        fig_day_avg = px.bar(
            x=daily_weekday.index,
            y=daily_weekday["mean"],
            title="Średnio godzin per dzień",
            labels={"x": "Dzień", "y": "Średnia"},
            color_discrete_sequence=["#2ca02c"],
        )
        fig_day_avg.update_layout(height=350)
        st.plotly_chart(fig_day_avg, width='stretch')

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
                    color_continuous_scale="RdYlGn",
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
            key="personal_dashboard_person_selector"
        )
    
    with col_month:
        if has_months:
            months_available = sorted(df["month_str"].dropna().unique(), reverse=True)
            selected_month = st.selectbox(
                "📅 Okres",
                options=["Wszystkie"] + months_available,
                key="personal_dashboard_month_selector"
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
            st.warning("⚠️ **Uwaga:** Statystyki i koszty dotyczą CAŁEGO okresu danych (wszystkie miesiące razem), nie jednego miesiąca!")
        else:
            st.info("ℹ️ Statystyki dotyczą całego okresu danych w pliku.")
    else:
        st.success(f"✅ Statystyki dla miesiąca: **{selected_month}**")
    
    st.markdown(f"### 📊 Statystyki dla: **{selected_person}**")
    st.markdown("---")
    
    # METRYKI GŁÓWNE
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="📅 Liczba zadań",
            value=stats["num_tasks"]
        )
    
    with col2:
        st.metric(
            label="⏰ Łączne godziny",
            value=f"{stats['total_hours']:.1f}h"
        )
    
    with col3:
        st.metric(
            label="✨ Godziny twórcze",
            value=f"{stats['creative_hours']:.1f}h"
        )
    
    with col4:
        if stats["creative_percent_avg"] is not None:
            st.metric(
                label="🎨 Średnia twórczość",
                value=f"{stats['creative_percent_avg']:.0f}%"
            )
        else:
            st.metric(
                label="🎨 Średnia twórczość",
                value="—"
            )
    
    st.markdown("---")
    
    # CREATIVE SCORE
    st.markdown("### 🏆 Creative Score")
    st.metric(
        label="Creative Score (suma wszystkich zadań)",
        value=f"{stats['creative_score']:.1f}",
        help="Suma (creative_hours × creative_% / 100) ze wszystkich zadań"
    )
    
    st.markdown("---")
    
    # KALKULATOR KOSZTÓW
    st.markdown("### 💰 Kalkulator kosztów pracy")
    
    col_salary, col_hours = st.columns(2)
    
    with col_salary:
        brutto_salary = st.number_input(
            "Wynagrodzenie brutto miesięczne (PLN)",
            min_value=0.0,
            value=10000.0,
            step=500.0,
            key=f"salary_{selected_person}"
        )
    
    with col_hours:
        monthly_hours = st.number_input(
            "Godzin roboczych miesięcznie",
            min_value=1,
            value=168,
            step=1,
            help="Standardowo: 168h (21 dni × 8h), opcjonalnie: 160h lub 176h",
            key=f"hours_{selected_person}"
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
            creative_cost = (stats["creative_hours"] / stats["total_hours"] * brutto_salary) if stats["total_hours"] > 0 else 0
        else:
            total_cost = stats["total_hours"] * hourly_rate
            creative_cost = stats["creative_hours"] * hourly_rate
        
        # Analiza najbardziej i najmniej kosztownych zadań
        most_expensive_task = None
        least_expensive_task = None
        
        if not df_filtered.empty and stats["total_hours"] > 0:
            tasks_with_cost = df_filtered.copy()
            
            # Oblicz koszt dla każdego zadania
            if selected_month != "Wszystkie":
                # Dla konkretnego miesiąca: proporcjonalnie do udziału godzin
                tasks_with_cost["task_cost"] = (tasks_with_cost["time_hours"] / stats["total_hours"]) * brutto_salary
            else:
                # Dla wszystkich miesięcy: godziny × stawka
                tasks_with_cost["task_cost"] = tasks_with_cost["time_hours"] * hourly_rate
            
            # Filtruj zadania z czasem > 0
            valid_tasks = tasks_with_cost[tasks_with_cost["time_hours"] > 0].copy()
            
            if not valid_tasks.empty:
                # Najbardziej kosztowne zadanie
                most_expensive_idx = valid_tasks["task_cost"].idxmax()
                most_expensive_task = {
                    "task": valid_tasks.loc[most_expensive_idx, "task"],
                    "key": valid_tasks.loc[most_expensive_idx, "key"] if "key" in valid_tasks.columns else "—",
                    "hours": valid_tasks.loc[most_expensive_idx, "time_hours"],
                    "creative_percent": valid_tasks.loc[most_expensive_idx, "creative_percent"] if "creative_percent" in valid_tasks.columns else 0,
                    "cost": valid_tasks.loc[most_expensive_idx, "task_cost"]
                }
                
                # Najmniej kosztowne zadanie (najmniejszy koszt)
                least_expensive_idx = valid_tasks["task_cost"].idxmin()
                least_expensive_task = {
                    "task": valid_tasks.loc[least_expensive_idx, "task"],
                    "key": valid_tasks.loc[least_expensive_idx, "key"] if "key" in valid_tasks.columns else "—",
                    "hours": valid_tasks.loc[least_expensive_idx, "time_hours"],
                    "creative_percent": valid_tasks.loc[least_expensive_idx, "creative_percent"] if "creative_percent" in valid_tasks.columns else 0,
                    "cost": valid_tasks.loc[least_expensive_idx, "task_cost"]
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
                help_text = f"Obliczony dla {stats['total_hours']:.1f}h z wybranego okresu"
            else:
                help_text = f"Pełne wynagrodzenie miesięczne za {selected_month}"
            st.metric(
                label="💸 Koszt całkowity czasu pracy",
                value=f"{total_cost:,.2f} PLN",
                help=help_text
            )
        
        with col_cost2:
            if selected_month == "Wszystkie":
                help_text = f"Koszt {stats['creative_hours']:.1f}h faktycznie twórczych"
            else:
                help_text = f"{stats['creative_hours']:.1f}h twórczych / {stats['total_hours']:.1f}h łącznie = {stats['creative_hours']/stats['total_hours']*100:.0f}% wynagrodzenia" if stats["total_hours"] > 0 else "Brak godzin"
            st.metric(
                label="💎 Wartość pracy twórczej",
                value=f"{creative_cost:,.2f} PLN",
                help=help_text
            )
        
        st.markdown("---")
        
        # Najbardziej i najmniej kosztowne zadanie
        if most_expensive_task or least_expensive_task:
            st.markdown("### 🎯 Analiza kosztów zadań")
            
            col_exp, col_cheap = st.columns(2)
            
            with col_exp:
                if most_expensive_task:
                    st.markdown("#### 💎 Najbardziej kosztowne")
                    st.markdown(f"**{most_expensive_task['task']}**")
                    st.caption(f"🔑 {most_expensive_task['key']}")
                    st.metric(
                        label="Koszt zadania",
                        value=f"{most_expensive_task['cost']:,.2f} PLN"
                    )
                    st.caption(
                        f"⏱️ Czas: {most_expensive_task['hours']:.1f}h | "
                        f"🎨 Twórczość: {most_expensive_task['creative_percent']:.0f}%"
                    )
            
            with col_cheap:
                if least_expensive_task:
                    st.markdown("#### 💸 Najmniej kosztowne")
                    st.markdown(f"**{least_expensive_task['task']}**")
                    st.caption(f"🔑 {least_expensive_task['key']}")
                    st.metric(
                        label="Koszt zadania",
                        value=f"{least_expensive_task['cost']:,.2f} PLN"
                    )
                    st.caption(
                        f"⏱️ Czas: {least_expensive_task['hours']:.1f}h | "
                        f"🎨 Twórczość: {least_expensive_task['creative_percent']:.0f}%"
                    )
        
        st.markdown("---")
        
        # Koszty per kategoria
        if stats["categories_breakdown"]:
            st.markdown("### 📋 Koszty per kategoria zadań")
            
            categories_cost_data = []
            for cat, data in stats["categories_breakdown"].items():
                if selected_month != "Wszystkie":
                    # Dla konkretnego miesiąca - proporcjonalnie do udziału godzin
                    cat_cost = (data["hours"] / stats["total_hours"] * brutto_salary) if stats["total_hours"] > 0 else 0
                    creative_cat_cost = (data["creative_hours"] / stats["total_hours"] * brutto_salary) if stats["total_hours"] > 0 else 0
                else:
                    # Dla wszystkich miesięcy - godziny * stawka
                    cat_cost = data["hours"] * hourly_rate
                    creative_cat_cost = data["creative_hours"] * hourly_rate
                    
                categories_cost_data.append({
                    "Kategoria": cat,
                    "Liczba zadań": data["count"],
                    "Godziny": data["hours"],
                    "Koszt [PLN]": cat_cost,
                    "Godz. twórcze": data["creative_hours"],
                    "Wartość twórcza [PLN]": creative_cat_cost,
                })
            
            if categories_cost_data:
                cost_df = pd.DataFrame(categories_cost_data)
                cost_df = cost_df.sort_values("Koszt [PLN]", ascending=False)
                
                # Formatuj
                cost_df_display = cost_df.copy()
                cost_df_display["Godziny"] = cost_df_display["Godziny"].apply(lambda x: f"{x:.1f}h")
                cost_df_display["Koszt [PLN]"] = cost_df_display["Koszt [PLN]"].apply(lambda x: f"{x:,.2f}")
                cost_df_display["Godz. twórcze"] = cost_df_display["Godz. twórcze"].apply(lambda x: f"{x:.1f}h")
                cost_df_display["Wartość twórcza [PLN]"] = cost_df_display["Wartość twórcza [PLN]"].apply(lambda x: f"{x:,.2f}")
                
                st.dataframe(cost_df_display, use_container_width=True, hide_index=True)
                
                if selected_month != "Wszystkie":
                    st.caption(
                        f"✅ Koszty per kategoria obliczone proporcjonalnie do udziału godzin. "
                        f"Suma kosztów wszystkich kategorii = {brutto_salary:,.0f} PLN (pełne wynagrodzenie miesięczne)."
                    )
                else:
                    st.caption(
                        f"⚠️ Koszty obliczone jako (godziny × stawka godzinowa) dla całego okresu. "
                        f"Wybierz konkretny miesiąc powyżej, żeby zobaczyć podział wynagrodzenia miesięcznego."
                    )
                
                # Wykres kosztów
                fig_cost = px.bar(
                    cost_df,
                    x="Koszt [PLN]",
                    y="Kategoria",
                    orientation="h",
                    title="Koszt pracy per kategoria",
                    labels={"Koszt [PLN]": "Koszt (PLN)", "Kategoria": ""},
                    color="Wartość twórcza [PLN]",
                    color_continuous_scale="Viridis",
                )
                fig_cost.update_layout(height=400)
                st.plotly_chart(fig_cost, use_container_width=True)
    
    st.markdown("---")
    
    # TOP ZADANIA
    if stats["top_tasks_df"] is not None and not stats["top_tasks_df"].empty:
        st.markdown("### 🎯 Top 10 zadań (według Creative Score)")
        
        top_tasks_display = stats["top_tasks_df"].copy()
        top_tasks_display["time_hours"] = top_tasks_display["time_hours"].apply(lambda x: f"{x:.1f}h")
        top_tasks_display["creative_percent"] = top_tasks_display["creative_percent"].apply(lambda x: f"{int(x)}%")
        top_tasks_display["creative_hours"] = top_tasks_display["creative_hours"].apply(lambda x: f"{x:.1f}h")
        top_tasks_display["task_score"] = top_tasks_display["task_score"].apply(lambda x: f"{x:.2f}")
        
        top_tasks_display.columns = ["📋 Zadanie", "🔑 Klucz", "⏰ Czas", "🎨 %", "✨ Godz. twórcze", "💎 Score"]
        
        st.dataframe(top_tasks_display, use_container_width=True, hide_index=True)


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
    st.dataframe(example_data, width='stretch')


# =============================================================================
# GŁÓWNA FUNKCJA
# =============================================================================


def main():
    st.title("📊 Raport Czasu Pracy i Pracy Twórczej")

    # Sidebar
    worklogs_file, uploaded_file = render_sidebar()

    if worklogs_file is None:
        st.info("👈 Wgraj plik Worklogs w panelu bocznym aby rozpocząć analizę.")
        render_help_tab()
        return
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

        st.success(
            f"✅ Załadowano {len(df_worklogs)} wpisów worklogs ({len(df_processed_full)} unikatowych zadań)"
        )

        # Filtruj wykluczone osoby TYLKO DLA DASHBOARDU (nie dla metryk)
        EXCLUDED_PEOPLE = ["Justyna Kalota", "Piotr Janeczek"]
        df_processed = df_processed_full[
            ~df_processed_full["person"].isin(EXCLUDED_PEOPLE)
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
                    pd.to_numeric(df_totals_raw["Level"], errors="coerce").fillna(0).astype(int)
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
            df_worklogs_by_month = {
                month: group.copy()
                for month, group in df_worklogs.groupby("month_str")
            }
            months_available = sorted(df_worklogs_by_month.keys(), reverse=True)

        # METRYKI (zawsze widoczne) - WSZYSTKIE OSOBY
        render_metrics(df_processed_full)
        st.markdown("---")

        # TABS - porządek: Dashboard → Worklogs (jeśli dostępne) → Personal Dashboard → Pomoc
        if months_available:
            tabs = ["📊 Dashboard", "📋 Worklogs", "👤 Personal Dashboard", "❓ Pomoc"]
        else:
            tabs = ["📊 Dashboard", "👤 Personal Dashboard", "❓ Pomoc"]
        tab_objects = st.tabs(tabs)

        # TAB 0: DASHBOARD
        with tab_objects[0]:
            # Executive Summary
            render_executive_summary(df_processed)
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
                    month: df[~df["person"].isin(EXCLUDED_PEOPLE)].copy()
                    for month, df in df_worklogs_by_month.items()
                }
                render_worklogs_section(df_worklogs_by_month_filtered, months_available)

        # TAB 2 (lub 1): PERSONAL DASHBOARD
        personal_tab_index = 2 if months_available else 1
        with tab_objects[personal_tab_index]:
            # Jeśli mamy worklogs - użyj ich (mają month_str), jeśli nie - użyj df_processed
            df_for_personal = df_worklogs if not df_worklogs.empty else df_processed
            # Filtruj wykluczone osoby
            df_for_personal = df_for_personal[~df_for_personal["person"].isin(EXCLUDED_PEOPLE)].copy()
            
            # Debug info
            if df_for_personal.empty:
                st.error("❌ Brak danych po filtracji!")
                st.info(f"Worklogs empty: {df_worklogs.empty}, Processed rows: {len(df_processed)}")
            
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
