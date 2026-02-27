import pandas as pd

# Wczytaj worklogs
df = pd.read_excel("data/worklogs_2025-12-01_2026-02-28(1).xlsx")

summary_col = "Issue Summary"
creative_col = "Procent pracy twórczej"

print("=" * 100)
print("ANALIZA KATEGORII ZADAŃ NA PODSTAWIE 'ISSUE SUMMARY'")
print("=" * 100)

# Kategorie z rozszerzonymi keywords (specificzny order - wazne!)
# Fragmenty słów aby łapać odmiany: np. "napr" zgryzie "naprawiać", "naprawę", "napraw"
keywords = {
    "Bug/Hotfix": [
        "bug",
        "hotfix",
        "crash",
        "błąd",
        "error",
        "problem z",
        "niezgodność",
        "uszkodz",
        "awaria",
        "napr",
        "fix",
    ],
    "Code Review": [
        "review",
        "pull request",
        "pr ",
        "feedback code",
        "sprawdzenie kodu",
        "code review",
    ],
    "Testing": [
        "test",
        "qa",
        "validation",
        "weryfikacja",
        "acceptance",
        "e2e",
        "unit",
        "testowani",
        "testy",
    ],
    "Development/Implementacja": [
        "feature",
        "implement",
        "develop",
        "build",
        "funkcj",
        "kod",
        "refactor",
        "wdrożeni",
        "stworz",
        "endpoint",
        "komponent",
        "obsług",
        "logik",
        "edycj",
        "popraw",
        "ulepsz",
        "improve",
        "edycja",
    ],
    "Analiza/Design": [
        "analiz",
        "przegląd",
        "diagram",
        "design",
        "dokumentuj",
        "architektur",
        "zapoznani",
        "sprawdz",
        "research",
        "badani",
        "ocen",
        "koncepj",
        "wymagan",
    ],
    "DevOps/Infrastruktura": [
        "deploy",
        "deployment",
        "ci/cd",
        "ci ",
        "cd ",
        "pipeline",
        "gitlab-ci",
        "docker",
        "kubernetes",
        "infra",
        "serwer",
        "baza danych",
        "monitoring",
        "logging",
        "konfiguruj",
        "infrastructure",
        "środowisk",
    ],
    "Szkolenia/Uczenie": [
        "szkoleni",
        "webinar",
        "training",
        "workshop",
        "moduł",
        "kurs",
        "nauk",
        "edukacj",
        "certifikacj",
        "copilot",
        "samoszkoleni",
    ],
    "Administracja/Support": [
        "administraj",
        "support",
        "help desk",
        "help ",
        "incident",
        "zgłoszeni",
        "obsług",
        "wsparci",
        "mail",
        "telefon",
        "biuro",
        "dostęp",
        "uprawni",
        "konto",
    ],
    "Spotkania/Sesje": [
        "spotkani",
        "meeting",
        "call",
        "standup",
        "daily",
        "retro",
        "retrospectiv",
        "planning",
        "refinement",
        "grooming",
        "sesj",
        "briefing",
        "sync",
        "kick-off",
        "komitet",
        "posiedzeni",
        "dyskusj",
        "scrum",
    ],
}

print("\n--- ROZKŁAD GODZIN I PROCENTU TWÓRCZOŚCI PER KATEGORIA ---\n")

for cat, kws in keywords.items():
    mask = df[summary_col].str.lower().str.contains("|".join(kws), na=False)
    if mask.sum() > 0:
        count = mask.sum()
        unique = df[mask][summary_col].nunique()
        avg_pct = df[mask][creative_col].mean()

        # Spróbuj obliczyć godziny (jeśli kolumna istnieje)
        if "Time Spent" in df.columns:
            try:
                # Time Spent w formacie HH:MM
                hours = (
                    df[mask]["Time Spent"]
                    .str.split(":")
                    .apply(lambda x: int(x[0]) + int(x[1]) / 60 if len(x) == 2 else 0)
                    .sum()
                )
            except:
                hours = 0
        else:
            hours = 0

        print(
            f"{cat:30} | {count:5} wpisów | {unique:3} zadań | {avg_pct:5.1f}% | {hours:6.1f}h"
        )

print("\n" + "=" * 100)
print("\nPRZYKŁADOWE ZADANIA Z KAŻDEJ KATEGORII:\n")

for cat, kws in keywords.items():
    mask = df[summary_col].str.lower().str.contains("|".join(kws), na=False)
    if mask.sum() > 0:
        print(f"\n{cat}:")
        samples = df[mask][summary_col].unique()[:6]
        for s in samples:
            pct = df[df[summary_col] == s][creative_col].mean()
            print(f"  {pct:5.0f}% - {s[:75]}")

print("\n" + "=" * 100)
print("\nWNIOSEK: Jakie kategorie zaproponować w insights?")
print("=" * 100)
