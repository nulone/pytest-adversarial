"""
URL Parser — второй пример для ACH эксперимента.

ВНИМАНИЕ: Этот код НАМЕРЕННО содержит уязвимости для демонстрации.

Известные проблемы:
1. Нет валидации URL формата
2. Уязвим к path traversal
3. Нет обработки unicode в URL
4. Нет защиты от очень длинных URL
5. Query параметры парсятся небезопасно
"""

from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote


def parse_url(url: str) -> dict:
    """
    Парсит URL и возвращает компоненты.

    Args:
        url: URL строка

    Returns:
        dict с scheme, host, port, path, query, fragment
    """
    parsed = urlparse(url)

    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port,
        "path": parsed.path,
        "query": parsed.query,
        "fragment": parsed.fragment,
    }


def get_query_param(url: str, param: str) -> Optional[str]:
    """
    Извлекает значение query параметра.

    Args:
        url: URL строка
        param: Имя параметра

    Returns:
        Значение или None
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    values = params.get(param)
    return values[0] if values else None


def normalize_path(path: str) -> str:
    """
    Нормализует путь (убирает ../, ./, дублирующие /).

    Args:
        path: Путь

    Returns:
        Нормализованный путь
    """
    # Заменяем // на /
    while "//" in path:
        path = path.replace("//", "/")

    # Обрабатываем ..
    parts = path.split("/")
    result = []

    for part in parts:
        if part == "..":
            if result:
                result.pop()
        elif part != ".":
            result.append(part)

    return "/".join(result)


def build_url(
    scheme: str = "https",
    host: str = "",
    port: Optional[int] = None,
    path: str = "/",
    query: Optional[dict] = None,
) -> str:
    """
    Собирает URL из компонентов.

    Args:
        scheme: http или https
        host: Хост
        port: Порт (optional)
        path: Путь
        query: Query параметры

    Returns:
        URL строка
    """
    url = f"{scheme}://{host}"

    if port:
        url += f":{port}"

    url += path

    if query:
        query_str = "&".join(f"{k}={v}" for k, v in query.items())
        url += f"?{query_str}"

    return url


def decode_url(url: str) -> str:
    """
    Декодирует URL-encoded строку.

    Args:
        url: Закодированная строка

    Returns:
        Декодированная строка
    """
    return unquote(url)


def is_valid_url(url: str) -> bool:
    """
    Проверяет валидность URL.

    Args:
        url: URL строка

    Returns:
        True если валидный
    """
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


def extract_domain(url: str) -> str:
    """
    Извлекает домен из URL.

    Args:
        url: URL строка

    Returns:
        Домен
    """
    parsed = urlparse(url)
    return parsed.hostname
