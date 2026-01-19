#!/usr/bin/env python3
"""
Convergent Evolution Experiment.

Запускает DRQ несколько раз независимо и проверяет:
1. Сходятся ли результаты?
2. Находятся ли похожие уязвимости?
3. Какой разброс в robustness?

Это ключевой эксперимент из оригинальной DRQ статьи.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from drq import DRQRunner, DRQConfig
from config import get_api_config, MODEL_GPT4O_MINI


def run_convergent_experiment(
    n_runs: int = 3,
    n_rounds: int = 10,
    target_file: str = "examples/json_parser/target.py",
):
    """
    Запускает несколько независимых DRQ экспериментов.

    Args:
        n_runs: Количество независимых запусков
        n_rounds: Раундов в каждом запуске
        target_file: Целевой файл
    """

    print("="*70)
    print("🔬 CONVERGENT EVOLUTION EXPERIMENT")
    print("="*70)
    print(f"Independent runs: {n_runs}")
    print(f"Rounds per run: {n_rounds}")
    print(f"Target: {target_file}")
    print("="*70)

    # Проверяем API
    if not get_api_config():
        print("❌ API ключ не задан!")
        sys.exit(1)

    # Результаты всех запусков
    all_results = []

    # Директория для результатов
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir = Path(f"results/convergent_{timestamp}")
    exp_dir.mkdir(parents=True, exist_ok=True)

    for run_id in range(1, n_runs + 1):
        print(f"\n{'='*70}")
        print(f"🔄 RUN {run_id}/{n_runs}")
        print(f"{'='*70}")

        # Конфиг для этого запуска
        config = DRQConfig(
            n_rounds=n_rounds,
            attacks_per_round=5,
            attacker_model=MODEL_GPT4O_MINI,
            defender_model=MODEL_GPT4O_MINI,
            target_file=target_file,
            output_dir=str(exp_dir / f"run_{run_id}"),
        )

        # Запускаем
        runner = DRQRunner(config)
        results = runner.run()

        # Сохраняем результаты
        run_summary = {
            "run_id": run_id,
            "final_robustness": results["final_robustness"],
            "total_attacks": len(runner.attack_archive.get_all()),
            "niches_covered": len(runner.attack_archive.archive),
            "attack_types": list(set(a.attack_type for a in runner.attack_archive.get_all())),
            "api_calls": results["api_calls"],
            "cost": results["estimated_cost"],
        }

        all_results.append(run_summary)

        print(f"\n📊 Run {run_id} Summary:")
        print(f"   Robustness: {run_summary['final_robustness']:.1%}")
        print(f"   Attacks: {run_summary['total_attacks']}")
        print(f"   Types: {run_summary['attack_types']}")

    # Анализ конвергенции
    print("\n" + "="*70)
    print("📈 CONVERGENT EVOLUTION ANALYSIS")
    print("="*70)

    robustness_values = [r["final_robustness"] for r in all_results]
    attack_counts = [r["total_attacks"] for r in all_results]

    # Все типы атак
    all_types = set()
    for r in all_results:
        all_types.update(r["attack_types"])

    # Общие типы (найдены во всех запусках)
    common_types = set(all_results[0]["attack_types"])
    for r in all_results[1:]:
        common_types &= set(r["attack_types"])

    print("\n1. ROBUSTNESS CONVERGENCE:")
    print(f"   Values: {[f'{v:.1%}' for v in robustness_values]}")
    print(f"   Mean: {sum(robustness_values)/len(robustness_values):.1%}")
    print(f"   Spread: {max(robustness_values) - min(robustness_values):.1%}")

    print("\n2. ATTACK CONVERGENCE:")
    print(f"   Total unique types found: {len(all_types)}")
    print(f"   Types found in ALL runs: {common_types}")
    print(f"   Convergence rate: {len(common_types)/len(all_types):.1%}")

    print("\n3. ATTACK COUNTS:")
    print(f"   Per run: {attack_counts}")
    print(f"   Mean: {sum(attack_counts)/len(attack_counts):.1f}")

    # Сохраняем сводку
    summary = {
        "experiment_type": "convergent_evolution",
        "timestamp": timestamp,
        "n_runs": n_runs,
        "n_rounds": n_rounds,
        "target_file": target_file,
        "runs": all_results,
        "analysis": {
            "robustness_mean": sum(robustness_values)/len(robustness_values),
            "robustness_spread": max(robustness_values) - min(robustness_values),
            "all_attack_types": list(all_types),
            "common_attack_types": list(common_types),
            "convergence_rate": len(common_types)/len(all_types) if all_types else 0,
        },
        "total_cost": sum(r["cost"] for r in all_results),
    }

    summary_path = exp_dir / "convergent_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n💾 Results saved to: {exp_dir}")
    print(f"💰 Total cost: ${summary['total_cost']:.2f}")

    # Вердикт
    print("\n" + "="*70)
    print("🎯 CONVERGENCE VERDICT")
    print("="*70)

    spread = max(robustness_values) - min(robustness_values)
    convergence = len(common_types)/len(all_types) if all_types else 0

    if spread < 0.1 and convergence > 0.5:
        print("✅ STRONG CONVERGENCE")
        print("   Independent runs produce similar results.")
        print("   This validates the DRQ approach!")
    elif spread < 0.2 and convergence > 0.3:
        print("⚠️ MODERATE CONVERGENCE")
        print("   Some variation between runs.")
        print("   Consider more rounds or different models.")
    else:
        print("❌ WEAK CONVERGENCE")
        print("   Results vary significantly between runs.")
        print("   May need different approach or more iterations.")

    return summary


def main():
    """CLI для convergent experiment."""

    print("\n🔬 Convergent Evolution Experiment")
    print("Based on Sakana AI's DRQ research\n")

    try:
        n_runs = int(input("Number of independent runs (default 3): ").strip() or "3")
        n_rounds = int(input("Rounds per run (default 10): ").strip() or "10")
    except ValueError:
        n_runs = 3
        n_rounds = 10

    estimated_cost = n_runs * n_rounds * 6 * 0.002  # 6 calls per round
    print(f"\n📊 Estimated cost: ${estimated_cost:.2f}")
    print(f"📊 Estimated time: {n_runs * n_rounds * 0.5:.0f} minutes\n")

    confirm = input("Continue? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    run_convergent_experiment(n_runs=n_runs, n_rounds=n_rounds)


if __name__ == "__main__":
    main()
