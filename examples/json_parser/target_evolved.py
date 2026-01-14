"""
Простой JSON parser — целевой код для ACH эксперимента.

ВНИМАНИЕ: Этот код НАМЕРЕННО содержит уязвимости для демонстрации.
Цель ACH — найти их и исправить автоматически.

Известные проблемы (для проверки что ACH их найдёт):
1. Нет обработки пустого ввода
2. Нет защиты от глубокой рекурсии
3. Нет валидации типов
4. Уязвимость к специальным символам
5. Нет обработки unicode
"""

import json
from typing import Any, Optional


def parse_json(text: str) -> Any:
    """
    Парсит JSON строку и возвращает Python объект.
    
    Args:
        text: JSON строка
        
    Returns:
        Распарсенный объект (dict, list, str, int, float, bool, None)
    """
    return json.loads(text)


def get_value(data: dict, key: str) -> Any:
    """
    Извлекает значение по ключу из словаря.
    
    Args:
        data: Словарь
        key: Ключ (поддерживает вложенность через точку: "a.b.c")
        
    Returns:
        Значение или None если не найдено
    """
    keys = key.split(".")
    current = data
    
    for k in keys:
        current = current[k]
    
    return current


def safe_get(data: dict, key: str, default: Any = None) -> Any:
    """
    Безопасно извлекает значение по ключу.
    
    Args:
        data: Словарь
        key: Ключ
        default: Значение по умолчанию
        
    Returns:
        Значение или default
    """
    try:
        return get_value(data, key)
    except:
        return default


def merge_dicts(a: dict, b: dict) -> dict:
    """
    Объединяет два словаря (b перезаписывает a).
    
    Args:
        a: Первый словарь
        b: Второй словарь
        
    Returns:
        Объединённый словарь
    """
    result = a.copy()
    result.update(b)
    return result


def flatten_json(data: dict, prefix: str = "") -> dict:
    """
    Разворачивает вложенный словарь в плоский.
    
    {"a": {"b": 1}} -> {"a.b": 1}
    """
    result = {}
    
    for key, value in data.items():
        new_key = f"{prefix}.{key}" if prefix else key
        
        if isinstance(value, dict):
            result.update(flatten_json(value, new_key))
        else:
            result[new_key] = value
    
    return result


def validate_schema(data: dict, schema: dict) -> bool:
    """
    Проверяет соответствие данных схеме.
    
    Schema format:
        {"field": "type", "nested": {"field": "type"}}
    
    Types: "str", "int", "float", "bool", "list", "dict"
    """
    TYPE_MAP = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
    }
    
    for key, expected_type in schema.items():
        if key not in data:
            return False
        
        if isinstance(expected_type, dict):
            if not validate_schema(data[key], expected_type):
                return False
        else:
            if not isinstance(data[key], TYPE_MAP[expected_type]):
                return False
    
    return True
