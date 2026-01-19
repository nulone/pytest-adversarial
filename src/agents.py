"""
Agents: Attacker и Defender для adversarial code hardening.

Поддерживает: OpenRouter, NanoGPT, OpenAI
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from config import ModelConfig, get_api_config
from utils import extract_functions

logger = logging.getLogger(__name__)


def get_client(config: ModelConfig) -> OpenAI:
    """Создаёт клиент для API."""

    api_config = get_api_config()

    if not api_config:
        raise ValueError(
            "API ключ не задан!\n\n"
            "OpenRouter (рекомендуется):\n"
            "  export OPENROUTER_API_KEY='ваш-ключ'\n"
            "  Получить: https://openrouter.ai/keys\n\n"
            "NanoGPT:\n"
            "  export NANOGPT_API_KEY='ваш-ключ'\n"
            "  Получить: https://nano-gpt.com\n\n"
            "OpenAI:\n"
            "  export OPENAI_API_KEY='sk-...'\n"
        )

    return OpenAI(
        api_key=api_config["api_key"],
        base_url=api_config["base_url"],
        timeout=config.timeout,
    )


@dataclass
class Attack:
    """Результат работы Attacker'а."""
    test_code: str
    description: str
    attack_type: str


@dataclass
class Defense:
    """Результат работы Defender'а."""
    fixed_code: str
    explanation: str


class Attacker:
    """Генерирует тесты/edge cases, которые ломают код."""

    SYSTEM_PROMPT = """You are an elite adversarial security researcher. Find bugs that others miss.

IMPORTANT: You must find NEW and DIFFERENT vulnerabilities each time. Do not repeat attacks!

Attack categories (USE ALL OF THEM, not just edge_case):
1. edge_case: empty string "", None, [], {}
2. invalid_input: wrong types (int instead of str, list instead of dict)
3. overflow: deep recursion, huge numbers (10**1000), very long strings (10000 chars)
4. injection: control characters (\x00, \n, \r), unicode exploits, escape sequences
5. boundary: MAX_INT, MIN_INT, float('inf'), float('nan')
6. concurrency: (if applicable) race conditions
7. resource: memory exhaustion, CPU exhaustion

CRITICAL RULES:
1. DO NOT use pytest.raises() - let the code CRASH
2. DO NOT use try/except - let exceptions propagate
3. Each test must call a REAL function from target code
4. Target has MULTIPLE functions - attack different ones:
   - parse_json(text) - JSON parsing
   - get_value(data, key) - dict access with dot notation
   - safe_get(data, key, default) - safe dict access
   - merge_dicts(a, b) - merge two dicts
   - flatten_json(data, prefix) - flatten nested dict
   - validate_schema(data, schema) - schema validation

VARIETY IS KEY: If previous attacks used parse_json, try get_value or flatten_json!

Example attacks on DIFFERENT functions:
```python
# Attack on get_value with deep nesting
def test_get_value_overflow():
    from target import get_value
    deep = {"a": {"b": {"c": "x"}} * 1000}  # Very deep
    result = get_value(deep, "a.b.c.d.e.f.g.h")  # Deep key access

# Attack on flatten_json with circular reference attempt
def test_flatten_circular():
    from target import flatten_json
    data = {}
    data["self"] = data  # This will crash!
    flatten_json(data)

# Attack on validate_schema with invalid schema
def test_validate_invalid_schema():
    from target import validate_schema
    validate_schema({"a": 1}, {"a": "invalid_type"})  # Unknown type
```

Generate ONE creative attack that is DIFFERENT from previous attempts."""

    MUTATION_PROMPT = """You are mutating a successful attack to create a variant.

ORIGINAL ATTACK (this worked!):
```python
{original_code}
```

Error it caused: {error}

Create a MUTATION - keep the core idea but change ONE thing:
- Different input values (but same attack vector)
- Same input, target a different function
- Make it more extreme (deeper recursion, longer string, etc.)

The mutation should still crash the code but in a slightly different way.

Output the mutated test in ```python``` block."""

    CROSSOVER_PROMPT = """Combine two successful attacks into one stronger attack.

ATTACK 1 ({type1}):
```python
{code1}
```

ATTACK 2 ({type2}):
```python
{code2}
```

Create ONE NEW attack that combines their strategies.

Output the combined test in ```python``` block."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = get_client(config)

    def mutate_attack(self, successful_attack: Attack) -> Optional[Attack]:
        """Мутирует успешную атаку для создания варианта."""

        prompt = self.MUTATION_PROMPT.format(
            original_code=successful_attack.test_code,
            error=successful_attack.description[:200] if successful_attack.description else "Unknown"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.config.attacker_model,
                messages=[
                    {"role": "system", "content": "You evolve attacks through mutation."},
                    {"role": "user", "content": prompt},
                ],
                temperature=1.0,
                max_tokens=self.config.max_tokens,
            )

            content = response.choices[0].message.content
            attack = self._parse_attack(content)

            if attack:
                attack.attack_type = successful_attack.attack_type + "_mut"
                attack.description = f"Mutated: {successful_attack.description[:50]}"

            return attack

        except Exception as e:
            logger.warning(f"Mutation failed: {e}")
            return None

    def crossover_attacks(self, attack1: Attack, attack2: Attack) -> Optional[Attack]:
        """Скрещивает две успешные атаки."""

        prompt = self.CROSSOVER_PROMPT.format(
            type1=attack1.attack_type,
            code1=attack1.test_code,
            type2=attack2.attack_type,
            code2=attack2.test_code,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.config.attacker_model,
                messages=[
                    {"role": "system", "content": "You combine attack strategies."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_tokens=self.config.max_tokens,
            )

            content = response.choices[0].message.content
            attack = self._parse_attack(content)

            if attack:
                attack.attack_type = f"{attack1.attack_type}+{attack2.attack_type}"
                attack.description = "Crossover"

            return attack

        except Exception as e:
            logger.warning(f"Crossover failed: {e}")
            return None

    def generate_attack(
        self,
        target_code: str,
        previous_attacks: list[Attack],
        failed_attacks: list[Attack],
    ) -> Optional[Attack]:
        """Генерирует атаку."""

        # Extract available functions from target code
        available_functions = extract_functions(target_code)

        prompt = f"Target code:\n```python\n{target_code}\n```\n\n"

        if available_functions:
            prompt += f"Attack ONLY these functions: {available_functions}\n\n"

        if previous_attacks:
            # Группируем по типам
            by_type = {}
            by_function = {}
            for a in previous_attacks:
                by_type[a.attack_type] = by_type.get(a.attack_type, 0) + 1
                # Пытаемся определить функцию
                for func in available_functions:
                    if func in a.test_code:
                        by_function[func] = by_function.get(func, 0) + 1

            prompt += "⚠️ ALREADY TRIED (find something DIFFERENT!):\n"
            prompt += f"Attack types used: {dict(by_type)}\n"
            prompt += f"Functions attacked: {dict(by_function)}\n"

            # Показываем последние атаки
            prompt += "\nRecent attacks:\n"
            for a in previous_attacks[-5:]:
                prompt += f"- [{a.attack_type}] {a.description[:60]}...\n"

            # Подсказка что ещё не пробовали
            untried_types = set(["edge_case", "invalid_input", "overflow", "injection", "boundary"]) - set(by_type.keys())
            untried_funcs = set(available_functions) - set(by_function.keys())

            if untried_types:
                prompt += f"\n💡 HINT: Try these attack types: {untried_types}\n"
            if untried_funcs:
                prompt += f"💡 HINT: Try attacking these functions: {untried_funcs}\n"

            prompt += "\n"

        prompt += "Generate a NEW and DIFFERENT attack:"

        try:
            response = self.client.chat.completions.create(
                model=self.config.attacker_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.config.attacker_temperature,
                max_tokens=self.config.max_tokens,
            )

            content = response.choices[0].message.content
            return self._parse_attack(content)

        except Exception as e:
            error_msg = str(e)
            # Retry on transient errors
            if "401" in error_msg or "429" in error_msg or "500" in error_msg:
                logger.warning(f"API error (will retry): {error_msg[:100]}")
                import time
                time.sleep(2)
                try:
                    response = self.client.chat.completions.create(
                        model=self.config.attacker_model,
                        messages=[
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=self.config.attacker_temperature,
                        max_tokens=self.config.max_tokens,
                    )
                    content = response.choices[0].message.content
                    return self._parse_attack(content)
                except Exception as e2:
                    logger.error(f"Attacker retry failed: {e2}")
                    return None
            logger.error(f"Attacker failed: {e}")
            return None

    def _parse_attack(self, content: str) -> Optional[Attack]:
        """Парсит ответ. Работает с разными форматами от разных моделей."""

        # DEBUG: показываем что получили от LLM
        logger.debug(f"Attacker response: {content[:500]}")

        # Ищем код
        code_match = re.search(r"```python\n(.*?)```", content, re.DOTALL)
        if not code_match:
            code_match = re.search(r"```\n(.*?)```", content, re.DOTALL)
        if not code_match:
            logger.warning(f"No code block found. Response starts with: {content[:200]}")
            return None

        test_code = code_match.group(1).strip()

        if "def test" not in test_code:
            logger.warning(f"No test function found in: {test_code[:200]}")
            return None

        # Тип атаки - пробуем разные способы
        attack_type = "unknown"

        # Способ 1: Attack type: <type>
        type_match = re.search(r"Attack type:\s*(\w+)", content, re.IGNORECASE)
        if type_match:
            attack_type = type_match.group(1).lower()

        # Способ 2: # Attack on <function> with <type>
        if attack_type == "unknown":
            type_match = re.search(r"#\s*Attack.*?(edge.?case|invalid.?input|overflow|injection|boundary|resource)", content, re.IGNORECASE)
            if type_match:
                attack_type = type_match.group(1).lower().replace(" ", "_").replace("-", "_")

        # Способ 3: Определяем по имени теста
        if attack_type == "unknown":
            func_match = re.search(r"def test_\w+_(edge|invalid|overflow|injection|boundary|empty|none|null)", test_code, re.IGNORECASE)
            if func_match:
                keyword = func_match.group(1).lower()
                type_map = {
                    "edge": "edge_case", "empty": "edge_case", "none": "edge_case", "null": "edge_case",
                    "invalid": "invalid_input",
                    "overflow": "overflow",
                    "injection": "injection",
                    "boundary": "boundary",
                }
                attack_type = type_map.get(keyword, "unknown")

        # Способ 4: Определяем по содержимому теста
        if attack_type == "unknown":
            test_lower = test_code.lower()
            if "none" in test_lower or "empty" in test_lower or '""' in test_code or "''" in test_code or "{}" in test_code:
                attack_type = "edge_case"
            elif "recursion" in test_lower or "depth" in test_lower or "10**" in test_code or "1000000" in test_code:
                attack_type = "overflow"
            elif "\\x" in test_code or "\\n" in test_code or "\\0" in test_code or "unicode" in test_lower:
                attack_type = "injection"
            elif "inf" in test_lower or "nan" in test_lower or "max_int" in test_lower:
                attack_type = "boundary"
            elif "str(" in test_code or "int(" in test_code or "isinstance" in test_lower:
                attack_type = "invalid_input"

        # Описание - пробуем разные способы
        description = "No description"

        # Способ 1: Description: <text>
        desc_match = re.search(r"Description:\s*(.+)", content, re.IGNORECASE)
        if desc_match:
            description = desc_match.group(1).strip()[:100]

        # Способ 2: Первый комментарий в коде
        if description == "No description":
            comment_match = re.search(r"#\s*(.+)", test_code)
            if comment_match:
                description = comment_match.group(1).strip()[:100]

        # Способ 3: Текст перед кодом
        if description == "No description":
            before_code = content.split("```")[0].strip()
            if before_code and len(before_code) > 10:
                # Берём последнее предложение перед кодом
                sentences = before_code.split(".")
                for s in reversed(sentences):
                    if len(s.strip()) > 10:
                        description = s.strip()[:100]
                        break

        return Attack(test_code=test_code, description=description, attack_type=attack_type)


class Defender:
    """Исправляет код."""

    SYSTEM_PROMPT = """You are a senior security engineer. Make the code BULLETPROOF.

Your job: Fix ALL vulnerabilities while keeping original functionality.

DEFENSE STRATEGIES (use multiple):

1. INPUT VALIDATION (at function start):
   - Check types: isinstance(x, str)
   - Check values: if not x or len(x) > MAX_SIZE
   - Raise ValueError/TypeError with clear messages

2. RECURSION PROTECTION:
   - Add max_depth parameter with default
   - Track current depth, raise if exceeded
   - Example: if depth > 100: raise RecursionError("Max depth exceeded")

3. JSON SAFETY:
   - Wrap json.loads in try/except JSONDecodeError
   - Return None or raise ValueError on invalid JSON

4. DICT ACCESS SAFETY:
   - Use .get() instead of []
   - Check key exists before access
   - Handle None values

5. RESOURCE LIMITS:
   - Limit string length: if len(s) > 10000: raise ValueError
   - Limit recursion depth
   - Limit dict depth for flattening

CRITICAL RULES:
1. Keep original function signatures
2. Original functionality MUST still work (sanity tests must pass)
3. Add validation at the START of each function
4. Use specific exceptions (ValueError, TypeError), not bare Exception
5. Include helpful error messages

Output format:
```python
# Complete fixed code for ALL functions
```

Then briefly explain each fix."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = get_client(config)

    def generate_defense(
        self,
        target_code: str,
        failing_tests: list[Attack],
        previous_fixes: list[str],
    ) -> Optional[Defense]:
        """Генерирует фикс."""

        prompt = f"Current code:\n```python\n{target_code}\n```\n\n"
        prompt += "Failing test:\n```python\n"
        prompt += failing_tests[0].test_code if failing_tests else ""
        prompt += "\n```\n\nFix the code:"

        try:
            response = self.client.chat.completions.create(
                model=self.config.defender_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.config.defender_temperature,
                max_tokens=self.config.max_tokens,
            )

            content = response.choices[0].message.content
            return self._parse_defense(content)

        except Exception as e:
            logger.error(f"Defender failed: {e}")
            return None

    def _parse_defense(self, content: str) -> Optional[Defense]:
        """Парсит ответ."""

        code_match = re.search(r"```python\n(.*?)```", content, re.DOTALL)
        if not code_match:
            code_match = re.search(r"```\n(.*?)```", content, re.DOTALL)
        if not code_match:
            logger.warning("No code block found in defender response")
            return None

        fixed_code = code_match.group(1).strip()
        explanation = re.sub(r"```.*?```", "", content, flags=re.DOTALL).strip()[:300]

        return Defense(fixed_code=fixed_code, explanation=explanation)
