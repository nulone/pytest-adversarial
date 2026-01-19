#!/usr/bin/env python3
"""
Визуализация результатов DRQ.

Генерирует графики для README:
1. Robustness over rounds
2. Attack diversity (MAP-Elites coverage)
3. Generality evolution
"""

import json
import sys
from pathlib import Path

# Проверяем matplotlib
try:
    import matplotlib.pyplot as plt
except ImportError:
    print("Установи matplotlib: pip install matplotlib")
    sys.exit(1)


def load_results(results_dir: Path) -> dict:
    """Загружает результаты DRQ."""
    results_path = results_dir / "results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"Нет результатов: {results_path}")

    return json.loads(results_path.read_text())


def plot_robustness(results: dict, output_dir: Path) -> None:
    """График robustness по раундам."""

    robustness = results["metrics"].get("robustness_over_time", [])

    if not robustness:
        print("Нет данных robustness")
        return

    plt.figure(figsize=(10, 6))
    plt.plot(range(1, len(robustness) + 1), robustness, 'g-o', linewidth=2, markersize=8)
    plt.fill_between(range(1, len(robustness) + 1), robustness, alpha=0.3, color='green')

    plt.xlabel('Round', fontsize=12)
    plt.ylabel('Robustness', fontsize=12)
    plt.title('Defense Robustness Evolution', fontsize=14)
    plt.ylim(0, 1.05)
    plt.grid(True, alpha=0.3)

    # Аннотации
    if robustness:
        plt.annotate(f'Start: {robustness[0]:.1%}',
                    xy=(1, robustness[0]),
                    xytext=(1.5, robustness[0] + 0.1),
                    fontsize=10)
        plt.annotate(f'Final: {robustness[-1]:.1%}',
                    xy=(len(robustness), robustness[-1]),
                    xytext=(len(robustness) - 1, robustness[-1] + 0.1),
                    fontsize=10)

    plt.tight_layout()
    plt.savefig(output_dir / "robustness_evolution.png", dpi=150)
    plt.close()
    print(f"✅ Saved: {output_dir / 'robustness_evolution.png'}")


def plot_attack_coverage(results: dict, output_dir: Path) -> None:
    """Heatmap покрытия MAP-Elites."""

    coverage = results.get("attack_archive_stats", {}).get("coverage_by_type", {})

    if not coverage:
        print("Нет данных coverage")
        return

    # Фильтруем непустые
    coverage = {k: v for k, v in coverage.items() if v > 0}

    if not coverage:
        print("Все типы атак пусты")
        return

    plt.figure(figsize=(10, 6))

    types = list(coverage.keys())
    counts = list(coverage.values())

    colors = plt.cm.Reds([c / max(counts) for c in counts])
    bars = plt.barh(types, counts, color=colors)

    plt.xlabel('Number of Attacks', fontsize=12)
    plt.ylabel('Attack Type', fontsize=12)
    plt.title('MAP-Elites Coverage by Attack Type', fontsize=14)

    # Добавляем значения на бары
    for bar, count in zip(bars, counts):
        plt.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                str(count), va='center', fontsize=10)

    plt.tight_layout()
    plt.savefig(output_dir / "attack_coverage.png", dpi=150)
    plt.close()
    print(f"✅ Saved: {output_dir / 'attack_coverage.png'}")


def plot_cost_over_time(results: dict, output_dir: Path) -> None:
    """График стоимости API вызовов."""

    rounds = results["metrics"].get("rounds", [])

    if not rounds:
        print("Нет данных по раундам")
        return

    # Считаем кумулятивную стоимость
    cost_per_call = results["config"].get("estimated_cost_per_call", 0.002)

    cumulative_calls = []
    total = 0
    for r in rounds:
        # Примерно 6 вызовов на раунд (5 атак + 1 защита)
        total += r.get("attacks_generated", 0) + 1
        cumulative_calls.append(total)

    costs = [c * cost_per_call for c in cumulative_calls]

    plt.figure(figsize=(10, 6))
    plt.plot(range(1, len(costs) + 1), costs, 'b-o', linewidth=2)
    plt.fill_between(range(1, len(costs) + 1), costs, alpha=0.3, color='blue')

    plt.xlabel('Round', fontsize=12)
    plt.ylabel('Cumulative Cost ($)', fontsize=12)
    plt.title('API Cost Over Time', fontsize=14)
    plt.grid(True, alpha=0.3)

    if costs:
        plt.annotate(f'Total: ${costs[-1]:.2f}',
                    xy=(len(costs), costs[-1]),
                    xytext=(len(costs) - 2, costs[-1] + 0.5),
                    fontsize=12, fontweight='bold')

    plt.tight_layout()
    plt.savefig(output_dir / "cost_evolution.png", dpi=150)
    plt.close()
    print(f"✅ Saved: {output_dir / 'cost_evolution.png'}")


def plot_summary(results: dict, output_dir: Path) -> None:
    """Сводный график."""

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 1. Robustness
    ax1 = axes[0, 0]
    robustness = results["metrics"].get("robustness_over_time", [])
    if robustness:
        ax1.plot(range(1, len(robustness) + 1), robustness, 'g-o', linewidth=2)
        ax1.fill_between(range(1, len(robustness) + 1), robustness, alpha=0.3, color='green')
        ax1.set_ylim(0, 1.05)
    ax1.set_xlabel('Round')
    ax1.set_ylabel('Robustness')
    ax1.set_title('Defense Robustness')
    ax1.grid(True, alpha=0.3)

    # 2. Attack coverage
    ax2 = axes[0, 1]
    coverage = results.get("attack_archive_stats", {}).get("coverage_by_type", {})
    coverage = {k: v for k, v in coverage.items() if v > 0}
    if coverage:
        ax2.barh(list(coverage.keys()), list(coverage.values()), color='red', alpha=0.7)
    ax2.set_xlabel('Count')
    ax2.set_title('Attack Types Found')

    # 3. Round stats
    ax3 = axes[1, 0]
    rounds = results["metrics"].get("rounds", [])
    if rounds:
        attacks_gen = [r.get("attacks_generated", 0) for r in rounds]
        attacks_succ = [r.get("attacks_successful", 0) for r in rounds]
        x = range(1, len(rounds) + 1)
        ax3.bar(x, attacks_gen, alpha=0.5, label='Generated', color='gray')
        ax3.bar(x, attacks_succ, alpha=0.8, label='Successful', color='red')
        ax3.legend()
    ax3.set_xlabel('Round')
    ax3.set_ylabel('Attacks')
    ax3.set_title('Attack Success Rate')

    # 4. Summary text
    ax4 = axes[1, 1]
    ax4.axis('off')

    summary_text = f"""
    DRQ Summary
    ═══════════════════════════

    Rounds: {results['config'].get('n_rounds', 'N/A')}

    Final Robustness: {results['metrics'].get('final_robustness', 0):.1%}

    Total Attacks: {results.get('attack_archive_stats', {}).get('total_genomes', 0)}

    Niches Covered: {results.get('attack_archive_stats', {}).get('total_niches', 0)}

    API Calls: {results['metrics'].get('api_calls', 0)}

    Estimated Cost: ${results['metrics'].get('estimated_cost', 0):.2f}
    """

    ax4.text(0.1, 0.5, summary_text, fontsize=14, family='monospace',
             verticalalignment='center', transform=ax4.transAxes,
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.suptitle('Digital Red Queen — Results Summary', fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_dir / "drq_summary.png", dpi=150)
    plt.close()
    print(f"✅ Saved: {output_dir / 'drq_summary.png'}")


def main():
    """Генерирует все графики."""

    results_dir = Path("results/drq")

    if not results_dir.exists():
        print(f"❌ Директория не найдена: {results_dir}")
        print("Сначала запусти: python src/drq.py")
        sys.exit(1)

    print("📊 Генерация графиков...\n")

    try:
        results = load_results(results_dir)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Создаём директорию для графиков
    plots_dir = results_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    # Генерируем графики
    plot_robustness(results, plots_dir)
    plot_attack_coverage(results, plots_dir)
    plot_cost_over_time(results, plots_dir)
    plot_summary(results, plots_dir)

    print(f"\n✅ Все графики сохранены в: {plots_dir}")


if __name__ == "__main__":
    main()
