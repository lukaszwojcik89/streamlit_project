# -*- coding: utf-8 -*-
import pandas as pd

# Zaladuj pliki
totals_file = "data/totals_2025-12-01_2026-02-28(3).xlsx"
worklogs_file = "data/worklogs_2025-12-01_2026-02-28(1).xlsx"

print("=" * 80)
print("POROWNANIE STRUKTURY DANYCH")
print("=" * 80)

# === TOTALS ===
print("\n1. TOTALS (Raport Level 0/1/2)")
print("-" * 80)
df_totals = pd.read_excel(totals_file)
print(f"Wymiary: {df_totals.shape}")
print(f"Kolumny: {list(df_totals.columns)}")
print(f"\nPiersze 3 wiersze:")
print(df_totals.head(3))

# === WORKLOGS ===
print("\n\n2. WORKLOGS")
print("-" * 80)
df_worklogs = pd.read_excel(worklogs_file)
print(f"Wymiary: {df_worklogs.shape}")
print(f"Kolumny: {list(df_worklogs.columns)}")
print(f"\nPiersze 3 wiersze:")
print(df_worklogs.head(3))

# === POROWNANIE ===
print("\n\n3. POROWNANIE")
print("-" * 80)
print(f"Totals:   {df_totals.shape[0]:,} wierszy x {df_totals.shape[1]} kolumn")
print(f"Worklogs: {df_worklogs.shape[0]:,} wierszy x {df_worklogs.shape[1]} kolumn")

print(f"\nIssue Keys (unikalnych):")
if 'Key' in df_totals.columns:
    totals_keys = set(df_totals['Key'].dropna().unique())
    print(f"  Totals: {len(totals_keys)} unikatowych keys")

if 'Issue Key' in df_worklogs.columns:
    worklogs_keys = set(df_worklogs['Issue Key'].dropna().unique())
    print(f"  Worklogs: {len(worklogs_keys)} unikatowych keys")
    
    if 'Key' in df_totals.columns:
        overlap = totals_keys & worklogs_keys
        only_totals = len(totals_keys - worklogs_keys)
        only_worklogs = len(worklogs_keys - totals_keys)
        print(f"\n  Wspolne: {len(overlap)}")
        print(f"  Tylko w Totals: {only_totals}")
        print(f"  Tylko w Worklogs: {only_worklogs}")

print(f"\nKolumny tworzysci:")
for df, name in [(df_totals, "Totals"), (df_worklogs, "Worklogs")]:
    creative_cols = [c for c in df.columns if 'procent' in c.lower() or 'creative' in c.lower()]
    print(f"  {name}: {creative_cols}")

print(f"\nKolumny czasowe:")
for df, name in [(df_totals, "Totals"), (df_worklogs, "Worklogs")]:
    time_cols = [c for c in df.columns if 'time' in c.lower() or 'date' in c.lower() or 'hour' in c.lower()]
    print(f"  {name}: {time_cols}")
