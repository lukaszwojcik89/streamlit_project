# Raport Czasu Pracy i Pracy Twórczej

Aplikacja webowa do analizy czasu pracy i procentu pracy twórczej na podstawie eksportów z Jiry. Umożliwia wizualizację danych, obliczanie wskaźników kreatywności oraz eksport raportów do Excel/CSV.

## ✨ Funkcjonalności

- **Worklogs** (główne źródło) - analiza szczegółowych logów pracy z datami, autorami, typami zadań
- **Agregacja danych** - automatyczne podsumowanie per osoba/zadanie bez utraty informacji
- **Creative Score** - wskaźnik łączący czas pracy z poziomem kreatywności
- **Analizy per miesiąc** - timeline, rozkład tygodniowy, statystyki
- **Wykresy interaktywne** - heatmapy, wykresy słupkowe, timeline (Plotly)
- **Eksport danych** - CSV oraz Excel z profesjonalnym formatowaniem i kolorowaniem
- **Porównanie z Totals** (opcjonalnie) - struktura Level 0/1/2 dla porównania

## 📋 Wymagania

- Python 3.10+
- Zależności: `streamlit`, `pandas`, `plotly`, `openpyxl`

## 🚀 Szybki Start

### ⚡ Opcja 1: Automatyczna instalacja (REKOMENDOWANA)

#### Windows
```bash
# 1. Klonowanie repozytorium
git clone <repo-url>
cd misc

# 2. Uruchom skrypt instalacyjny
setup.bat
```

#### macOS / Linux
```bash
# 1. Klonowanie repozytorium
git clone <repo-url>
cd misc

# 2. Uruchom skrypt instalacyjny
bash setup.sh
```

Skrypt automatycznie:
- ✅ Sprawdza czy Python 3.10+ jest zainstalowany
- ✅ Tworzy wirtualne środowisko
- ✅ Uaktualnia pip
- ✅ Instaluje wszystkie zależności
- ✅ Testuje importy
- ✅ Wyświetla instrukcję uruchomienia aplikacji

---

### 📋 Opcja 2: Manualna instalacja (krok po kroku)

#### Windows
```bash
# 1. Klonowanie repozytorium
git clone <repo-url>
cd misc

# 2. Utworzenie środowiska wirtualnego
python -m venv .venv

# 3. Aktywacja środowiska
.venv\Scripts\activate

# 4. Instalacja zależności
pip install -r requirements.txt

# 5. Uruchomienie aplikacji
streamlit run app.py
```

#### macOS / Linux
```bash
# 1. Klonowanie repozytorium
git clone <repo-url>
cd misc

# 2. Utworzenie środowiska wirtualnego
python3 -m venv .venv

# 3. Aktywacja środowiska
source .venv/bin/activate

# 4. Instalacja zależności
pip install -r requirements.txt

# 5. Uruchomienie aplikacji
streamlit run app.py
```

---

**Aplikacja uruchomi się pod adresem:** `http://localhost:8501`

## 📂 Struktura projektu

```
misc/
├── app.py                    # Główna aplikacja Streamlit
├── helpers.py                # Funkcje pomocnicze (parsowanie, formatowanie)
├── export_utils.py           # Logika eksportu (CSV, Excel)
├── config.py                 # Konfiguracja, stałe
├── setup.sh                  # Skrypt instalacji dla macOS/Linux
├── setup.bat                 # Skrypt instalacji dla Windows
├── requirements.txt          # Zależności Python
├── README.md                 # Ten plik
├── CHANGELOG.md              # Historia zmian
├── LICENSE                   # Licencja MIT
├── .gitignore                # Ignorowanie plików git
└── data/                     # Pliki przykładowe (opcjonalnie)
```

## 📥 Przygotowanie danych

## 📥 Przygotowanie danych

### Worklogs (💡 PRIMARY - główne źródło)

Eksport z Jiry zawierający:

| Kolumna | Opis |
|---------|------|
| **Author** | Osoba, która logowała czas |
| **Issue Key** | Klucz zadania (np. AOTM-123) |
| **Issue Summary** | Nazwa zadania/problemu |
| **Start Date** | Data rozpoczęcia |
| **Time Spent** | Czas pracy (format HH:MM, np. 03:00) |
| **Procent pracy twórczej** | % twórczości (0-100) |
| **Issue Type** | Typ (Story, Bug, Subtask itp.) |
| **Issue Status** | Status (To Do, In Progress, Done) |
| **Components** | Moduł/komponent |

Aplikacja automatycznie agreguje wpisy (każda osoba per każde zadanie).

### Raport główny (opcjonalnie) - struktura Level 0/1/2

Dla porównania danych. Struktura:

| Level | Users / Issues / Procent pracy twórczej | Key | Total Time Spent |
|-------|----------------------------------------|-----|------------------|
| 0 | Jan Kowalski | | |
| 1 | Implementacja modułu | PROJ-123 | 10:00 |
| 2 | 90 | | |

- **Level 0** - nazwa użytkownika
- **Level 1** - zadanie z kluczem Jira i czasem pracy (format HH:MM)
- **Level 2** - procent pracy twórczej (0-100)

## 🧮 Jak działa aplikacja

```
1. Wgraj Worklogs (.xlsx)
   ↓
2. Aplikacja przetwarza dane
   - Parsuje czas (HH:MM → godziny)
   - Oblicza godziny twórcze
   - Agreguje per osoba + zadanie
   ↓
3. Wyświetla analizy
   - Executive Summary
   - Ranking Creative Score
   - Szczegółowe dane
   - Wykresy analityczne
   - Analizy per miesiąc
   ↓
4. Eksportuje wyniki (CSV/Excel)
```

## 📊 Obliczenia

- **Godziny twórcze** = czas pracy × (procent twórczości / 100)
  - Przykład: 10h × 90% = 9h twórczych

- **Creative Score** = godziny twórcze × (procent twórczości / 100)
  - Nagradza HIGH TIME + HIGH CREATIVITY
  - Przykład: 9h twórczych × (90/100) = 8.1 score

## 📊 Eksport danych

### CSV

- Kodowanie UTF-8 z BOM (poprawne wyświetlanie polskich znaków w Excel)

### Excel

- **Dwa arkusze:**
  - `Worklogs / Raport pracy` - szczegółowe dane per osoba/zadanie
  - `Podsumowanie` - agregacja per osoba

- **Formatowanie:**
  - Kolorowanie procentów twórczości:
    - 🔴 Czerwony: ≤50%
    - 🟡 Żółty: 51-80%
    - 🟢 Zielony: >80%
  - Zamrożony nagłówek
  - Filtry automatyczne

## 🛠️ Dla developerów

### Architektura

- **app.py** - UI Streamlit i main flow
- **helpers.py** - funkcje do przetwarzania danych (parsowanie, formatowanie, agregacja)
- **export_utils.py** - logika eksportu (CSV, Excel) z stylowaniem
- **config.py** - stałe, progi kolorów, szerokości kolumn

### Funkcje kluczowe

```python
process_worklogs_data()           # Zaladuj i przetwórz worklogs
aggregate_worklogs_to_report()    # Agreguj per (person, key)
process_excel_data()              # Zaladuj stary format Level 0/1/2
export_to_csv()                   # Export do CSV
export_to_excel()                 # Export do Excel 2-arkuszowy
```

### Uruchomienie w trybie dev

```bash
# Bez cachingu (dla testów)
streamlit run app.py --logger.level=debug

# Z reload'em kodu
streamlit run app.py --server.runOnSave=true
```

### Testowanie

```bash
# Sprawdzenie składni wszystkich plików
python -m py_compile app.py helpers.py export_utils.py config.py

# Test agregacji (w folderze data/ muszą być przykłady xlsx)
python debug_aggregation.py
```

## ❓ Troubleshooting

### Procenty się nie ładują?

- Użyj przycisku "🔄 Wyczyść cache" w panelu bocznym

### Polskie znaki wyświetlają się niepoprawnie?

- Aplikacja automatycznie naprawia typowe błędy kodowania (np. `Ä…` → `ą`)
- Jeśli problem się powtarza, sprawdź kodowanie encodingu pliku Excel

### Plik zbyt duży?

- Maksymalny rozmiar pliku: 50MB
- Dla plików >10MB przetwarzanie może potrwać dłużej
- Rozważ podzielenie na części (np. per kwartał)

### App nie startuje na Mac?

- Sprawdź czy masz `python3` zamiast `python`:

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### "ModuleNotFoundError" po instalacji?

```bash
# Przeinstaluj środowisko
rm -rf .venv
python -m venv .venv
source .venv/bin/activate  # lub .venv\Scripts\activate na Windows
pip install -r requirements.txt
```

## 📝 Licencja

MIT (patrz LICENSE file)

## 👤 Autor

Łukasz Wójcik

## 🤝 Wkład

Pull requests mile widziane! Dla większych zmian otwórz issue najpierw.
