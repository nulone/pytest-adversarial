import json
from typing import Any, Optional

MAX_SIZE = 10000
MAX_DEPTH = 100

def parse_json(text: str) -> Any:
    """
    Парсит JSON строку и возвращает Python объект.
    
    Args:
        text: JSON строка
        
    Returns:
        Распарсенный объект (dict, list, str, int, float, bool, None)
    """
    if not isinstance(text, str):
        raise TypeError("Input must be a string.")
    if not text or len(text) > MAX_SIZE:
        raise ValueError(f"Input cannot be empty and must not exceed {MAX_SIZE} characters.")
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON input.")

def get_value(data: dict, key: str, depth: int = 0) -> Any:
    """
    Извлекает значение по ключу из словаря.
    
    Args:
        data: Словарь
        key: Ключ (поддерживает вложенность через точку: "a.b.c")
        
    Returns:
        Значение или None если не найдено
    """
    if not isinstance(data, dict):
        raise TypeError("Data must be a dictionary.")
    if not isinstance(key, str):
        raise TypeError("Key must be a string.")
    if depth > MAX_DEPTH:
        raise RecursionError("Max depth exceeded in get_value.")
    
    keys = key.split(".")
    current = data
    
    for k in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(k)
    
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
    except (TypeError, RecursionError):
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
    if not isinstance(a, dict):
        raise TypeError("First argument must be a dictionary.")
    if not isinstance(b, dict):
        raise TypeError("Second argument must be a dictionary.")
    
    result = a.copy()
    result.update(b)
    return result

def flatten_json(data: dict, prefix: str = "", depth: int = 0) -> dict:
    """
    Разворачивает вложенный словарь в плоский.
    
    {"a": {"b": 1}} -> {"a.b": 1}
    """
    if not isinstance(data, dict):
        raise TypeError("Data must be a dictionary.")
    if depth > MAX_DEPTH:
        raise RecursionError("Max depth exceeded in flatten_json.")
    
    result = {}
    
    for key, value in data.items():
        new_key = f"{prefix}.{key}" if prefix else key
        
        if isinstance(value, dict):
            result.update(flatten_json(value, new_key, depth + 1))
        else:
            result[new_key] = value
    
    return result

def validate_schema(data: dict, schema: dict, depth: int = 0) -> bool:
    """
    Проверяет соответствие данных схеме.
    
    Schema format:
        {"field": "type", "nested": {"field": "type"}}
    
    Types: "str", "int", "float", "bool", "list", "dict"
    """
    if not isinstance(data, dict) or not isinstance(schema, dict):
        raise TypeError("Both data and schema must be dictionaries.")
    if depth > MAX_DEPTH:
        raise RecursionError("Max depth exceeded in validate_schema.")
    
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
            if not validate_schema(data[key], expected_type, depth + 1):
                return False
        else:
            if not isinstance(data[key], TYPE_MAP[expected_type]):
                return False
    
    return True