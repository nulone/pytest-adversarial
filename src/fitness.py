"""
Fitness Function для оценки атак и защит.

Fitness атаки = насколько сильно она ломает код:
- 1.0 = тест падает (атака успешна)
- 0.5 = тест вызывает warning/edge behavior
- 0.0 = тест проходит (атака провалилась)

Fitness защиты = сколько тестов проходит:
- 1.0 = все тесты проходят
- 0.0 = ни один тест не проходит

ВАЖНО: Sanity Tests
Defender может "сливать" — просто return None на всё.
Поэтому есть sanity_tests которые ДОЛЖНЫ проходить всегда.
Если sanity tests падают → fitness = 0 независимо от атак.
"""

import logging
import os
import subprocess
import tempfile
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agents import Attack

logger = logging.getLogger(__name__)


@dataclass
class FitnessResult:
    """Результат оценки."""

    score: float  # 0.0 - 1.0
    passed: int  # Сколько тестов прошло
    failed: int  # Сколько упало
    errors: list[str]  # Сообщения об ошибках
    output: str  # Полный вывод pytest


class FitnessEvaluator:
    """
    Оценивает код через запуск pytest.

    Работает так:
    1. Создаёт временную директорию
    2. Копирует туда целевой код
    3. Создаёт файл с тестами
    4. Запускает pytest
    5. Парсит результат
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def evaluate_attack(
        self,
        target_code: str,
        attack: Attack,
    ) -> FitnessResult:
        """
        Оценивает атаку против кода.

        Fitness = 1.0 если тест падает (атака успешна).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Записываем целевой код
            target_file = tmppath / "target.py"
            target_file.write_text(target_code)

            # Записываем тест
            test_file = tmppath / "test_attack.py"
            test_content = f"""
import sys
import pytest
sys.path.insert(0, '{tmpdir}')
from target import *

{attack.test_code}
"""
            test_file.write_text(test_content)

            # Запускаем pytest
            result = self._run_pytest(tmppath)

            # Для атаки: успех = тест падает
            if result.failed > 0:
                result.score = 1.0
            elif result.errors:
                result.score = 0.8  # Ошибка импорта и т.п. — частичный успех
            else:
                result.score = 0.0  # Тест прошёл — атака не сработала

            return result

    def evaluate_defense(
        self,
        defended_code: str,
        attacks: list[Attack],
        sanity_tests: Optional[str] = None,
    ) -> FitnessResult:
        """
        Оценивает защищённый код против всех атак.

        Fitness = доля пройденных тестов.

        ВАЖНО: Если sanity_tests заданы и падают → fitness = 0.
        Это защита от "сливающего" Defender который просто return None.
        """
        if not attacks:
            return FitnessResult(score=1.0, passed=0, failed=0, errors=[], output="")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Записываем защищённый код
            target_file = tmppath / "target.py"
            target_file.write_text(defended_code)

            # Записываем все тесты
            test_content = f"""
import sys
import pytest
sys.path.insert(0, '{tmpdir}')
from target import *

"""
            for i, attack in enumerate(attacks):
                # Переименовываем функции чтобы не конфликтовали
                renamed_test = attack.test_code.replace("def test_", f"def test_{i}_")
                test_content += (
                    f"\n# Attack {i}: {attack.description}\n{renamed_test}\n"
                )

            test_file = tmppath / "test_defense.py"
            test_file.write_text(test_content)

            # Запускаем pytest
            result = self._run_pytest(tmppath)

            # Для защиты: успех = тесты проходят
            total = result.passed + result.failed
            if total > 0:
                result.score = result.passed / total
            else:
                result.score = 0.0

            # SANITY CHECK: Если есть sanity_tests, они должны проходить
            if sanity_tests and result.score > 0:
                sanity_file = tmppath / "test_sanity.py"
                sanity_content = f"""
import sys
import pytest
sys.path.insert(0, '{tmpdir}')
from target import *

{sanity_tests}
"""
                sanity_file.write_text(sanity_content)
                sanity_result = self._run_pytest(tmppath, test_file="test_sanity.py")

                if sanity_result.failed > 0:
                    logger.warning(
                        "Sanity tests failed! Defender is gaming the system."
                    )
                    result.score = 0.0
                    result.errors.append("SANITY_FAILED: Original functionality broken")

            return result

    def _run_pytest(
        self, test_dir: Path, test_file: Optional[str] = None
    ) -> FitnessResult:
        """
        Запускает pytest и парсит результат.

        БЕЗОПАСНОСТЬ: Ограничиваем ресурсы и время.
        TODO: Для продакшена использовать Docker/nsjail.
        """
        try:
            test_path = str(test_dir / test_file) if test_file else str(test_dir)

            # Безопасные ограничения
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"  # Не создавать .pyc

            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=test_dir,
            )

            output = proc.stdout + proc.stderr

            # Парсим результат
            passed, failed, errors = self._parse_pytest_output(output)

            return FitnessResult(
                score=0.0,  # Будет установлен вызывающим кодом
                passed=passed,
                failed=failed,
                errors=errors,
                output=output,
            )

        except subprocess.TimeoutExpired:
            logger.warning("Pytest timeout")
            return FitnessResult(
                score=0.5,  # Timeout = partial success для атаки
                passed=0,
                failed=0,
                errors=["Timeout"],
                output="Test execution timed out",
            )
        except Exception as e:
            logger.error(f"Pytest error: {e}")
            return FitnessResult(
                score=0.0,
                passed=0,
                failed=0,
                errors=[str(e)],
                output=str(e),
            )

    def _parse_pytest_output(self, output: str) -> tuple[int, int, list[str]]:
        """Парсит вывод pytest."""
        import re

        passed = 0
        failed = 0
        errors = []

        # Ищем summary line: "1 passed, 2 failed"
        re.search(
            r"(\d+) passed|(\d+) failed|(\d+) error",
            output,
        )

        # Считаем passed
        passed_match = re.search(r"(\d+) passed", output)
        if passed_match:
            passed = int(passed_match.group(1))

        # Считаем failed
        failed_match = re.search(r"(\d+) failed", output)
        if failed_match:
            failed = int(failed_match.group(1))

        # Считаем errors
        error_match = re.search(r"(\d+) error", output)
        if error_match:
            errors.append(f"{error_match.group(1)} errors")

        # Извлекаем сообщения об ошибках
        error_lines = re.findall(r"E\s+(.+)", output)
        errors.extend(error_lines[:5])  # Макс 5 ошибок

        return passed, failed, errors


def quick_test():
    """Быстрый тест fitness evaluator."""
    evaluator = FitnessEvaluator()

    # Простой код с багом
    buggy_code = """
def divide(a, b):
    return a / b
"""

    # Атака: деление на ноль
    attack = Attack(
        test_code="""
def test_divide_by_zero():
    result = divide(10, 0)
    assert result is not None
""",
        description="Division by zero",
        attack_type="edge_case",
    )

    result = evaluator.evaluate_attack(buggy_code, attack)
    print(f"Attack fitness: {result.score}")
    print(f"Passed: {result.passed}, Failed: {result.failed}")
    print(f"Output: {result.output[:500]}")


if __name__ == "__main__":
    quick_test()
