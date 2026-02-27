# -*- coding: utf-8 -*-
import pandas as pd
import sys
sys.path.insert(0, 'c:/projects/misc')

from helpers import parse_time_to_hours, extract_creative_percentage

# Test agregacji worklogs
worklogs_file = "data/worklogs_2025-12-01_2026-02-28(1).xlsx"

print("=" * 80)
print("TEST AGREGACJI WORKLOGS")
print("=" * 80)

# Załaduj raw
df_raw = pd.read_excel(worklogs_file)
print(f"\nRaw worklogs: {df_raw.shape}")
print(f"Kolumny: {list(df_raw.columns[:10])}")

# Przetwórz
df_work = df_raw.copy()
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

df_processed = df_work[[
    "person", "task", "key", "time_hours", "creative_percent", "creative_hours", "Start Date", "month_str",
]]

print(f"\nProcessed worklogs: {df_processed.shape}")
print(f"Pierwsze 3 wiersze:")
print(df_processed.head(3))

# Agreguj
df_agg = df_processed.groupby(["key"], as_index=False).agg({
    "time_hours": "sum",
    "creative_hours": "sum",
    "creative_percent": "first",
    "person": lambda x: x.iloc[0] if len(x) > 0 else "",
})

task_mapping = df_processed.groupby("key")["task"].first()
df_agg["task"] = df_agg["key"].map(task_mapping)

df_final = df_agg[["person", "task", "key", "time_hours", "creative_percent", "creative_hours"]]

print(f"\nAgregated: {df_final.shape}")
print(f"Pierwsze 5 wierszy:")
print(df_final.head(5))

print(f"\nLaczna walidacja:")
print(f"  Time in raw: {df_processed['time_hours'].sum():.1f}h")
print(f"  Time in agg: {df_final['time_hours'].sum():.1f}h")
print(f"  Match: {abs(df_processed['time_hours'].sum() - df_final['time_hours'].sum()) < 0.1}")

print(f"\n✅ Agregacja OK")
