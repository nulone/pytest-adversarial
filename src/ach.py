"""
ACH (Adversarial Code Hardening) — главный цикл DRQ.

Алгоритм:
1. Attacker генерирует атаку против текущего кода
2. Fitness оценивает: атака сработала?
3. Если да — добавляем в MAP-Elites архив
4. Defender пытается исправить код против ВСЕХ атак из архива
5. Повторяем

С каждым раундом:
- Архив атак растёт и становится разнообразнее
- Код становится robust'нее
"""

import argparse
import json
import logging
import random
from pathlib import Path

from config import Config, PRESET_DEBUG, PRESET_MINIMAL, PRESET_FULL
from agents import Attacker, Defender, Attack
from archive import MAPElitesArchive, SimpleArchive
from fitness import FitnessEvaluator

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class ACHRunner:
    """
    Запускает DRQ цикл для hardening кода.

    Основано на: https://arxiv.org/abs/2601.03335
    """

    def __init__(self, config: Config, target_code: str, target_path: Path):
        self.config = config
        self.original_code = target_code
        self.current_code = target_code
        self.target_path = target_path

        # Инициализация компонентов
        self.attacker = Attacker(config.model)
        self.defender = Defender(config.model)
        self.fitness = FitnessEvaluator()

        # Выбор архива (MAP-Elites или простой для сравнения)
        if config.drq.use_map_elites:
            self.archive = MAPElitesArchive(max_size=config.drq.archive_size)
        else:
            self.archive = SimpleArchive(max_size=config.drq.archive_size)

        # История для метрик
        self.history: list[dict] = []
        self.failed_attacks: list[Attack] = []

    def run(self) -> dict:
        """
        Запускает полный цикл DRQ.

        Returns:
            Словарь с результатами и метриками
        """
        logger.info(f"Starting ACH with {self.config.drq.n_rounds} rounds")
        logger.info(f"Target: {self.target_path}")
        logger.info(f"MAP-Elites: {self.config.drq.use_map_elites}")

        for round_num in range(1, self.config.drq.n_rounds + 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"ROUND {round_num}/{self.config.drq.n_rounds}")
            logger.info(f"{'='*50}")

            round_result = self._run_round(round_num)
            self.history.append(round_result)

            # Сохраняем прогресс
            if round_num % self.config.experiment.save_every == 0:
                self._save_checkpoint(round_num)

            # Логируем прогресс
            logger.info(f"Round {round_num} complete:")
            logger.info(f"  New attacks: {round_result['new_attacks']}")
            logger.info(f"  Archive size: {len(self.archive)}")
            logger.info(f"  Defense score: {round_result['defense_score']:.2%}")

        return self._compile_results()

    def _run_round(self, round_num: int) -> dict:
        """Один раунд DRQ: атаки → защита."""
        new_attacks = 0
        successful_defenses = 0

        # Фаза 1: Генерация атак
        logger.info("Phase 1: Generating attacks...")

        for i in range(self.config.drq.n_iterations):
            attack = self.attacker.generate_attack(
                target_code=self.current_code,
                previous_attacks=self.archive.get_all_attacks(),
                failed_attacks=self.failed_attacks[-10:],  # Последние неудачные
            )

            if attack is None:
                continue

            # Оцениваем атаку
            result = self.fitness.evaluate_attack(self.current_code, attack)

            if result.score > 0.5:  # Атака сработала
                added = self.archive.add(attack, result.score, round_num)
                if added:
                    new_attacks += 1
                    logger.debug(f"  Attack {i}: {attack.attack_type} - SUCCESS (fitness={result.score:.2f})")
            else:
                self.failed_attacks.append(attack)
                if len(self.failed_attacks) > 50:
                    self.failed_attacks = self.failed_attacks[-30:]

        # Фаза 2: Защита против ВСЕХ атак из архива
        logger.info("Phase 2: Defending against archive...")

        all_attacks = self.archive.get_all_attacks()
        if all_attacks:
            defense = self.defender.generate_defense(
                target_code=self.current_code,
                failing_tests=all_attacks[:10],  # Топ-10 атак
                previous_fixes=[],
            )

            if defense:
                # Проверяем защиту против ВСЕХ атак
                defense_result = self.fitness.evaluate_defense(
                    defense.fixed_code,
                    all_attacks
                )

                if defense_result.score > self.config.drq.fitness_threshold:
                    self.current_code = defense.fixed_code
                    successful_defenses = 1
                    logger.info(f"  Defense accepted: {defense_result.score:.2%} tests pass")
                else:
                    logger.info(f"  Defense rejected: only {defense_result.score:.2%} tests pass")

        return {
            "round": round_num,
            "new_attacks": new_attacks,
            "archive_size": len(self.archive),
            "defense_score": self.fitness.evaluate_defense(
                self.current_code,
                self.archive.get_all_attacks()
            ).score if self.archive.get_all_attacks() else 1.0,
            "code_changed": successful_defenses > 0,
        }

    def _save_checkpoint(self, round_num: int) -> None:
        """Сохраняет текущее состояние."""
        output_dir = Path(self.config.experiment.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Сохраняем текущий код
        code_path = output_dir / f"code_round_{round_num}.py"
        code_path.write_text(self.current_code)

        # Сохраняем историю
        history_path = output_dir / "history.json"
        history_path.write_text(json.dumps(self.history, indent=2))

        logger.info(f"Checkpoint saved to {output_dir}")

    def _compile_results(self) -> dict:
        """Собирает финальные результаты."""
        return {
            "original_code": self.original_code,
            "hardened_code": self.current_code,
            "total_rounds": len(self.history),
            "final_archive_size": len(self.archive),
            "archive_coverage": self.archive.coverage() if hasattr(self.archive, 'coverage') else {},
            "history": self.history,
            "improvement": self._calculate_improvement(),
        }

    def _calculate_improvement(self) -> dict:
        """Считает метрики улучшения."""
        if not self.history:
            return {}

        first_score = self.history[0].get("defense_score", 0)
        last_score = self.history[-1].get("defense_score", 0)

        return {
            "initial_robustness": first_score,
            "final_robustness": last_score,
            "absolute_improvement": last_score - first_score,
            "relative_improvement": (last_score - first_score) / max(first_score, 0.01),
        }


def load_target(target_dir: str) -> tuple[str, Path]:
    """Загружает целевой код из директории."""
    target_path = Path(target_dir)

    # Ищем main файл
    for name in ["target.py", "main.py", "__init__.py"]:
        candidate = target_path / name
        if candidate.exists():
            return candidate.read_text(), candidate

    # Берём первый .py файл
    py_files = list(target_path.glob("*.py"))
    if py_files:
        return py_files[0].read_text(), py_files[0]

    raise FileNotFoundError(f"No Python files found in {target_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Adversarial Code Hardening using DRQ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/ach.py --target examples/json_parser --rounds 5
  python src/ach.py --target examples/json_parser --preset debug
  python src/ach.py --target my_code.py --no-map-elites
        """
    )

    parser.add_argument(
        "--target", "-t",
        required=True,
        help="Path to target code directory or file"
    )
    parser.add_argument(
        "--rounds", "-r",
        type=int,
        default=10,
        help="Number of DRQ rounds (default: 10)"
    )
    parser.add_argument(
        "--iterations", "-i",
        type=int,
        default=50,
        help="Iterations per round (default: 50)"
    )
    parser.add_argument(
        "--preset",
        choices=["debug", "minimal", "full"],
        help="Use preset configuration"
    )
    parser.add_argument(
        "--no-map-elites",
        action="store_true",
        help="Disable MAP-Elites (for baseline comparison)"
    )
    parser.add_argument(
        "--output", "-o",
        default="results",
        help="Output directory (default: results)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility"
    )

    args = parser.parse_args()

    # Загружаем конфиг
    if args.preset == "debug":
        config = PRESET_DEBUG
    elif args.preset == "minimal":
        config = PRESET_MINIMAL
    elif args.preset == "full":
        config = PRESET_FULL
    else:
        config = Config()

    # Применяем аргументы командной строки
    config.drq.n_rounds = args.rounds
    config.drq.n_iterations = args.iterations
    config.drq.use_map_elites = not args.no_map_elites
    config.experiment.output_dir = args.output
    config.experiment.seed = args.seed

    # Устанавливаем seed
    random.seed(args.seed)

    # Загружаем целевой код
    target_code, target_path = load_target(args.target)
    logger.info(f"Loaded {len(target_code)} chars from {target_path}")

    # Запускаем
    runner = ACHRunner(config, target_code, target_path)
    results = runner.run()

    # Сохраняем результаты
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Финальный код
    final_code_path = output_dir / "hardened_code.py"
    final_code_path.write_text(results["hardened_code"])
    logger.info(f"Hardened code saved to {final_code_path}")

    # Полные результаты
    results_path = output_dir / "results.json"
    # Убираем код из JSON (слишком большой)
    results_for_json = {k: v for k, v in results.items() if k not in ["original_code", "hardened_code"]}
    results_path.write_text(json.dumps(results_for_json, indent=2))

    # Выводим summary
    print("\n" + "="*50)
    print("RESULTS SUMMARY")
    print("="*50)
    print(f"Rounds completed: {results['total_rounds']}")
    print(f"Attacks discovered: {results['final_archive_size']}")
    print(f"Attack types: {results['archive_coverage']}")
    print(f"Improvement: {results['improvement']}")
    print(f"\nHardened code: {final_code_path}")


if __name__ == "__main__":
    main()
