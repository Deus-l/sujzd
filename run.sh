#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="$VENV_DIR/bin/python3"
PIP="$VENV_DIR/bin/pip"
UVICORN="$VENV_DIR/bin/uvicorn"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8877}"

# OpenRouter API (бесплатно, рекомендуется): https://openrouter.ai → Keys → Create Key
# Передайте ключ через env: OPENROUTER_API_KEY=sk-or-... ./run.sh
export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

# Groq API (бесплатно): https://console.groq.com → API Keys
export GROQ_API_KEY="${GROQ_API_KEY:-}"

# ModelGate API (российский агрегатор): https://modelgate.ru
export MODELGATE_API_KEY="${MODELGATE_API_KEY:-}"

# Hugging Face токен (опционально, если используется HF provider)
export HF_TOKEN="${HF_TOKEN:-}"

# Освобождаем порт если занят
PIDS=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    echo "  Порт $PORT занят (PID: $PIDS) — завершаю..."
    echo "$PIDS" | xargs kill -9 2>/dev/null || true
    sleep 0.5
fi

# Проверяем venv
if [ ! -f "$PYTHON" ]; then
    echo "Виртуальное окружение не найдено. Создаю..."
    python3 -m venv "$VENV_DIR"
fi

# Проверяем, что shebang в uvicorn указывает на правильный Python
if [ -f "$VENV_DIR/bin/uvicorn" ]; then
    SHEBANG_PYTHON=$(head -1 "$VENV_DIR/bin/uvicorn" | sed 's|#!||')
    if [ ! -f "$SHEBANG_PYTHON" ]; then
        echo "Окружение содержит битые пути (папка была переименована). Пересоздаю..."
        rm -rf "$VENV_DIR"
        python3 -m venv "$VENV_DIR"
    fi
fi

# Устанавливаем зависимости, если нужно
if ! "$VENV_DIR/bin/python3" -c "import fastapi, uvicorn, sqlalchemy" 2>/dev/null; then
    echo "Устанавливаю зависимости..."
    "$PIP" install -r requirements.txt
fi

echo ""
echo "  СУЖЦД запускается..."
echo "  URL: http://localhost:$PORT"
echo "  API: http://localhost:$PORT/api/docs"
echo "  Остановить: Ctrl+C"
echo ""

"$UVICORN" main:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload
