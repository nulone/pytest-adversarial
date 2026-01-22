"""
Novelty Scoring — Предотвращение повторяющихся атак.

Проблема: Без дедупликации Attacker генерирует одни и те же атаки.
Это создаёт иллюзию прогресса без реального улучшения.

Решения:
1. Хэширование кода атаки (точные дубликаты)
2. Кластеризация по типу ошибки (семантические дубликаты)
3. Novelty score по coverage (новые пути выполнения)
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional
from collections import defaultdict

from .agents import Attack


@dataclass
class NoveltyResult:
    """Результат проверки новизны."""

    is_novel: bool
    novelty_score: float  # 0.0 - 1.0
    reason: str
    similar_to: Optional[str] = None  # ID похожей атаки


class NoveltyTracker:
    """
    Отслеживает новизну атак.

    Три уровня проверки:
    1. Exact duplicate (хэш кода)
    2. Semantic duplicate (тип ошибки + структура)
    3. Coverage novelty (какие строки кода затронуты)
    """

    def __init__(self):
        # Хэши всех виденных атак
        self.seen_hashes: set[str] = set()

        # Группировка по типу ошибки
        self.error_clusters: dict[str, list[str]] = defaultdict(list)

        # Счётчик атак по типу
        self.type_counts: dict[str, int] = defaultdict(int)

    def _hash_code(self, code: str) -> str:
        """Нормализует и хэширует код."""
        # Убираем комментарии и лишние пробелы
        normalized = re.sub(r"#.*", "", code)  # Убираем комментарии
        normalized = re.sub(r"\s+", " ", normalized)  # Нормализуем пробелы
        normalized = normalized.strip().lower()
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def _extract_error_signature(self, error_msg: str) -> str:
        """Извлекает сигнатуру ошибки для кластеризации."""
        if not error_msg:
            return "no_error"

        # Извлекаем тип исключения
        exception_match = re.search(r"(\w+Error|\w+Exception)", error_msg)
        exception_type = exception_match.group(1) if exception_match else "unknown"

        # Извлекаем ключевые слова
        keywords = []
        if "division by zero" in error_msg.lower():
            keywords.append("div_zero")
        if "index" in error_msg.lower():
            keywords.append("index")
        if "key" in error_msg.lower():
            keywords.append("key")
        if "type" in error_msg.lower():
            keywords.append("type")
        if "overflow" in error_msg.lower():
            keywords.append("overflow")
        if "recursion" in error_msg.lower():
            keywords.append("recursion")
        if "timeout" in error_msg.lower():
            keywords.append("timeout")

        return f"{exception_type}:{','.join(keywords) or 'generic'}"

    def check_novelty(
        self,
        attack: Attack,
        error_msg: str = "",
    ) -> NoveltyResult:
        """
        Проверяет новизну атаки.

        Returns:
            NoveltyResult с оценкой новизны
        """
        code_hash = self._hash_code(attack.test_code)

        # 1. Exact duplicate check
        if code_hash in self.seen_hashes:
            return NoveltyResult(
                is_novel=False,
                novelty_score=0.0,
                reason="exact_duplicate",
                similar_to=code_hash,
            )

        # 2. Semantic duplicate check (по типу ошибки)
        error_sig = self._extract_error_signature(error_msg)
        similar_count = len(self.error_clusters[error_sig])

        if similar_count >= 3:  # Уже 3+ атак с такой же ошибкой
            return NoveltyResult(
                is_novel=False,
                novelty_score=0.2,
                reason=f"semantic_duplicate: {similar_count} similar attacks",
                similar_to=error_sig,
            )

        # 3. Type saturation check
        type_count = self.type_counts[attack.attack_type]
        if type_count >= 5:  # Уже 5+ атак этого типа
            # Не отклоняем, но снижаем score
            novelty_score = max(0.3, 1.0 - (type_count * 0.1))
            return NoveltyResult(
                is_novel=True,
                novelty_score=novelty_score,
                reason=f"type_saturated: {type_count} attacks of type {attack.attack_type}",
            )

        # Новая атака!
        novelty_score = 1.0
        if similar_count > 0:
            novelty_score -= similar_count * 0.15

        return NoveltyResult(
            is_novel=True,
            novelty_score=max(0.5, novelty_score),
            reason="novel",
        )

    def register_attack(
        self,
        attack: Attack,
        error_msg: str = "",
    ) -> None:
        """Регистрирует атаку после успешной проверки."""
        code_hash = self._hash_code(attack.test_code)
        self.seen_hashes.add(code_hash)

        error_sig = self._extract_error_signature(error_msg)
        self.error_clusters[error_sig].append(code_hash)

        self.type_counts[attack.attack_type] += 1

    def get_stats(self) -> dict:
        """Возвращает статистику для отладки."""
        return {
            "total_attacks": len(self.seen_hashes),
            "unique_error_types": len(self.error_clusters),
            "attacks_by_type": dict(self.type_counts),
            "largest_cluster": max(
                (len(v) for v in self.error_clusters.values()), default=0
            ),
        }


class DefenseQualityChecker:
    """
    Проверяет качество защиты (не только "проходит тесты").

    Ловит паттерны "читерства":
    - try/except без обработки
    - return None/{}/"" на всё
    - Удаление функциональности
    """

    SUSPICIOUS_PATTERNS = [
        # Пустые except блоки
        (r"except.*:\s*pass", "empty_except", 0.3),
        (r"except.*:\s*return None", "swallow_to_none", 0.4),
        (r"except.*:\s*return \{\}", "swallow_to_empty", 0.4),
        (r'except.*:\s*return ""', "swallow_to_empty_str", 0.4),
        (r"except.*:\s*return \[\]", "swallow_to_empty_list", 0.4),
        # Широкие except без конкретного типа
        (r"except\s*:", "bare_except", 0.2),
        (r"except Exception:", "catch_all_exception", 0.1),
        # Подозрительные ранние return
        (r"if.*:\s*return None", "early_return_none", 0.1),
    ]

    def check_defense_quality(
        self,
        original_code: str,
        fixed_code: str,
    ) -> tuple[float, list[str]]:
        """
        Оценивает качество защиты.

        Returns:
            (penalty: 0.0-1.0, warnings: list of issues)
        """
        warnings = []
        total_penalty = 0.0

        # Проверяем подозрительные паттерны
        for pattern, name, penalty in self.SUSPICIOUS_PATTERNS:
            # Считаем сколько раз паттерн встречается В НОВОМ коде
            # но НЕ встречался в старом
            old_matches = len(re.findall(pattern, original_code))
            new_matches = len(re.findall(pattern, fixed_code))

            added = new_matches - old_matches
            if added > 0:
                warnings.append(f"{name}: +{added} occurrences")
                total_penalty += penalty * added

        # Проверяем не удалил ли Defender слишком много кода
        old_lines = len(original_code.strip().split("\n"))
        new_lines = len(fixed_code.strip().split("\n"))

        if new_lines < old_lines * 0.5:  # Удалил больше 50% кода
            warnings.append(f"code_reduction: {old_lines} -> {new_lines} lines")
            total_penalty += 0.5

        # Проверяем не добавил ли слишком много try/except
        old_try = len(re.findall(r"\btry\s*:", original_code))
        new_try = len(re.findall(r"\btry\s*:", fixed_code))

        if new_try > old_try + 3:  # Добавил больше 3 try блоков
            warnings.append(f"try_explosion: {old_try} -> {new_try}")
            total_penalty += 0.2

        return min(1.0, total_penalty), warnings


def demo():
    """Демонстрация работы novelty tracker."""
    tracker = NoveltyTracker()
    checker = DefenseQualityChecker()

    # Тестовые атаки
    attacks = [
        Attack("def test_1(): assert parse('')", "Empty input", "edge_case"),
        Attack(
            "def test_2(): assert parse('')", "Empty input again", "edge_case"
        ),  # Дубликат
        Attack("def test_3(): assert parse(None)", "None input", "edge_case"),
        Attack("def test_4(): assert parse(123)", "Wrong type", "invalid_input"),
    ]

    for attack in attacks:
        result = tracker.check_novelty(attack, "ValueError: invalid input")
        print(
            f"{attack.description}: novel={result.is_novel}, score={result.novelty_score:.2f}, reason={result.reason}"
        )
        if result.is_novel:
            tracker.register_attack(attack, "ValueError: invalid input")

    print("\nStats:", tracker.get_stats())

    # Тест качества защиты
    original = """
def parse(data):
    return json.loads(data)
"""

    bad_fix = """
def parse(data):
    try:
        return json.loads(data)
    except:
        pass
    except:
        return None
"""

    penalty, warnings = checker.check_defense_quality(original, bad_fix)
    print(f"\nDefense quality: penalty={penalty:.2f}")
    print(f"Warnings: {warnings}")


if __name__ == "__main__":
    demo()
