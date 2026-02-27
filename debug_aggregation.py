# -*- coding: utf-8 -*-
import pandas as pd
<<<<<<< Updated upstream
=======
from helpers import parse_time_to_hours
>>>>>>> Stashed changes

worklogs_file = "data/worklogs_2025-12-01_2026-02-28(1).xlsx"
df_raw = pd.read_excel(worklogs_file)

print("=" * 80)
print("ANALIZA PROBLEMU - ISSUE KEY Z WIELOMA OSOBAMI")
print("=" * 80)

# Policz ile osób pracuje na kazdym Issue Key
key_people = df_raw.groupby('Issue Key')['Author'].nunique()
multi_person_keys = key_people[key_people > 1]

print(f"\nTotal Issue Keys: {len(key_people)}")
print(f"Keys z wieloma osobami: {len(multi_person_keys)}")

if len(multi_person_keys) > 0:
    print(f"\nPrzykłady keys z wieloma osobami:")
    for key in multi_person_keys.head(5).index:
        people_on_key = df_raw[df_raw['Issue Key'] == key]['Author'].unique()
        times = df_raw[df_raw['Issue Key'] == key][['Author', 'Time Spent']].values
        print(f"\n  {key}: {len(people_on_key)} osób")
        for author, time_spent in times:
            print(f"    - {author}: {time_spent}")

# Sprawdz ile czasu pominęliśmy
print("\n" + "=" * 80)
print("WPŁYW NA SUM CZASU")
print("=" * 80)

# Całkowity czas wszyscy
<<<<<<< Updated upstream
total_time = pd.to_timedelta(df_raw['Time Spent']).dt.total_seconds().sum() / 3600
print(f"\nCałkowity czas ze wszystkich wpisów: {total_time:.1f}h")

# Czas jeśli każdy key ma tylko 1 osobę (moja agregacja)
time_first_author_only = df_raw.groupby('Issue Key')['Time Spent'].first()
total_first = pd.to_timedelta(time_first_author_only).dt.total_seconds().sum() / 3600
=======
from helpers import parse_time_to_hours
total_time = df_raw['Time Spent'].apply(parse_time_to_hours).sum()
print(f"\nCałkowity czas ze wszystkich wpisów: {total_time:.1f}h")

# Czas jeśli każdy key ma tylko 1 osobę (moja agregacja)
# Ale czekaj - problem to jest że agregujemy po key bez względu na person!
# Musimy agregować per (person, key)
total_first = df_raw.groupby('Issue Key')['Time Spent'].apply(
    lambda x: parse_time_to_hours(x.iloc[0])
).sum()
>>>>>>> Stashed changes
print(f"Czas tylko pierwszego autora per key: {total_first:.1f}h")

print(f"\nBRAK: {total_time - total_first:.1f}h ({100*(total_time - total_first)/total_time:.1f}%)")

# Per osoba
print("\n" + "=" * 80)
print("CZY LUKASZ WÓJCIK MAL CZASAMI WSPÓLNE KEY?")
print("=" * 80)

# Zaladuj dane z naszym parsowaniem czasu
<<<<<<< Updated upstream
import sys
sys.path.insert(0, '.')
from helpers import parse_time_to_hours

=======
>>>>>>> Stashed changes
lukasz_worklogs = df_raw[df_raw['Author'] == 'Łukasz Wójcik']
print(f"\nŁukasz - liczba wpisów: {len(lukasz_worklogs)}")

lukasz_time = lukasz_worklogs['Time Spent'].apply(parse_time_to_hours).sum()
print(f"Rzeczywisty czas Łukasza: {lukasz_time:.2f}h")

# Sprawdź czy jego issue key'e są wspólne z innymi
lukasz_keys = set(lukasz_worklogs['Issue Key'].unique())
print(f"Liczba unikatowych Issue Keys gdzie pracował: {len(lukasz_keys)}")

# Które z jego keys mają innych autorów?
shared_keys = []
for key in lukasz_keys:
    authors_on_key = df_raw[df_raw['Issue Key'] == key]['Author'].unique()
    if len(authors_on_key) > 1:
        shared_keys.append((key, len(authors_on_key)))

print(f"Jego Issue Keys ze wspólnymi autorami: {len(shared_keys)}")
if shared_keys:
    print(f"Przykłady: {shared_keys[:5]}")
