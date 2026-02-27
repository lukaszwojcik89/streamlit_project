# -*- coding: utf-8 -*-
import pandas as pd

worklogs_file = "data/worklogs_2025-12-01_2026-02-28(1).xlsx"
df_wl = pd.read_excel(worklogs_file)

print("=" * 100)
print("ANALIZA WSZYSTKICH KOLUMN W WORKLOGACH")
print("=" * 100)

# Wyświetl wszystkie kolumny z info co w nich jest
for i, col in enumerate(df_wl.columns, 1):
    non_null = df_wl[col].notna().sum()
    unique = df_wl[col].nunique()
    dtype = df_wl[col].dtype
    
    # Pobierz sample wartości
    samples = df_wl[col].dropna().unique()[:2]
    
    print(f"\n{i:2d}. {col}")
    print(f"    Typ: {dtype} | Non-null: {non_null:,}/{len(df_wl)} | Unique: {unique}")
    if len(samples) > 0:
        print(f"    Przykłady: {list(samples)}")

print("\n" + "=" * 100)
print("KLUCZOWE KOLUMNY DLA ANALIZY")
print("=" * 100)

# Kolumny kluczowe
key_cols = [
    'Issue Key', 'Issue Summary', 'Author', 'Time Spent', 'Start Date',
    'Issue Type', 'Issue Status', 'Procent pracy twórczej', 'Story Points',
    'Components', 'Project Key', 'Epic Key', 'Epic Summary'
]

print("\nUzytkowe kolumny:")
for col in key_cols:
    if col in df_wl.columns:
        non_null = df_wl[col].notna().sum()
        print(f"  ✓ {col:40s} - {non_null:,}/{len(df_wl)} ({100*non_null/len(df_wl):.0f}%)")

print("\n" + "=" * 100)
print("POROWNANIE DANYCH")
print("=" * 100)

# Sumowanie czasu per osoba z worklogs
by_person = df_wl.groupby('Author').agg({
    'Time Spent (seconds)': 'sum',
    'Issue Key': 'nunique',
    'Issue Summary': 'nunique'
}).sort_values('Time Spent (seconds)', ascending=False)

by_person['Time Spent (hours)'] = by_person['Time Spent (seconds)'] / 3600
by_person = by_person[['Time Spent (hours)', 'Issue Key', 'Issue Summary']]
by_person.columns = ['Godziny', 'Unikatowe Keys', 'Unikatowe Tasiki']

print("\nTop 10 osób (z worklogs):")
print(by_person.head(10).to_string())

print(f"\nLaczne godziny z worklogs: {by_person['Godziny'].sum():.1f}h")
print(f"Liczba osób: {len(by_person)}")
