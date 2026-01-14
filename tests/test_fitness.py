"""
Тесты для модуля fitness.

Эти тесты реально запускают pytest, поэтому они интеграционные.
"""

import pytest

import sys
sys.path.insert(0, "src")

from fitness import FitnessEvaluator, FitnessResult
from agents import Attack


class TestFitnessResult:
    """Тесты для dataclass FitnessResult."""
    
    def test_creation(self):
        result = FitnessResult(
            score=0.75,
            passed=3,
            failed=1,
            errors=["Some error"],
            output="test output",
        )
        
        assert result.score == 0.75
        assert result.passed == 3
        assert result.failed == 1
        assert len(result.errors) == 1


class TestFitnessEvaluator:
    """Тесты для FitnessEvaluator."""
    
    def test_evaluate_attack_success(self):
        """Тест на код с багом — атака должна успешно его сломать."""
        evaluator = FitnessEvaluator()
        
        # Код с багом (деление на ноль)
        buggy_code = """
def divide(a, b):
    return a / b
"""
        
        # Атака: деление на ноль
        attack = Attack(
            test_code="""
def test_divide_by_zero():
    divide(10, 0)
""",
            description="Division by zero",
            attack_type="edge_case",
        )
        
        result = evaluator.evaluate_attack(buggy_code, attack)
        
        # Тест должен упасть (атака успешна)
        assert result.score == 1.0
        assert result.failed > 0 or result.errors
    
    def test_evaluate_attack_failure(self):
        """Тест на robust код — атака не должна сработать."""
        evaluator = FitnessEvaluator()
        
        # Код с защитой
        safe_code = """
def divide(a, b):
    if b == 0:
        return None
    return a / b
"""
        
        # Та же атака
        attack = Attack(
            test_code="""
def test_divide_by_zero():
    result = divide(10, 0)
    assert result is None
""",
            description="Division by zero",
            attack_type="edge_case",
        )
        
        result = evaluator.evaluate_attack(safe_code, attack)
        
        # Тест должен пройти (атака провалилась)
        assert result.score == 0.0
        assert result.passed > 0
    
    def test_evaluate_defense_all_pass(self):
        """Защита проходит все тесты."""
        evaluator = FitnessEvaluator()
        
        defended_code = """
def process(x):
    if x is None:
        return "null"
    if not isinstance(x, (int, float)):
        return "invalid"
    return str(x * 2)
"""
        
        attacks = [
            Attack(
                test_code="""
def test_none_input():
    result = process(None)
    assert result == "null"
""",
                description="None input",
                attack_type="edge_case",
            ),
            Attack(
                test_code="""
def test_string_input():
    result = process("hello")
    assert result == "invalid"
""",
                description="String input",
                attack_type="invalid_input",
            ),
            Attack(
                test_code="""
def test_normal():
    result = process(5)
    assert result == "10"
""",
                description="Normal input",
                attack_type="normal",
            ),
        ]
        
        result = evaluator.evaluate_defense(defended_code, attacks)
        
        assert result.score == 1.0
        assert result.passed == 3
        assert result.failed == 0
    
    def test_evaluate_defense_partial_pass(self):
        """Защита проходит только часть тестов."""
        evaluator = FitnessEvaluator()
        
        # Код с частичной защитой
        partial_code = """
def process(x):
    if x is None:
        return "null"
    # Нет проверки на string!
    return str(x * 2)
"""
        
        attacks = [
            Attack(
                test_code="""
def test_none():
    assert process(None) == "null"
""",
                description="None",
                attack_type="edge_case",
            ),
            Attack(
                test_code="""
def test_string():
    result = process("hello")
    assert result == "invalid"
""",
                description="String (will fail)",
                attack_type="invalid_input",
            ),
        ]
        
        result = evaluator.evaluate_defense(partial_code, attacks)
        
        # 1 из 2 тестов проходит
        assert result.score == 0.5
        assert result.passed == 1
        assert result.failed == 1
    
    def test_evaluate_defense_empty_attacks(self):
        """Нет атак — score = 1.0."""
        evaluator = FitnessEvaluator()
        
        result = evaluator.evaluate_defense("def foo(): pass", [])
        
        assert result.score == 1.0
    
    def test_timeout_handling(self):
        """Тест на timeout (infinite loop)."""
        evaluator = FitnessEvaluator(timeout=2)
        
        # Код с бесконечным циклом
        infinite_code = """
def hang():
    while True:
        pass
"""
        
        attack = Attack(
            test_code="""
def test_hang():
    hang()
""",
            description="Infinite loop",
            attack_type="overflow",
        )
        
        result = evaluator.evaluate_attack(infinite_code, attack)
        
        # Timeout = частичный успех атаки
        assert result.score == 0.5
        assert "Timeout" in result.errors


class TestPytestOutputParsing:
    """Тесты парсинга вывода pytest."""
    
    def test_parse_passed(self):
        evaluator = FitnessEvaluator()
        
        output = """
============================= test session starts ==============================
collected 3 items

test_foo.py ...                                                          [100%]

============================== 3 passed in 0.05s ===============================
"""
        
        passed, failed, errors = evaluator._parse_pytest_output(output)
        
        assert passed == 3
        assert failed == 0
    
    def test_parse_mixed(self):
        evaluator = FitnessEvaluator()
        
        output = """
============================= test session starts ==============================
collected 5 items

test_foo.py ..F.F                                                        [100%]

=========================== short test summary info ============================
FAILED test_foo.py::test_two
FAILED test_foo.py::test_four
========================= 3 passed, 2 failed in 0.10s =========================
"""
        
        passed, failed, errors = evaluator._parse_pytest_output(output)
        
        assert passed == 3
        assert failed == 2
    
    def test_parse_errors(self):
        evaluator = FitnessEvaluator()
        
        output = """
E       AssertionError: expected 5 but got 3
E       TypeError: unsupported operand
========================= 1 passed, 1 failed, 1 error in 0.05s =================
"""
        
        passed, failed, errors = evaluator._parse_pytest_output(output)
        
        assert "AssertionError" in errors[0] or len(errors) > 0
