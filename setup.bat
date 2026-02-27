@echo off
REM Skrypt instalacji dla Windows

echo.
echo ================================================
echo 🚀 Raport Czasu Pracy - Setup dla Windows
echo ================================================

REM Check Python
echo.
echo 1️⃣ Sprawdzam Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python nie znaleziony. Zainstaluj Python 3.10+ i spróbuj ponownie.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ Python: %PYTHON_VERSION%

REM Create venv
echo.
echo 2️⃣ Tworzę wirtualne środowisko...
if exist .venv (
    if exist .venv\Scripts\python.exe (
        echo ✅ Folder .venv już istnieje. Pomijam tworzenie...
    ) else (
        echo ⚠️  Folder .venv istnieje, ale brak plików Pythona. Tworzę od nowa...
        rmdir /s /q .venv >nul 2>&1
        python -m venv .venv
        if errorlevel 1 (
            echo ❌ Błąd przy tworzeniu środowiska
            pause
            exit /b 1
        )
        echo ✅ Środowisko wirtualne utworzone
    )
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ Błąd przy tworzeniu środowiska
        pause
        exit /b 1
    )
    echo ✅ Środowisko wirtualne utworzone
)

REM Activate venv
echo.
echo 3️⃣ Aktywuję środowisko...
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo ✅ Środowisko aktywne
) else (
    echo ❌ Błąd: Nie znaleziono .venv\Scripts\activate.bat
    pause
    exit /b 1
)

REM Upgrade pip
echo.
echo 4️⃣ Aktualizuję pip...
python -m pip install --upgrade pip setuptools wheel >nul 2>&1
echo ✅ Pip zaktualizowany

REM Install requirements
echo.
echo 5️⃣ Instaluję zależności...
pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo ❌ Błąd przy instalacji zależności
    echo Spróbuj ręcznie: pip install -r requirements.txt
    pause
    exit /b 1
)
echo ✅ Zależności zainstalowane

REM Test imports
echo.
echo 6️⃣ Testuję importy...
python -c "import streamlit, pandas, plotly, openpyxl; print('✅ Wszystko OK!')" 2>nul
if errorlevel 1 (
    echo ❌ Błąd przy importach. Spróbuj uruchomić ponownie.
    pause
    exit /b 1
)

echo.
echo ================================================
echo ✅ Setup ukończony!
echo ================================================
echo.
echo 🎯 Aby uruchomić aplikację:
echo.
echo    .venv\Scripts\activate
echo    streamlit run app.py
echo.
echo 📌 Aplikacja uruchomi się pod: http://localhost:8501
echo.
pause
