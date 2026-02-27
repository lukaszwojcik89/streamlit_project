#!/bin/bash
# Skrypt instalacji dla macOS / Linux

set -e  # Exit on error

echo "================================================"
echo "🚀 Raport Czasu Pracy - Setup dla macOS/Linux"
echo "================================================"

# Check Python
echo ""
echo "1️⃣ Sprawdzam Python..."

# Prefer 'python' (works on Windows Git Bash), fallback to 'python3' (macOS/Linux)
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "❌ Python nie znaleziony. Zainstaluj Python 3.10+ i spróbuj ponownie."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version | cut -d' ' -f2)
echo "✅ Python: $PYTHON_VERSION"

# Create venv
echo ""
echo "2️⃣ Tworzę wirtualne środowisko..."
VENV_PY_WIN=".venv/Scripts/python.exe"
VENV_PY_UNIX=".venv/bin/python"

if [ -d ".venv" ]; then
    if [ -f "$VENV_PY_WIN" ] || [ -f "$VENV_PY_UNIX" ]; then
        echo "✅ Folder .venv już istnieje. Pomijam tworzenie..."
    else
        echo "⚠️  Folder .venv istnieje, ale brak plików Pythona. Tworzę od nowa..."
        rm -rf .venv
        $PYTHON_CMD -m venv .venv
        echo "✅ Środowisko wirtualne utworzone"
    fi
else
    $PYTHON_CMD -m venv .venv
    echo "✅ Środowisko wirtualne utworzone"
fi

# Activate venv
echo ""
echo "3️⃣ Aktywuję środowisko..."

# Check if already activated
if [ -n "$VIRTUAL_ENV" ]; then
    echo "✅ Środowisko już aktywne (VIRTUAL_ENV=$VIRTUAL_ENV)"
else
    # Try Windows path first
    if [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
        echo "✅ Środowisko aktywne (Windows Scripts/)"
    # Try Unix path
    elif [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo "✅ Środowisko aktywne (Unix bin/)"
    # Try bash variant on Windows
    elif [ -f ".venv/Scripts/activate.bat" ]; then
        # For git bash, we can source the bash version if it exists
        if [ -f ".venv/Scripts/activate.bash" ]; then
            source .venv/Scripts/activate.bash
            echo "✅ Środowisko aktywne (Windows Scripts bash)"
        else
            echo "⚠️  Znaleziono .venv ale nie się dało aktywować - spróbuj ręcznie:"
            echo "   source .venv/Scripts/activate.bat"
            exit 1
        fi
    else
        echo "❌ Błąd: Nie znaleziono skryptu aktywacji w:"
        echo "   - .venv/Scripts/activate (Windows)"
        echo "   - .venv/bin/activate (Unix/macOS)"
        exit 1
    fi
fi

# Upgrade pip
echo ""
echo "4️⃣ Aktualizuję pip..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo "✅ Pip zaktualizowany"

# Install requirements
echo ""
echo "5️⃣ Instaluję zależności..."
pip install -r requirements.txt > /dev/null 2>&1
echo "✅ Zależności zainstalowane"

# Test imports
echo ""
echo "6️⃣ Testuję importy..."
python -c "import streamlit, pandas, plotly, openpyxl; print('✅ Wszystko OK!')" 2>/dev/null || {
    echo "❌ Błąd przy importach. Spróbuj uruchomić ponownie."
    exit 1
}

echo ""
echo "================================================"
echo "✅ Setup ukończony!"
echo "================================================"
echo ""
echo "🎯 Aby uruchomić aplikację:"
echo ""
echo "   source .venv/bin/activate"
echo "   streamlit run app.py"
echo ""
echo "📌 Aplikacja uruchomi się pod: http://localhost:8501"
echo ""
