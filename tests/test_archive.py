"""
Тесты для модуля archive (MAP-Elites).
"""

import tempfile
from pathlib import Path

import sys
sys.path.insert(0, "src")

from archive import MAPElitesArchive, SimpleArchive, ArchiveEntry
from agents import Attack


class TestMAPElitesArchive:
    """Тесты для MAP-Elites архива."""

    def test_empty_archive(self):
        archive = MAPElitesArchive()

        assert len(archive) == 0
        assert archive.sample(5) == []
        assert archive.get_all_attacks() == []

    def test_add_single_attack(self):
        archive = MAPElitesArchive()

        attack = Attack(
            test_code="def test_x(): pass",
            description="Test",
            attack_type="edge_case",
        )

        added = archive.add(attack, fitness=0.8, round_num=1)

        assert added is True
        assert len(archive) == 1

    def test_add_duplicate_cell_lower_fitness(self):
        """Новая атака с меньшим fitness не должна заменить старую."""
        archive = MAPElitesArchive()

        attack1 = Attack("def test_1(): pass", "First", "edge_case")
        attack2 = Attack("def test_2(): pass", "Second", "edge_case")  # Тот же тип, та же сложность

        archive.add(attack1, fitness=0.9, round_num=1)
        added = archive.add(attack2, fitness=0.5, round_num=2)

        assert added is False
        assert len(archive) == 1
        assert archive.get_all_attacks()[0].description == "First"

    def test_add_duplicate_cell_higher_fitness(self):
        """Новая атака с большим fitness должна заменить старую."""
        archive = MAPElitesArchive()

        attack1 = Attack("def test_1(): pass", "First", "edge_case")
        attack2 = Attack("def test_2(): pass", "Second", "edge_case")

        archive.add(attack1, fitness=0.5, round_num=1)
        added = archive.add(attack2, fitness=0.9, round_num=2)

        assert added is True
        assert len(archive) == 1
        assert archive.get_all_attacks()[0].description == "Second"

    def test_different_attack_types(self):
        """Атаки разных типов должны быть в разных ячейках."""
        archive = MAPElitesArchive()

        attack1 = Attack("def test_1(): pass", "First", "edge_case")
        attack2 = Attack("def test_2(): pass", "Second", "injection")
        attack3 = Attack("def test_3(): pass", "Third", "overflow")

        archive.add(attack1, fitness=0.8, round_num=1)
        archive.add(attack2, fitness=0.8, round_num=1)
        archive.add(attack3, fitness=0.8, round_num=1)

        assert len(archive) == 3

    def test_complexity_bins(self):
        """Атаки разной сложности должны быть в разных ячейках."""
        archive = MAPElitesArchive()

        # Короткий код (1 строка)
        attack1 = Attack("def test(): pass", "Short", "edge_case")

        # Длинный код (15 строк)
        long_code = "\n".join([f"    line{i} = {i}" for i in range(15)])
        attack2 = Attack(f"def test():\n{long_code}", "Long", "edge_case")

        archive.add(attack1, fitness=0.8, round_num=1)
        archive.add(attack2, fitness=0.8, round_num=1)

        # Должны быть в разных bin'ах по сложности
        assert len(archive) == 2

    def test_sample(self):
        archive = MAPElitesArchive()

        for i in range(10):
            attack = Attack(f"def test_{i}(): pass", f"Attack {i}", f"type_{i}")
            archive.add(attack, fitness=0.8, round_num=1)

        sampled = archive.sample(3)

        assert len(sampled) == 3
        assert all(isinstance(a, Attack) for a in sampled)

    def test_sample_more_than_available(self):
        archive = MAPElitesArchive()

        attack = Attack("def test(): pass", "Only one", "edge_case")
        archive.add(attack, fitness=0.8, round_num=1)

        sampled = archive.sample(10)

        assert len(sampled) == 1

    def test_get_best(self):
        archive = MAPElitesArchive()

        attacks_data = [
            ("edge_case", 0.5),
            ("injection", 0.9),
            ("overflow", 0.7),
        ]

        for attack_type, fitness in attacks_data:
            attack = Attack("def test(): pass", f"Type: {attack_type}", attack_type)
            archive.add(attack, fitness=fitness, round_num=1)

        best = archive.get_best(2)

        assert len(best) == 2
        assert best[0].fitness == 0.9
        assert best[1].fitness == 0.7

    def test_coverage(self):
        archive = MAPElitesArchive()

        for _ in range(3):
            archive.add(Attack("def t(): pass", "A", "edge_case"), 0.8, 1)

        archive.add(Attack("def t(): pass", "B", "injection"), 0.8, 1)
        archive.add(Attack("def t(): pass", "C", "injection"), 0.9, 1)  # Заменит B

        coverage = archive.coverage()

        assert coverage["edge_case"] == 1  # Только одна ячейка
        assert coverage["injection"] == 1

    def test_save_and_load(self):
        archive = MAPElitesArchive()

        attack = Attack("def test(): pass", "Test attack", "edge_case")
        archive.add(attack, fitness=0.85, round_num=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "archive.json"

            archive.save(path)

            new_archive = MAPElitesArchive()
            new_archive.load(path)

            assert len(new_archive) == 1
            loaded_attack = new_archive.get_all_attacks()[0]
            assert loaded_attack.description == "Test attack"


class TestSimpleArchive:
    """Тесты для простого архива (baseline)."""

    def test_add_and_retrieve(self):
        archive = SimpleArchive(max_size=10)

        attack = Attack("def test(): pass", "Test", "edge_case")
        archive.add(attack, fitness=0.8, round_num=1)

        assert len(archive) == 1

    def test_keeps_top_n(self):
        archive = SimpleArchive(max_size=3)

        for i in range(5):
            attack = Attack(f"def test_{i}(): pass", f"Attack {i}", "edge_case")
            archive.add(attack, fitness=i * 0.2, round_num=1)

        # Должен хранить только топ-3 по fitness
        assert len(archive) == 3

        # Проверяем что это топ-3
        attacks = archive.get_all_attacks()
        descriptions = [a.description for a in attacks]

        # Attack 4 (0.8), Attack 3 (0.6), Attack 2 (0.4)
        assert "Attack 4" in descriptions
        assert "Attack 3" in descriptions
        assert "Attack 2" in descriptions
        assert "Attack 0" not in descriptions
        assert "Attack 1" not in descriptions

    def test_sample(self):
        archive = SimpleArchive(max_size=10)

        for i in range(5):
            attack = Attack(f"def test_{i}(): pass", f"Attack {i}", "edge_case")
            archive.add(attack, fitness=0.8, round_num=1)

        sampled = archive.sample(2)

        assert len(sampled) == 2


class TestArchiveEntry:
    """Тесты для ArchiveEntry."""

    def test_to_dict(self):
        attack = Attack("code", "desc", "type")
        entry = ArchiveEntry(attack=attack, fitness=0.75, round_discovered=5)

        d = entry.to_dict()

        assert d["fitness"] == 0.75
        assert d["round_discovered"] == 5
        assert d["attack"]["test_code"] == "code"

    def test_from_dict(self):
        d = {
            "attack": {
                "test_code": "code",
                "description": "desc",
                "attack_type": "type",
            },
            "fitness": 0.75,
            "round_discovered": 5,
        }

        entry = ArchiveEntry.from_dict(d)

        assert entry.fitness == 0.75
        assert entry.round_discovered == 5
        assert entry.attack.test_code == "code"
