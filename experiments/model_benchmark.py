#!/usr/bin/env python3
"""
Model Benchmark — сравнение разных LLM комбинаций.

Тестирует все комбинации Attacker × Defender и находит лучшую.

Запуск:
    cd /path/to/code-hardening
    python3 experiments/model_benchmark.py
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import shutil

# Находим корень проекта и добавляем src в путь
script_dir = Path(__file__).parent.resolve()
project_root = script_dir.parent
src_dir = project_root / "src"

# Добавляем оба пути на случай разной структуры
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

# Меняем рабочую директорию на корень проекта
os.chdir(project_root)

try:
    from drq import DRQRunner, DRQConfig
    from config import get_api_config
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print(f"   Текущая директория: {os.getcwd()}")
    print(f"   Project root: {project_root}")
    print(f"   Src dir: {src_dir}")
    print("\nПопробуй запустить из корня проекта:")
    print(f"   cd {project_root}")
    print("   python3 experiments/model_benchmark.py")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# МОДЕЛИ ДЛЯ ТЕСТИРОВАНИЯ
# ═══════════════════════════════════════════════════════════════

MODELS = {
    "gpt4o-mini": {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o-mini",
        "cost_per_call": 0.002,
    },
    "gpt4o": {
        "id": "openai/gpt-4o",
        "name": "GPT-4o",
        "cost_per_call": 0.01,
    },
    "claude-haiku": {
        "id": "anthropic/claude-3-haiku",
        "name": "Claude Haiku",
        "cost_per_call": 0.003,
    },
    "claude-sonnet": {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Claude Sonnet",
        "cost_per_call": 0.015,
    },
    "deepseek": {
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek V3",
        "cost_per_call": 0.001,
    },
    "llama-70b": {
        "id": "meta-llama/llama-3.1-70b-instruct",
        "name": "Llama 70B",
        "cost_per_call": 0.0005,  # Почти бесплатно
    },
}


# ═══════════════════════════════════════════════════════════════
# ПРЕСЕТЫ БЕНЧМАРКА
# ═══════════════════════════════════════════════════════════════

BENCHMARK_PRESETS = {
    "quick": {
        "name": "Quick (для поиска лучшей комбинации)",
        "rounds": 5,
        "attacks": 3,
        "description": "Быстрый тест всех комбинаций",
    },
    "standard": {
        "name": "Standard",
        "rounds": 10,
        "attacks": 5,
        "description": "Стандартный бенчмарк",
    },
    "full": {
        "name": "Full (для финальной статистики)",
        "rounds": 20,
        "attacks": 10,
        "description": "Полный тест лучших моделей",
    },
}


@dataclass
class BenchmarkResult:
    """Результат одной комбинации."""
    attacker_model: str
    defender_model: str
    attacker_name: str
    defender_name: str

    # Метрики
    peak_robustness: float
    final_robustness: float
    total_attacks: int
    attack_types: int
    niches_covered: int

    # Стоимость
    api_calls: int
    estimated_cost: float

    # Время
    duration_seconds: float


def run_single_benchmark(
    attacker_key: str,
    defender_key: str,
    rounds: int = 5,
    attacks_per_round: int = 3,
    output_dir: str = "results/benchmark",
) -> Optional[BenchmarkResult]:
    """Запускает один бенчмарк."""

    attacker = MODELS[attacker_key]
    defender = MODELS[defender_key]

    print(f"\n{'='*60}")
    print(f"🔴 Attacker: {attacker['name']}")
    print(f"🟢 Defender: {defender['name']}")
    print(f"{'='*60}")

    # Уникальная директория для этого теста
    run_dir = f"{output_dir}/{attacker_key}_vs_{defender_key}"

    # Очищаем предыдущие результаты
    if Path(run_dir).exists():
        shutil.rmtree(run_dir)

    config = DRQConfig(
        n_rounds=rounds,
        attacks_per_round=attacks_per_round,
        attacker_model=attacker["id"],
        defender_model=defender["id"],
        output_dir=run_dir,
        estimated_cost_per_call=(attacker["cost_per_call"] + defender["cost_per_call"]) / 2,
    )

    import time
    start_time = time.time()

    try:
        runner = DRQRunner(config)
        results = runner.run()

        duration = time.time() - start_time

        # Считаем типы атак
        attack_types = len(set(a.attack_type for a in runner.attack_archive.get_all()))

        return BenchmarkResult(
            attacker_model=attacker["id"],
            defender_model=defender["id"],
            attacker_name=attacker["name"],
            defender_name=defender["name"],
            peak_robustness=max(runner.metrics.get("robustness_history", [0])),
            final_robustness=results["final_robustness"],
            total_attacks=len(runner.attack_archive.get_all()),
            attack_types=attack_types,
            niches_covered=len(runner.attack_archive.archive),
            api_calls=results["api_calls"],
            estimated_cost=results["estimated_cost"],
            duration_seconds=duration,
        )

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


def run_benchmark(
    preset: str = "quick",
    attackers: list[str] = None,
    defenders: list[str] = None,
):
    """
    Запускает полный бенчмарк.

    Args:
        preset: quick, standard, или full
        attackers: Список ключей моделей для Attacker (или None для всех)
        defenders: Список ключей моделей для Defender (или None для всех)
    """

    # Проверяем API
    if not get_api_config():
        print("❌ API ключ не задан!")
        print("export OPENROUTER_API_KEY='sk-or-...'")
        sys.exit(1)

    # Пресет
    p = BENCHMARK_PRESETS[preset]

    # Модели по умолчанию
    if attackers is None:
        attackers = ["gpt4o-mini", "gpt4o", "deepseek"]
    if defenders is None:
        defenders = ["gpt4o-mini", "gpt4o", "deepseek"]

    # Оценка стоимости
    n_combinations = len(attackers) * len(defenders)
    calls_per_run = p["rounds"] * (p["attacks"] + 1)  # attacks + 1 defender

    avg_cost = sum(MODELS[m]["cost_per_call"] for m in attackers + defenders) / len(attackers + defenders)
    estimated_total = n_combinations * calls_per_run * avg_cost

    print("="*70)
    print("🏆 MODEL BENCHMARK")
    print("="*70)
    print(f"Preset: {p['name']}")
    print(f"Rounds: {p['rounds']}, Attacks/round: {p['attacks']}")
    print(f"Combinations: {n_combinations}")
    print(f"Attackers: {[MODELS[a]['name'] for a in attackers]}")
    print(f"Defenders: {[MODELS[d]['name'] for d in defenders]}")
    print(f"Estimated cost: ${estimated_total:.2f}")
    print("="*70)

    confirm = input("\nПродолжить? (y/n): ").strip().lower()
    if confirm != "y":
        print("Отменено.")
        return

    # Директория для результатов
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"results/benchmark_{timestamp}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Запускаем все комбинации
    results: list[BenchmarkResult] = []

    for i, attacker_key in enumerate(attackers):
        for j, defender_key in enumerate(defenders):
            combo_num = i * len(defenders) + j + 1
            print(f"\n{'#'*70}")
            print(f"# COMBO {combo_num}/{n_combinations}")
            print(f"{'#'*70}")

            result = run_single_benchmark(
                attacker_key=attacker_key,
                defender_key=defender_key,
                rounds=p["rounds"],
                attacks_per_round=p["attacks"],
                output_dir=output_dir,
            )

            if result:
                results.append(result)

    # Анализ результатов
    print("\n" + "="*70)
    print("📊 BENCHMARK RESULTS")
    print("="*70)

    if not results:
        print("❌ Нет результатов")
        return

    # Сортируем по разным метрикам
    print("\n🏆 TOP COMBINATIONS BY FINAL ROBUSTNESS:")
    by_robustness = sorted(results, key=lambda r: r.final_robustness, reverse=True)
    for i, r in enumerate(by_robustness[:5], 1):
        print(f"  {i}. {r.attacker_name} vs {r.defender_name}: {r.final_robustness:.1%}")

    print("\n🔴 TOP ATTACKERS (by attacks found):")
    by_attacks = sorted(results, key=lambda r: r.total_attacks, reverse=True)
    for i, r in enumerate(by_attacks[:5], 1):
        print(f"  {i}. {r.attacker_name}: {r.total_attacks} attacks, {r.attack_types} types")

    print("\n🟢 TOP DEFENDERS (by peak robustness):")
    by_defense = sorted(results, key=lambda r: r.peak_robustness, reverse=True)
    for i, r in enumerate(by_defense[:5], 1):
        print(f"  {i}. {r.defender_name}: {r.peak_robustness:.1%} peak")

    print("\n💰 COST EFFICIENCY (robustness per $):")
    by_efficiency = sorted(results, key=lambda r: r.final_robustness / max(r.estimated_cost, 0.01), reverse=True)
    for i, r in enumerate(by_efficiency[:5], 1):
        efficiency = r.final_robustness / max(r.estimated_cost, 0.01)
        print(f"  {i}. {r.attacker_name} vs {r.defender_name}: {efficiency:.1f}%/$ (${r.estimated_cost:.2f})")

    # Таблица всех результатов
    print("\n" + "="*70)
    print("📋 FULL RESULTS TABLE")
    print("="*70)
    print(f"{'Attacker':<15} {'Defender':<15} {'Final%':<8} {'Peak%':<8} {'Attacks':<8} {'Types':<6} {'Cost':<8}")
    print("-"*70)
    for r in sorted(results, key=lambda r: r.final_robustness, reverse=True):
        print(f"{r.attacker_name:<15} {r.defender_name:<15} {r.final_robustness:>6.1%}  {r.peak_robustness:>6.1%}  {r.total_attacks:>6}  {r.attack_types:>4}  ${r.estimated_cost:>5.2f}")

    # Сохраняем результаты
    summary = {
        "timestamp": timestamp,
        "preset": preset,
        "config": p,
        "attackers": attackers,
        "defenders": defenders,
        "results": [
            {
                "attacker": r.attacker_name,
                "defender": r.defender_name,
                "final_robustness": r.final_robustness,
                "peak_robustness": r.peak_robustness,
                "total_attacks": r.total_attacks,
                "attack_types": r.attack_types,
                "cost": r.estimated_cost,
            }
            for r in results
        ],
        "best_combo": {
            "by_robustness": f"{by_robustness[0].attacker_name} vs {by_robustness[0].defender_name}",
            "by_attacks": by_attacks[0].attacker_name,
            "by_defense": by_defense[0].defender_name,
            "by_efficiency": f"{by_efficiency[0].attacker_name} vs {by_efficiency[0].defender_name}",
        },
        "total_cost": sum(r.estimated_cost for r in results),
    }

    summary_path = Path(output_dir) / "benchmark_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n💾 Results saved to: {output_dir}")
    print(f"💰 Total cost: ${summary['total_cost']:.2f}")

    # Рекомендации
    print("\n" + "="*70)
    print("💡 RECOMMENDATIONS")
    print("="*70)
    print(f"Best Attacker: {by_attacks[0].attacker_name}")
    print(f"Best Defender: {by_defense[0].defender_name}")
    print(f"Best Overall: {by_robustness[0].attacker_name} vs {by_robustness[0].defender_name}")
    print(f"Best Value: {by_efficiency[0].attacker_name} vs {by_efficiency[0].defender_name}")

    return summary


def main():
    """CLI интерфейс."""

    print("\n🏆 MODEL BENCHMARK")
    print("Compare different LLM combinations\n")

    print("Presets:")
    for key, p in BENCHMARK_PRESETS.items():
        print(f"  {key}: {p['name']} ({p['rounds']} rounds × {p['attacks']} attacks)")

    print("\nAvailable models:")
    for key, m in MODELS.items():
        print(f"  {key}: {m['name']} (${m['cost_per_call']:.3f}/call)")

    print("\n" + "-"*50)

    # Выбор пресета
    preset = input("Preset (quick/standard/full) [quick]: ").strip() or "quick"
    if preset not in BENCHMARK_PRESETS:
        preset = "quick"

    # Выбор моделей
    print("\nВведи модели через запятую или Enter для default")

    default_attackers = ["gpt4o-mini", "gpt4o", "deepseek"]
    default_defenders = ["gpt4o-mini", "gpt4o", "deepseek"]

    attackers_input = input(f"Attackers [{','.join(default_attackers)}]: ").strip()
    if attackers_input:
        attackers = [a.strip() for a in attackers_input.split(",") if a.strip() in MODELS]
    else:
        attackers = default_attackers

    defenders_input = input(f"Defenders [{','.join(default_defenders)}]: ").strip()
    if defenders_input:
        defenders = [d.strip() for d in defenders_input.split(",") if d.strip() in MODELS]
    else:
        defenders = default_defenders

    run_benchmark(preset=preset, attackers=attackers, defenders=defenders)


if __name__ == "__main__":
    main()
