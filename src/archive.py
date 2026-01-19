"""
MAP-Elites Archive для сохранения разнообразия атак.

MAP-Elites — quality-diversity алгоритм:
- Пространство разбивается на ячейки по поведенческим характеристикам
- В каждой ячейке хранится только лучший элемент
- Это предотвращает схлопывание к одной стратегии

В нашем случае:
- Ось 1: Тип атаки (edge_case, invalid_input, injection, etc.)
- Ось 2: Сложность атаки (количество строк кода)
- Fitness: Насколько сильно атака "ломает" код (0-1)
"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

from agents import Attack

logger = logging.getLogger(__name__)


@dataclass
class ArchiveEntry:
    """Элемент архива."""
    attack: Attack
    fitness: float  # 0-1, выше = лучше атака
    round_discovered: int  # В каком раунде нашли

    def to_dict(self) -> dict:
        return {
            "attack": asdict(self.attack),
            "fitness": self.fitness,
            "round_discovered": self.round_discovered,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArchiveEntry":
        return cls(
            attack=Attack(**data["attack"]),
            fitness=data["fitness"],
            round_discovered=data["round_discovered"],
        )


class MAPElitesArchive:
    """
    MAP-Elites архив для хранения разнообразных атак.

    Behavior space:
    - attack_type: категория атаки (строка)
    - complexity: bins по количеству строк (0-5, 5-10, 10-20, 20+)

    Каждая (attack_type, complexity_bin) ячейка хранит лучшую атаку.
    """

    COMPLEXITY_BINS = [(0, 5), (5, 10), (10, 20), (20, float("inf"))]

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.archive: dict[tuple[str, int], ArchiveEntry] = {}

    def _get_complexity_bin(self, code: str) -> int:
        """Определяет bin по количеству строк."""
        n_lines = len(code.strip().split("\n"))
        for i, (low, high) in enumerate(self.COMPLEXITY_BINS):
            if low <= n_lines < high:
                return i
        return len(self.COMPLEXITY_BINS) - 1

    def _get_cell(self, attack: Attack) -> tuple[str, int]:
        """Определяет ячейку для атаки."""
        complexity_bin = self._get_complexity_bin(attack.test_code)
        return (attack.attack_type.lower(), complexity_bin)

    def add(
        self,
        attack: Attack,
        fitness: float,
        round_num: int,
    ) -> bool:
        """
        Пытается добавить атаку в архив.

        Returns:
            True если атака добавлена (новая ячейка или лучше существующей)
        """
        cell = self._get_cell(attack)
        entry = ArchiveEntry(attack=attack, fitness=fitness, round_discovered=round_num)

        # Проверяем, есть ли уже что-то в этой ячейке
        if cell not in self.archive:
            self.archive[cell] = entry
            logger.debug(f"New cell filled: {cell}")
            return True

        # Сравниваем fitness
        if fitness > self.archive[cell].fitness:
            logger.debug(f"Improved cell {cell}: {self.archive[cell].fitness:.3f} -> {fitness:.3f}")
            self.archive[cell] = entry
            return True

        return False

    def sample(self, n: int = 1) -> list[Attack]:
        """Выбирает случайные атаки из архива."""
        import random

        if not self.archive:
            return []

        entries = list(self.archive.values())
        n = min(n, len(entries))
        sampled = random.sample(entries, n)
        return [e.attack for e in sampled]

    def get_all_attacks(self) -> list[Attack]:
        """Возвращает все атаки из архива."""
        return [e.attack for e in self.archive.values()]

    def get_best(self, n: int = 5) -> list[ArchiveEntry]:
        """Возвращает топ-N атак по fitness."""
        sorted_entries = sorted(
            self.archive.values(),
            key=lambda e: e.fitness,
            reverse=True
        )
        return sorted_entries[:n]

    def coverage(self) -> dict[str, int]:
        """Статистика заполнения архива по типам атак."""
        from collections import Counter
        types = [cell[0] for cell in self.archive.keys()]
        return dict(Counter(types))

    def save(self, path: Path) -> None:
        """Сохраняет архив в JSON."""
        data = {
            str(k): v.to_dict()
            for k, v in self.archive.items()
        }
        path.write_text(json.dumps(data, indent=2))
        logger.info(f"Archive saved to {path} ({len(self.archive)} entries)")

    def load(self, path: Path) -> None:
        """Загружает архив из JSON."""
        if not path.exists():
            logger.warning(f"Archive file not found: {path}")
            return

        data = json.loads(path.read_text())
        for k_str, v in data.items():
            # Восстанавливаем tuple ключ
            k = eval(k_str)  # ("edge_case", 0) -> tuple
            self.archive[k] = ArchiveEntry.from_dict(v)

        logger.info(f"Archive loaded from {path} ({len(self.archive)} entries)")

    def __len__(self) -> int:
        return len(self.archive)

    def __repr__(self) -> str:
        return f"MAPElitesArchive({len(self.archive)} entries, coverage={self.coverage()})"


# Упрощённый архив без MAP-Elites для сравнения (baseline)
class SimpleArchive:
    """
    Простой архив: хранит топ-N по fitness.
    Используется для ablation study (сравнение с MAP-Elites).
    """

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.entries: list[ArchiveEntry] = []

    def add(self, attack: Attack, fitness: float, round_num: int) -> bool:
        entry = ArchiveEntry(attack=attack, fitness=fitness, round_discovered=round_num)
        self.entries.append(entry)

        # Сортируем и обрезаем
        self.entries.sort(key=lambda e: e.fitness, reverse=True)
        self.entries = self.entries[:self.max_size]

        return True

    def sample(self, n: int = 1) -> list[Attack]:
        import random
        n = min(n, len(self.entries))
        sampled = random.sample(self.entries, n) if self.entries else []
        return [e.attack for e in sampled]

    def get_all_attacks(self) -> list[Attack]:
        return [e.attack for e in self.entries]

    def __len__(self) -> int:
        return len(self.entries)
