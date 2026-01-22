#!/bin/bash
# check_results.sh — Анализ результатов после запуска ACH
#
# Использование:
#   ./check_results.sh

set -e

# Цвета
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

cd "$(dirname "$0")"

echo ""
echo -e "${CYAN}📊 Анализ результатов ACH${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Проверяем существование файлов
ORIGINAL="examples/json_parser/target.py"
EVOLVED="examples/json_parser/target_evolved.py"

if [ ! -f "$EVOLVED" ]; then
    echo -e "${YELLOW}⚠️  Файл target_evolved.py не найден${NC}"
    echo "   Сначала запусти: ./start.sh"
    exit 1
fi

# Статистика файлов
echo -e "${BLUE}📁 Статистика файлов:${NC}"
echo ""

orig_lines=$(wc -l < "$ORIGINAL")
evol_lines=$(wc -l < "$EVOLVED")
diff_lines=$((evol_lines - orig_lines))

echo "   Оригинал:    $orig_lines строк"
echo "   После ACH:   $evol_lines строк (+$diff_lines)"
echo ""

# Подсчёт защитных конструкций
echo -e "${BLUE}🛡️  Защитные конструкции:${NC}"
echo ""

count_pattern() {
    local file=$1
    local pattern=$2
    grep -c "$pattern" "$file" 2>/dev/null || echo "0"
}

orig_try=$(count_pattern "$ORIGINAL" "try:")
evol_try=$(count_pattern "$EVOLVED" "try:")
orig_if=$(count_pattern "$ORIGINAL" "if ")
evol_if=$(count_pattern "$EVOLVED" "if ")
orig_raise=$(count_pattern "$ORIGINAL" "raise ")
evol_raise=$(count_pattern "$EVOLVED" "raise ")
orig_isinstance=$(count_pattern "$ORIGINAL" "isinstance")
evol_isinstance=$(count_pattern "$EVOLVED" "isinstance")

printf "   %-20s %5s → %s\n" "try/except:" "$orig_try" "$evol_try"
printf "   %-20s %5s → %s\n" "if проверки:" "$orig_if" "$evol_if"
printf "   %-20s %5s → %s\n" "raise исключений:" "$orig_raise" "$evol_raise"
printf "   %-20s %5s → %s\n" "isinstance():" "$orig_isinstance" "$evol_isinstance"
echo ""

# Показываем diff
echo -e "${BLUE}📝 Изменения (diff):${NC}"
echo ""

if command -v colordiff &> /dev/null; then
    diff -u "$ORIGINAL" "$EVOLVED" | colordiff | head -50
else
    diff -u "$ORIGINAL" "$EVOLVED" | head -50
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Оценка результата
echo -e "${BLUE}🎯 Оценка результата:${NC}"
echo ""

score=0
feedback=""

if [ "$evol_try" -gt "$orig_try" ]; then
    score=$((score + 25))
    feedback+="   ✅ Добавлена обработка исключений\n"
else
    feedback+="   ⚪ try/except не изменились\n"
fi

if [ "$evol_if" -gt "$orig_if" ]; then
    score=$((score + 25))
    feedback+="   ✅ Добавлены проверки условий\n"
else
    feedback+="   ⚪ if проверки не изменились\n"
fi

if [ "$evol_isinstance" -gt "$orig_isinstance" ]; then
    score=$((score + 25))
    feedback+="   ✅ Добавлена валидация типов\n"
else
    feedback+="   ⚪ Валидация типов не добавлена\n"
fi

if [ "$evol_raise" -gt "$orig_raise" ]; then
    score=$((score + 25))
    feedback+="   ✅ Добавлены информативные исключения\n"
else
    feedback+="   ⚪ Исключения не добавлены\n"
fi

echo -e "$feedback"
echo ""

if [ $score -ge 75 ]; then
    echo -e "${GREEN}🎉 Отличный результат! ($score/100)${NC}"
    echo "   Код значительно улучшился. Можно автоматизировать."
elif [ $score -ge 50 ]; then
    echo -e "${YELLOW}👍 Хороший результат ($score/100)${NC}"
    echo "   Код улучшился. Попробуй ещё несколько раундов."
elif [ $score -ge 25 ]; then
    echo -e "${YELLOW}🤔 Средний результат ($score/100)${NC}"
    echo "   Есть улучшения, но можно лучше. Проверь промпты."
else
    echo -e "${YELLOW}⚠️  Слабый результат ($score/100)${NC}"
    echo "   Код почти не изменился. Проверь:"
    echo "   - Работает ли API?"
    echo "   - Правильные ли промпты в src/agents.py?"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Полный diff:  diff -u $ORIGINAL $EVOLVED"
echo "Оригинал:     cat $ORIGINAL"
echo "Результат:    cat $EVOLVED"
echo ""
