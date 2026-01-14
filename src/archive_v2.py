"""
MAP-Elites Archive — ключевой компонент DRQ.

MAP-Elites сохраняет РАЗНООБРАЗИЕ стратегий, а не только лучшую.
Это критично для Red Queen динамики.

Архив организован по "нишам" (behavior descriptors):
- Тип атаки (edge_case, injection, overflow, ...)
- Тип ошибки (TypeError, ValueError, RecursionError, ...)
- Сложность атаки (простая, средняя, сложная)

В каждой нише хранится ЛУЧШАЯ атака для этой ниши.
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path
from collections import defaultdict


@dataclass
class AttackGenome:
    """Геном атаки — хранит код и метаданные."""
    
    code: str
    attack_type: str  # edge_case, injection, overflow, etc.
    error_type: str   # TypeError, ValueError, etc.
    description: str
    
    # Fitness metrics
    fitness: float = 0.0
    
    # Generality: против скольких defenders работает
    defeats_count: int = 0
    tested_against: int = 0
    
    # Lineage
    generation: int = 0
    parent_hash: Optional[str] = None
    
    @property
    def generality(self) -> float:
        """Доля defenders, которых эта атака побеждает."""
        if self.tested_against == 0:
            return 0.0
        return self.defeats_count / self.tested_against
    
    @property
    def niche(self) -> tuple:
        """Behavior descriptor для MAP-Elites."""
        return (self.attack_type, self.error_type)
    
    @property
    def hash(self) -> str:
        """Уникальный идентификатор генома."""
        return hashlib.md5(self.code.encode()).hexdigest()[:12]


@dataclass
class DefenseGenome:
    """Геном защиты — хранит код и метаданные."""
    
    code: str
    description: str
    
    # Fitness: доля атак, которые отражает
    fitness: float = 0.0
    
    # Robustness: против скольких attackers защищает
    blocks_count: int = 0
    tested_against: int = 0
    
    # Lineage
    generation: int = 0
    parent_hash: Optional[str] = None
    
    @property
    def robustness(self) -> float:
        """Доля attackers, от которых защищает."""
        if self.tested_against == 0:
            return 0.0
        return self.blocks_count / self.tested_against
    
    @property
    def hash(self) -> str:
        return hashlib.md5(self.code.encode()).hexdigest()[:12]


class MAPElitesArchive:
    """
    MAP-Elites архив для атак.
    
    Ключевая идея: сохраняем ЛУЧШУЮ атаку в каждой нише.
    Ниша определяется (attack_type, error_type).
    
    Это даёт разнообразие атак для тестирования defenders.
    """
    
    # Известные типы атак
    ATTACK_TYPES = [
        "edge_case",      # Граничные значения
        "invalid_input",  # Неверные типы
        "injection",      # Инъекции
        "overflow",       # Переполнения
        "unicode",        # Unicode проблемы
        "concurrency",    # Race conditions
        "resource",       # Resource exhaustion
        "unknown",        # Неизвестный тип
    ]
    
    # Известные типы ошибок
    ERROR_TYPES = [
        "TypeError",
        "ValueError", 
        "KeyError",
        "IndexError",
        "RecursionError",
        "MemoryError",
        "JSONDecodeError",
        "AttributeError",
        "ZeroDivisionError",
        "RuntimeError",
        "unknown",
    ]
    
    def __init__(self, max_per_niche: int = 3):
        self.max_per_niche = max_per_niche
        
        # Основной архив: niche -> list of genomes
        self.archive: dict[tuple, list[AttackGenome]] = defaultdict(list)
        
        # История всех геномов (для lineage tracking)
        self.history: list[AttackGenome] = []
        
        # Статистика
        self.total_evaluated = 0
        self.total_added = 0
    
    def add(self, genome: AttackGenome) -> bool:
        """
        Добавляет геном в архив, если он лучше существующего в нише.
        
        Returns:
            True если геном добавлен, False если отклонён
        """
        self.total_evaluated += 1
        self.history.append(genome)
        
        niche = genome.niche
        niche_list = self.archive[niche]
        
        # Если ниша не заполнена — добавляем
        if len(niche_list) < self.max_per_niche:
            niche_list.append(genome)
            niche_list.sort(key=lambda g: g.fitness, reverse=True)
            self.total_added += 1
            return True
        
        # Если fitness выше минимального в нише — заменяем
        min_fitness = min(g.fitness for g in niche_list)
        if genome.fitness > min_fitness:
            # Удаляем худший
            niche_list.sort(key=lambda g: g.fitness)
            niche_list.pop(0)
            niche_list.append(genome)
            niche_list.sort(key=lambda g: g.fitness, reverse=True)
            self.total_added += 1
            return True
        
        return False
    
    def get_all(self) -> list[AttackGenome]:
        """Возвращает все геномы из архива."""
        result = []
        for niche_list in self.archive.values():
            result.extend(niche_list)
        return result
    
    def get_by_type(self, attack_type: str) -> list[AttackGenome]:
        """Возвращает геномы определённого типа атаки."""
        result = []
        for niche, niche_list in self.archive.items():
            if niche[0] == attack_type:
                result.extend(niche_list)
        return result
    
    def get_diverse_sample(self, n: int) -> list[AttackGenome]:
        """
        Возвращает разнообразную выборку из архива.
        Берёт по одному из каждой ниши, потом повторяет.
        """
        all_genomes = self.get_all()
        if len(all_genomes) <= n:
            return all_genomes
        
        # Берём по одному из каждой ниши
        sample = []
        niches = list(self.archive.keys())
        
        while len(sample) < n and niches:
            for niche in niches[:]:
                if self.archive[niche]:
                    # Берём лучший из ниши
                    sample.append(self.archive[niche][0])
                    if len(sample) >= n:
                        break
            # Если прошли все ниши, но нужно ещё — берём вторые лучшие
            niches = [n for n in niches if len(self.archive[n]) > 1]
        
        return sample[:n]
    
    def get_stats(self) -> dict:
        """Статистика архива."""
        all_genomes = self.get_all()
        
        coverage = {}
        for attack_type in self.ATTACK_TYPES:
            coverage[attack_type] = len(self.get_by_type(attack_type))
        
        return {
            "total_niches": len(self.archive),
            "total_genomes": len(all_genomes),
            "total_evaluated": self.total_evaluated,
            "acceptance_rate": self.total_added / max(1, self.total_evaluated),
            "coverage_by_type": coverage,
            "avg_fitness": sum(g.fitness for g in all_genomes) / max(1, len(all_genomes)),
            "avg_generality": sum(g.generality for g in all_genomes) / max(1, len(all_genomes)),
        }
    
    def save(self, path: Path) -> None:
        """Сохраняет архив в JSON."""
        data = {
            "genomes": [asdict(g) for g in self.get_all()],
            "history": [asdict(g) for g in self.history],
            "stats": self.get_stats(),
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    
    def load(self, path: Path) -> None:
        """Загружает архив из JSON."""
        data = json.loads(path.read_text())
        
        for g_dict in data.get("genomes", []):
            genome = AttackGenome(**g_dict)
            self.archive[genome.niche].append(genome)
        
        for g_dict in data.get("history", []):
            self.history.append(AttackGenome(**g_dict))


class DefenseArchive:
    """
    Архив defenders.
    
    В отличие от атак, defenders не организованы по нишам.
    Храним историю всех защит для тестирования generality.
    """
    
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.archive: list[DefenseGenome] = []
        self.history: list[DefenseGenome] = []
    
    def add(self, genome: DefenseGenome) -> None:
        """Добавляет защиту в архив."""
        self.history.append(genome)
        
        # Добавляем в архив
        self.archive.append(genome)
        
        # Если архив переполнен — удаляем худшие
        if len(self.archive) > self.max_size:
            self.archive.sort(key=lambda g: g.robustness, reverse=True)
            self.archive = self.archive[:self.max_size]
    
    def get_best(self) -> Optional[DefenseGenome]:
        """Возвращает лучшую защиту."""
        if not self.archive:
            return None
        return max(self.archive, key=lambda g: g.robustness)
    
    def get_all(self) -> list[DefenseGenome]:
        """Возвращает все защиты."""
        return self.archive.copy()
    
    def get_stats(self) -> dict:
        """Статистика архива."""
        if not self.archive:
            return {"total": 0}
        
        return {
            "total": len(self.archive),
            "total_history": len(self.history),
            "best_robustness": max(g.robustness for g in self.archive),
            "avg_robustness": sum(g.robustness for g in self.archive) / len(self.archive),
        }
