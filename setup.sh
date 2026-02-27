#!/bin/bash
# Skrypt instalacji dla macOS / Linux

set -e  # Exit on error

echo "================================================"
echo "🚀 Raport Czasu Pracy - Setup dla macOS/Linux"
echo "================================================"

# Check Python
echo ""
echo "1️⃣ Sprawdzam Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 nie znaleziony. Zainstaluj Python 3.10+ i spróbuj ponownie."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python: $PYTHON_VERSION"

# Create venv
echo ""
echo "2️⃣ Tworzę wirtualne środowisko..."
if [ -d ".venv" ]; then
    echo "⚠️  Folder .venv już istnieje. Usuwam..."
    rm -rf .venv
fi

python3 -m venv .venv
echo "✅ Środowisko wirtualne utworzone"

# Activate venv
echo ""
echo "3️⃣ Aktywuję środowisko..."
source .venv/bin/activate
echo "✅ Środowisko aktywne"

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
python3 -c "import streamlit, pandas, plotly, openpyxl; print('✅ Wszystko OK!')" 2>/dev/null || {
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
