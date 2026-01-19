"""
Тесты для модуля agents.

Эти тесты проверяют базовую функциональность без реальных API вызовов.
Для интеграционных тестов с API используйте tests/test_integration.py
"""

from unittest.mock import patch, MagicMock
import pytest

import sys
sys.path.insert(0, "src")

from agents import Attacker, Defender, Attack, Defense
from config import ModelConfig


@pytest.fixture
def mock_api_client():
    """Mock get_client to avoid API key requirements in tests."""
    with patch("agents.get_client") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        yield mock_client


class TestAttackDataclass:
    """Тесты для dataclass Attack."""

    def test_attack_creation(self):
        attack = Attack(
            test_code="def test_foo(): pass",
            description="Test description",
            attack_type="edge_case",
        )

        assert attack.test_code == "def test_foo(): pass"
        assert attack.description == "Test description"
        assert attack.attack_type == "edge_case"

    def test_attack_equality(self):
        a1 = Attack("code", "desc", "type")
        a2 = Attack("code", "desc", "type")

        assert a1 == a2


class TestDefenseDataclass:
    """Тесты для dataclass Defense."""

    def test_defense_creation(self):
        defense = Defense(
            fixed_code="def foo(): pass",
            explanation="Fixed the bug",
        )

        assert defense.fixed_code == "def foo(): pass"
        assert defense.explanation == "Fixed the bug"


class TestAttackerParsing:
    """Тесты парсинга ответов Attacker."""

    def test_parse_attack_valid(self, mock_api_client):
        config = ModelConfig()
        attacker = Attacker(config)

        content = """
Here's an attack:

```python
# Attack type: edge_case
# Description: Test empty input

def test_empty():
    result = parse("")
    assert result is None
```

This should break the code.
"""

        attack = attacker._parse_attack(content)

        assert attack is not None
        assert "def test_empty" in attack.test_code
        assert attack.attack_type == "edge_case"
        assert "empty input" in attack.description.lower()

    def test_parse_attack_no_code_block(self, mock_api_client):
        config = ModelConfig()
        attacker = Attacker(config)

        content = "Just some text without code"
        attack = attacker._parse_attack(content)

        assert attack is None

    def test_parse_attack_missing_metadata(self, mock_api_client):
        config = ModelConfig()
        attacker = Attacker(config)

        content = """
```python
def test_something():
    pass
```
"""

        attack = attacker._parse_attack(content)

        assert attack is not None
        assert attack.attack_type == "unknown"
        assert attack.description == "No description"


class TestDefenderParsing:
    """Тесты парсинга ответов Defender."""

    def test_parse_defense_valid(self, mock_api_client):
        config = ModelConfig()
        defender = Defender(config)

        content = """
I fixed the code by adding input validation:

```python
def parse(text):
    if not text:
        return None
    return json.loads(text)
```

This handles empty input.
"""

        defense = defender._parse_defense(content)

        assert defense is not None
        assert "def parse" in defense.fixed_code
        assert "if not text" in defense.fixed_code
        assert "input validation" in defense.explanation.lower()

    def test_parse_defense_no_code_block(self, mock_api_client):
        config = ModelConfig()
        defender = Defender(config)

        content = "Cannot fix this code"
        defense = defender._parse_defense(content)

        assert defense is None


class TestAttackerWithMockedAPI:
    """Тесты Attacker с замоканным API."""

    @patch("agents.get_client")
    def test_generate_attack_success(self, mock_get_client):
        # Настраиваем mock
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = """
```python
# Attack type: injection
# Description: SQL injection test

def test_injection():
    parse("'; DROP TABLE users; --")
```
"""
        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client.chat.completions.create.return_value = mock_response

        # Тест
        config = ModelConfig()
        attacker = Attacker(config)

        attack = attacker.generate_attack(
            target_code="def parse(x): pass",
            previous_attacks=[],
            failed_attacks=[],
        )

        assert attack is not None
        assert attack.attack_type == "injection"
        assert "DROP TABLE" in attack.test_code

    @patch("agents.get_client")
    def test_generate_attack_api_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        config = ModelConfig()
        attacker = Attacker(config)

        attack = attacker.generate_attack(
            target_code="def parse(x): pass",
            previous_attacks=[],
            failed_attacks=[],
        )

        assert attack is None


class TestDefenderWithMockedAPI:
    """Тесты Defender с замоканным API."""

    @patch("agents.get_client")
    def test_generate_defense_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = """
```python
def parse(text):
    if not isinstance(text, str):
        raise TypeError("Expected string")
    return json.loads(text)
```
"""
        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client.chat.completions.create.return_value = mock_response

        config = ModelConfig()
        defender = Defender(config)

        attack = Attack("def test(): pass", "test", "edge_case")
        defense = defender.generate_defense(
            target_code="def parse(x): pass",
            failing_tests=[attack],
            previous_fixes=[],
        )

        assert defense is not None
        assert "isinstance" in defense.fixed_code
