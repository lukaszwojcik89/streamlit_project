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

        st.subheader("📊 Raport główny")
        uploaded_file = st.file_uploader(
            "Plik Excel (.xlsx) - Level 0/1/2",
            type=["xlsx"],
            key="main_report",
            help="Użytkownik (0) / Zadanie (1) / % Twórczości (2)",
        )

        st.markdown("---")

        st.subheader("📋 Worklogs (opcjonalnie)")
        worklogs_file = st.file_uploader(
            "Worklogs z datami",
            type=["xlsx"],
            key="worklogs_file",
            help="Start Date, Issue Key, Time Spent, Procent pracy twórczej",
        )

        # Walidacja rozmiaru
        if uploaded_file:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                st.error(
                    f"❌ Plik zbyt duży: {file_size_mb:.1f}MB (max {MAX_FILE_SIZE_MB}MB)"
                )
                uploaded_file = None
            elif file_size_mb > LARGE_FILE_WARNING_MB:
                st.warning(f"⚠️ Duży plik: {file_size_mb:.1f}MB")

        st.markdown("---")
        st.header("ℹ️ Informacje")
        st.markdown(
            """
        **Struktura pliku (Level 0/1/2):**
        - Poziom 0: Nazwiska
        - Poziom 1: Zadania z czasem
        - Poziom 2: % pracy twórczej

        **Creative Score:**
        `godz_twórcze × (% / 100)`
        """
        )

    return uploaded_file, worklogs_file


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
    """Renderuje Executive Summary - kluczowe insights."""
    summary = generate_executive_summary(df)

    st.markdown("## 📋 Executive Summary")

    col1, col2, col3 = st.columns(3)

    with col1:
        if summary["top_performer"]:
            st.metric(
                "🏆 Top Performer",
                summary["top_performer"],
                delta=f"Score: {summary['top_performer_score']:.2f}",
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
                "🎨 Średni % twórczości", f"{summary['avg_creative_percent']:.0f}%"
            )
        else:
            st.metric("🎨 Średni % twórczości", "—")

    # Alerty
    if summary["alerts"]:
        with st.expander("⚠️ Uwagi i ostrzeżenia", expanded=False):
            for alert in summary["alerts"]:
                st.warning(alert)


def render_top_tasks_table(df: pd.DataFrame):
    """Renderuje tabelę i wykres Top Zadań per osoba."""
    st.markdown("## 🎯 Ranking Creative Score")
    st.caption(
        "Score = godziny twórcze × (% twórczości / 100) — "
        "nagradza kombinację zaangażowania i kreatywności"
    )

    top_tasks_df = get_top_task_per_person(df)

    if top_tasks_df.empty:
        st.info("Brak danych do wyświetlenia")
        return

    # Formatuj do wyświetlenia
    display_df = format_display_table(top_tasks_df)

    display_cols = [
        "person",
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
        "📋 Zadanie",
        "🔑 Klucz",
        "⏰ Czas",
        "🎨 %",
        "✨ Godz. twórcze",
        "🏆 Score",
        "📊 Typ",
    ]

    st.dataframe(
        display_df[display_cols].rename(columns=dict(zip(display_cols, display_names))),
        hide_index=True,
        width="stretch",
    )

    # Wykres
    fig = px.bar(
        top_tasks_df,
        x="score",
        y="person",
        orientation="h",
        title="Creative Score — balans czasu i kreatywności",
        labels={"score": "Score", "person": "Osoba"},
        color="creative_percent",
        color_continuous_scale="Viridis",
        hover_data=["time_hours", "creative_hours", "creative_percent"],
    )
    fig.update_layout(
        height=max(CHART_MIN_HEIGHT, len(top_tasks_df) * CHART_ROW_HEIGHT),
        xaxis_title="Creative Score",
        yaxis_title="",
        coloraxis_colorbar_title="% Twórczości",
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
        width="stretch",
        hide_index=True,
    )

    # Podsumowanie pracy twórczej
    st.markdown("**🎯 Podsumowanie pracy twórczej**")
    creative_summary = calculate_creative_summary(df_filtered)

    st.dataframe(
        creative_summary,
        column_config={
            "Łączne godziny": st.column_config.NumberColumn(format="%.1f h"),
            "Godziny twórcze": st.column_config.NumberColumn(format="%.1f h"),
            "% Pracy twórczej": st.column_config.NumberColumn(format="%.1f%%"),
            "Pokrycie danymi": st.column_config.NumberColumn(format="%.0f%%"),
        },
        width="stretch",
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
                creative_counts = (
                    creative_data["creative_percent"].value_counts().sort_index()
                )

                fig2 = px.pie(
                    values=creative_counts.values,
                    names=[f"{int(x)}%" for x in creative_counts.index],
                    title="Zadania według poziomu twórczości",
                )
                fig2.update_layout(height=400)
                st.plotly_chart(fig2, width="stretch")
            else:
                st.info("Brak danych o pracy twórczej.")

        # Dodatkowe wykresy
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Heatmapa: Osoba vs % twórczości**")
            creative_data = df_filtered.dropna(subset=["creative_percent"])
            if not creative_data.empty and len(creative_data) > 0:
                heatmap_data = (
                    creative_data.groupby(["person", "creative_percent"])
                    .size()
                    .reset_index(name="count")
                )
                heatmap_pivot = heatmap_data.pivot(
                    index="person", columns="creative_percent", values="count"
                ).fillna(0)

                fig_heatmap = px.imshow(
                    heatmap_pivot,
                    labels=dict(x="% Twórczości", y="Osoba", color="Liczba zadań"),
                    x=[f"{int(x)}%" for x in heatmap_pivot.columns],
                    y=heatmap_pivot.index,
                    color_continuous_scale="Blues",
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
    uploaded_file, worklogs_file = render_sidebar()

    if uploaded_file is None:
        st.info("👈 Wgraj plik Excel w panelu bocznym aby rozpocząć analizę.")
        render_help_tab()
        return

    try:
        # Wczytaj dane
        with st.spinner("📂 Wczytuję plik..."):
            df_raw = pd.read_excel(uploaded_file, engine="openpyxl")
            df_raw = apply_encoding_fix_to_dataframe(df_raw)

        # Sprawdź strukturę
        required_columns = ["Level", "Users / Issues / Procent pracy twórczej"]
        if not all(col in df_raw.columns for col in required_columns):
            st.error(f"❌ Brakujące kolumny: {required_columns}")
            st.info(f"Znalezione: {list(df_raw.columns)}")
            return

        # Waliduj
        issues, warnings = validate_data_structure(df_raw)

        if issues:
            st.error("❌ Krytyczne problemy:")
            for issue in issues:
                st.error(f"  • {issue}")
            return

        if warnings:
            with st.expander("⚠️ Potencjalne problemy", expanded=False):
                for warning in warnings:
                    st.warning(f"  • {warning}")

        # Konwertuj Level
        df_raw["Level"] = (
            pd.to_numeric(df_raw["Level"], errors="coerce").fillna(0).astype(int)
        )

        # Przetwórz dane
        with st.spinner("⚙️ Przetwarzam..."):
            df_processed = process_excel_data(df_raw)

        if df_processed.empty:
            st.warning("⚠️ Nie udało się przetworzyć danych.")
            return

        # Przetwórz worklogs jeśli wgrany
        df_worklogs_by_month = {}
        months_available = []

        if worklogs_file:
            try:
                with st.spinner("📋 Przetwarzam worklogs..."):
                    df_worklogs_raw = pd.read_excel(worklogs_file, engine="openpyxl")
                    df_worklogs = process_worklogs_data(df_worklogs_raw)

                    if not df_worklogs.empty:
                        df_worklogs_by_month = {
                            month: group.copy()
                            for month, group in df_worklogs.groupby("month_str")
                        }
                        months_available = sorted(
                            df_worklogs_by_month.keys(), reverse=True
                        )
                        st.success(
                            f"✅ Worklogs: {len(df_worklogs)} wpisów, "
                            f"miesiące: {', '.join(months_available)}"
                        )
            except Exception as e:
                st.error(f"❌ Błąd worklogs: {str(e)}")

        # METRYKI (zawsze widoczne)
        render_metrics(df_processed)
        st.markdown("---")

        # TABS
        tabs = ["📊 Dashboard", "📋 Worklogs", "❓ Pomoc"]
        if not months_available:
            tabs = ["📊 Dashboard", "❓ Pomoc"]

        tab_objects = st.tabs(tabs)

        # TAB 1: DASHBOARD
        with tab_objects[0]:
            # Executive Summary (NOWE!)
            render_executive_summary(df_processed)
            st.markdown("---")

            # Ranking Creative Score (WIDOCZNE DOMYŚLNIE!)
            render_top_tasks_table(df_processed)
            st.markdown("---")

            # Szczegółowe dane (widoczne domyślnie, nie w expanderze!)
            df_filtered, display_df = render_detailed_data(df_processed)

            # Wykresy (w expanderze)
            render_charts(df_filtered)
            st.markdown("---")

            # Eksport
            creative_summary = calculate_creative_summary(df_filtered)
            render_export_section(df_filtered, creative_summary)

        # TAB 2: WORKLOGS (jeśli dostępne)
        if months_available:
            with tab_objects[1]:
                render_worklogs_section(df_worklogs_by_month, months_available)

        # TAB 3 (lub 2): POMOC
        help_tab_index = 2 if months_available else 1
        with tab_objects[help_tab_index]:
            render_help_tab()

    except Exception as e:
        st.error(f"❌ Błąd: {str(e)}")
        with st.expander("🐞 Szczegóły techniczne"):
            import traceback

            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
