# Raport Czasu Pracy i Pracy Twórczej

Aplikacja webowa do analizy czasu pracy i procentu pracy twórczej na podstawie eksportów z Jira. Umożliwia wizualizację danych, obliczanie wskaźników kreatywności oraz eksport raportów do Excel/CSV.

## Funkcjonalności

- **Analiza hierarchiczna** - przetwarzanie raportów w strukturze Użytkownik → Zadanie → % Twórczości
- **Worklogs** - analiza szczegółowych logów pracy z datami i podziałem na miesiące
- **Creative Score** - wskaźnik łączący czas pracy z poziomem kreatywności
- **Wykresy interaktywne** - heatmapy, wykresy słupkowe, timeline (Plotly)
- **Eksport danych** - CSV (UTF-8) oraz Excel z profesjonalnym formatowaniem i kolorowaniem

## Wymagania

- Python 3.10+
- Zależności: `streamlit`, `pandas`, `plotly`, `openpyxl`, `numpy`

## Instalacja

```bash
# Klonowanie repozytorium
git clone <repo-url>
cd misc

# Utworzenie środowiska wirtualnego
python -m venv .venv

# Aktywacja (Windows)
.venv\Scripts\activate

# Aktywacja (Linux/macOS)
source .venv/bin/activate

# Instalacja zależności
pip install -r requirements.txt
```

## Uruchomienie

```bash
streamlit run app.py
```

Aplikacja uruchomi się pod adresem `http://localhost:8501`

## Format plików wejściowych

### Raport główny (struktura Level 0/1/2)

Plik Excel z hierarchiczną strukturą:

| Level | Users / Issues / Procent pracy twórczej | Key | Total Time Spent |
|-------|----------------------------------------|-----|------------------|
| 0 | Jan Kowalski | | |
| 1 | Implementacja modułu logowania | PROJ-123 | 10:00 |
| 2 | 90 | | |
| 1 | Testowanie aplikacji | PROJ-124 | 5:30 |
| 2 | 50 | | |
| 0 | Anna Nowak | | |
| 1 | Projektowanie UI | PROJ-125 | 8:15 |
| 2 | 100 | | |

- **Level 0** - nazwa użytkownika
- **Level 1** - zadanie z kluczem Jira i czasem pracy (format HH:MM)
- **Level 2** - procent pracy twórczej (0-100)

### Worklogs (opcjonalnie)

Płaski format z datami:

| Author | Issue Key | Issue Summary | Start Date | Time Spent | Procent pracy twórczej |
|--------|-----------|---------------|------------|------------|------------------------|
| Jan Kowalski | PROJ-123 | Implementacja... | 2025-01-15 | 03:00 | 90 |

## Obliczenia

- **Godziny twórcze** = czas pracy × (procent twórczości / 100)
- **Creative Score** = godziny twórcze × (procent twórczości / 100)

Creative Score nagradza kombinację długiego czasu pracy i wysokiego procentu twórczości.

## Eksport

### CSV
- Kodowanie UTF-8 z BOM (poprawne wyświetlanie polskich znaków w Excel)

### Excel
- Dwa arkusze: szczegółowe dane + podsumowanie per osoba
- Kolorowanie procentów twórczości:
  - 🔴 Czerwony: ≤50%
  - 🟡 Żółty: 51-80%
  - 🟢 Zielony: >80%
- Zamrożony nagłówek, filtry automatyczne

## Struktura projektu

```
misc/
├── app.py              # Główna aplikacja Streamlit
├── app_refactored.py   # Alternatywna wersja z innym layoutem UI
├── requirements.txt    # Zależności Python
├── data/               # Przykładowe pliki Excel do testów
└── .venv/              # Środowisko wirtualne (nie commitować)
```

## Rozwiązywanie problemów

**Procenty się nie ładują?**
- Użyj przycisku "Wyczyść cache" w panelu bocznym

**Polskie znaki wyświetlają się niepoprawnie?**
- Aplikacja automatycznie naprawia typowe błędy kodowania (np. `Ä…` → `ą`)

**Plik zbyt duży?**
- Maksymalny rozmiar pliku: 50MB
- Dla plików >10MB przetwarzanie może potrwać dłużej
