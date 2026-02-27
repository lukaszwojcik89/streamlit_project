# Changelog

Wszystkie ważne zmiany w projekcie zostaną zdokumentowane w tym pliku.

## [2.0.0] - 2025-01-22

### ✨ Nowe Funkcje

- **🔄 Worklogs-First Architecture**: Przesunięto na oparta o worklogi, a nie hierarchiczne dane
- **📅 Dane z datami**: Worklogi teraz zawierają daty, autorów i typy zgłoszeń
- **📊 Analiza miesięczna**: Nowa sekcja analizującą rozkład pracy na dni tygodnia
- **⏱️ Timeline Visualization**: Interaktywny timeline pokazujący pracę twórczą na procent
- **🎯 Creative Score**: Zaawansowany algorytm punktacji łączący chwile spędzony z procentem kreatywności
- **📥 Eksport Worklogs**: Eksport danych z worklogi na Excela z formatowaniem kolorami

### 🐛 Poprawki Błędów

- **CRITICAL**: Naprawiono problem, gdzie agregacja traciła 65% czasów pracy
  - Przyczyna: Funkcja `groupby(["key"])` ignorowała wiele autorów na klucz
  - Rozwiązanie: Zmieniono na `groupby(["person", "key"])`
  - Przykład: Łukasz Wójcik pokazywał 343.92h zamiast 408h
  - Weryfikacja: Test potwierdzuje 3433.6h czasu zachowanego, 408h dla Łukasza ✅

- Naprawiono deprecated API Streamlit (v1.54.0+)
  - Zmieniono 16 instancji `use_container_width=True` na `width='stretch'`

- Naprawiono kodowanie polskich znaków (ą, ę, ó, itd.)

- Naprawiono duplikowanie sekcji w sidebarze

- Naprawiono parsowanie danych worklogs

### 🏗️ Refaktoryzacja

- Podzielone `app.py` (1858 linii) na moduły:
  - `helpers.py` (521 linii) - Narzędzia do przetwarzania danych
  - `export_utils.py` (458 linii) - Eksport na Excel/CSV
  - `config.py` (199 linii) - Konfiguracja, kolory, szerokości kolumn
  - `app.py` (982 linii) - Logika aplikacji

- Reorganizacja UI:
  - Przeniesiono kluczowe informacje wyżej (overview)
  - Szczegóły w rozwijalnych sekcjach
  - Usunięto zbędne separatory

- Ograniczono zbędne duplikaty i optymalizacja layoutu

### 📋 Testowanie

- ✅ Syntax validation (py_compile)
- ✅ Import validation (pandas, streamlit, plotly, openpyxl)
- ✅ Aggregation test (3433.6h preserved, per-person calculation verified)
- ✅ Streamlit startup test

### 📚 Dokumentacja

- README.md zaktualizowany na worklogs-first architekturę
- Dodano sekcje Quick Start dla Windows i macOS/Linux
- Dodano Troubleshooting z 6 częstymi problemami
- Dodano Developer Guide z funkcjami i testowaniem

### 🚀 Deployment

- `setup.sh` - jednokomendowy setup dla Mac/Linux
- `setup.bat` - jednokomendowy setup dla Windows
- MIT License
- Zaktualizowany `.gitignore`

---

## [1.0.0] - Początkowa wersja

- Hierarchiczna struktura danych (Level 0/1/2 z pliku "Totals")
- Eksport na Excel z formatowaniem
- Analiza twórczości
- Dashboard Streamlit
