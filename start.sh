#!/bin/bash
# start.sh — Умный запуск ACH с проверкой всего
#
# Использование:
#   ./start.sh              # Запуск в Docker (безопасно)
#   ./start.sh --local      # Локальный запуск (небезопасно!)
#   ./start.sh --check      # Только проверка зависимостей
#   ./start.sh --help       # Справка

set -e  # Останавливаться при ошибках

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции вывода
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; exit 1; }

# Справка
show_help() {
    cat << EOF
🚀 ACH (Adversarial Code Hardening) — Скрипт запуска

Использование:
    ./start.sh              Запуск в Docker (рекомендуется)
    ./start.sh --local      Локальный запуск (небезопасно!)
    ./start.sh --check      Только проверка зависимостей
    ./start.sh --setup      Первоначальная настройка
    ./start.sh --help       Эта справка

Переменные окружения:
    OPENAI_API_KEY          Ключ OpenAI (обязательно)
    OPENAI_BASE_URL         URL для DeepSeek (опционально)

Примеры:
    export OPENAI_API_KEY='sk-...'
    ./start.sh

    # Для DeepSeek:
    export OPENAI_API_KEY='ваш-deepseek-ключ'
    export OPENAI_BASE_URL='https://api.deepseek.com'
    ./start.sh

EOF
    exit 0
}

# Проверка Docker
check_docker() {
    info "Проверяю Docker..."
    
    if ! command -v docker &> /dev/null; then
        error "Docker не установлен!
        
Установка:
  macOS:   brew install docker
  Ubuntu:  sudo apt install docker.io docker-compose
  Windows: Скачай Docker Desktop с docker.com"
    fi
    
    if ! docker info &> /dev/null; then
        error "Docker не запущен! Запусти Docker Desktop или dockerd"
    fi
    
    success "Docker OK ($(docker --version | cut -d' ' -f3 | tr -d ','))"
}

# Проверка docker-compose
check_compose() {
    info "Проверяю docker-compose..."
    
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    elif docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        error "docker-compose не установлен!
        
Установка:
  Ubuntu: sudo apt install docker-compose
  Или:    pip install docker-compose"
    fi
    
    success "docker-compose OK"
}

# Проверка API ключа
check_api_key() {
    info "Проверяю API ключ..."
    
    if [ -n "$OPENROUTER_API_KEY" ]; then
        success "API ключ OK (OpenRouter)"
    elif [ -n "$NANOGPT_API_KEY" ]; then
        success "API ключ OK (NanoGPT)"
    elif [ -n "$OPENAI_API_KEY" ]; then
        success "API ключ OK (OpenAI)"
    else
        error "API ключ не задан!

OpenRouter (рекомендуется, есть бесплатные модели):
  1. Зарегистрируйся на https://openrouter.ai
  2. Получи ключ: https://openrouter.ai/keys
  3. export OPENROUTER_API_KEY='sk-or-...'

NanoGPT:
  export NANOGPT_API_KEY='...'

OpenAI:
  export OPENAI_API_KEY='sk-...'"
    fi
}

# Проверка структуры проекта
check_structure() {
    info "Проверяю структуру проекта..."
    
    local required_files=(
        "src/config.py"
        "src/agents.py"
        "src/fitness.py"
        "src/novelty.py"
        "examples/json_parser/target.py"
        "examples/json_parser/manual_loop.py"
        "Dockerfile"
        "docker-compose.yml"
        "requirements.txt"
    )
    
    local missing=()
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            missing+=("$file")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        error "Отсутствуют файлы:
$(printf '  - %s\n' "${missing[@]}")

Убедись что ты в корневой папке проекта"
    fi
    
    success "Структура проекта OK"
}

# Проверка Python (для локального запуска)
check_python() {
    info "Проверяю Python..."
    
    if ! command -v python3 &> /dev/null; then
        error "Python 3 не установлен!"
    fi
    
    local version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)
    
    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 10 ]); then
        error "Нужен Python 3.10+, у тебя $version"
    fi
    
    success "Python OK ($version)"
}

# Проверка зависимостей Python
check_python_deps() {
    info "Проверяю Python зависимости..."
    
    local missing=()
    
    python3 -c "import openai" 2>/dev/null || missing+=("openai")
    python3 -c "import pytest" 2>/dev/null || missing+=("pytest")
    
    if [ ${#missing[@]} -ne 0 ]; then
        warning "Отсутствуют пакеты: ${missing[*]}"
        info "Устанавливаю..."
        pip install -r requirements.txt
    fi
    
    success "Python зависимости OK"
}

# Сборка Docker образа
build_docker() {
    info "Собираю Docker образ..."
    
    if docker images | grep -q "^ach "; then
        info "Образ уже существует. Пересобрать? (y/N)"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            docker build -t ach .
        fi
    else
        docker build -t ach .
    fi
    
    success "Docker образ готов"
}

# Запуск в Docker
run_docker() {
    info "Запускаю в Docker (безопасно)..."
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    $COMPOSE_CMD run --rm ach
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    success "Завершено!"
    
    if [ -f "examples/json_parser/target_evolved.py" ]; then
        info "Проверь результат: cat examples/json_parser/target_evolved.py"
    fi
}

# Локальный запуск
run_local() {
    warning "ЛОКАЛЬНЫЙ ЗАПУСК — Код от LLM будет выполняться на твоей машине!"
    echo ""
    echo "Продолжить? (yes/NO)"
    read -r response
    
    if [[ "$response" != "yes" ]]; then
        info "Отменено. Используй Docker: ./start.sh"
        exit 0
    fi
    
    check_python
    check_python_deps
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    cd "$(dirname "$0")"
    python3 examples/json_parser/manual_loop.py
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Первоначальная настройка
setup() {
    info "Первоначальная настройка ACH"
    echo ""
    
    check_structure
    check_docker
    check_compose
    
    info "Собираю Docker образ..."
    docker build -t ach .
    
    echo ""
    success "Настройка завершена!"
    echo ""
    echo "Следующие шаги:"
    echo "  1. Получи API ключ (OpenAI или DeepSeek)"
    echo "  2. export OPENAI_API_KEY='твой-ключ'"
    echo "  3. ./start.sh"
    echo ""
}

# Только проверка
check_only() {
    echo ""
    echo "🔍 Проверка зависимостей ACH"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    check_structure
    check_docker
    check_compose
    check_api_key
    
    echo ""
    success "Всё готово к запуску!"
    echo ""
    echo "Запусти: ./start.sh"
    echo ""
}

# Главная логика
main() {
    echo ""
    echo "🔴🟢 ACH — Adversarial Code Hardening"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Переходим в директорию скрипта
    cd "$(dirname "$0")"
    
    case "${1:-}" in
        --help|-h)
            show_help
            ;;
        --check)
            check_only
            ;;
        --setup)
            setup
            ;;
        --local)
            check_structure
            check_api_key
            run_local
            ;;
        "")
            check_structure
            check_docker
            check_compose
            check_api_key
            build_docker
            run_docker
            ;;
        *)
            error "Неизвестный параметр: $1\nИспользуй --help для справки"
            ;;
    esac
}

main "$@"
