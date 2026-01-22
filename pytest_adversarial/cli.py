#!/usr/bin/env python3
"""
pytest-adversarial — Adversarial testing with Digital Red Queen dynamics.

Key features:

1. RED QUEEN DYNAMICS:
   - New defenders must block ALL previous attackers
   - New attackers must defeat ALL previous defenders

2. MAP-ELITES:
   - Preserves attack diversity across categories
   - Not just "best attack", but "best in each category"

3. GENERALITY METRICS:
   - Measures: does defense work against unseen attacks?
   - Measures: does attack work against unseen defenses?

4. EVOLUTION:
   - Tracks genome lineage
   - Measures convergent evolution
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from .config import ModelConfig, get_api_config, MODEL_GPT4O_MINI
from .agents import Attacker, Defender, Attack
from .fitness import FitnessEvaluator
from .archive_v2 import MAPElitesArchive, DefenseArchive, AttackGenome, DefenseGenome


@dataclass
class DRQConfig:
    """DRQ configuration."""

    # Rounds and iterations
    n_rounds: int = 10
    attacks_per_round: int = 5

    # Archives
    max_attacks_per_niche: int = 3
    max_defenders: int = 50

    # Red Queen: how many previous to test against
    test_against_previous: int = 10

    # Models
    attacker_model: str = MODEL_GPT4O_MINI
    defender_model: str = MODEL_GPT4O_MINI

    # Paths
    target_file: str = "examples/json_parser/target.py"
    output_dir: str = "results/drq"

    # Cost (estimated)
    estimated_cost_per_call: float = 0.002  # $0.002 per call


class DRQRunner:
    """
    Main DRQ class.

    Implements Red Queen dynamics:
    - Attackers evolve to defeat defenders
    - Defenders evolve to block attackers
    - Both grow stronger through adversarial pressure
    """

    def __init__(self, config: DRQConfig):
        self.config = config

        # Check API
        api_config = get_api_config()
        if not api_config:
            raise ValueError("API key not set!")

        self.provider = api_config["provider"]

        # Models
        model_config = ModelConfig()
        model_config.attacker_model = config.attacker_model
        model_config.defender_model = config.defender_model

        self.attacker = Attacker(model_config)
        self.defender = Defender(model_config)
        self.evaluator = FitnessEvaluator()

        # Archives
        self.attack_archive = MAPElitesArchive(
            max_per_niche=config.max_attacks_per_niche
        )
        self.defense_archive = DefenseArchive(max_size=config.max_defenders)

        # Current code
        self.target_path = Path(config.target_file)
        self.current_code = self.target_path.read_text()
        self.original_code = self.current_code

        # Metrics
        self.metrics = {
            "rounds": [],
            "generality_over_time": [],
            "robustness_over_time": [],
            "api_calls": 0,
            "estimated_cost": 0.0,
        }

        # Output
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict:
        """Runs DRQ evolution."""

        print("=" * 70)
        print("🔴🟢 pytest-adversarial")
        print("=" * 70)
        print(f"Provider: {self.provider}")
        print(f"Attacker: {self.config.attacker_model}")
        print(f"Defender: {self.config.defender_model}")
        print(f"Rounds: {self.config.n_rounds}")
        print(f"Attacks per round: {self.config.attacks_per_round}")
        print("=" * 70)

        start_time = time.time()

        for round_num in range(1, self.config.n_rounds + 1):
            round_stats = self._run_round(round_num)
            self.metrics["rounds"].append(round_stats)

            # Save intermediate results
            if round_num % 2 == 0:
                self._save_checkpoint(round_num)

        total_time = time.time() - start_time

        # Final metrics
        self.metrics["total_time_sec"] = total_time
        self.metrics["final_robustness"] = self._measure_final_robustness()
        self.metrics["final_generality"] = self._measure_final_generality()

        # Save results
        self._save_results()

        return self.metrics

    def _run_round(self, round_num: int) -> dict:
        """One round of DRQ."""

        print(f"\n{'=' * 70}")
        print(f"🔄 ROUND {round_num}/{self.config.n_rounds}")
        print(f"{'=' * 70}")

        round_stats = {
            "round": round_num,
            "attacks_generated": 0,
            "attacks_successful": 0,
            "defense_improved": False,
            "new_robustness": 0.0,
        }

        # ═══════════════════════════════════════════════════════════
        # PHASE 1: ATTACK
        # Generate new attacks, test against current defense
        # ═══════════════════════════════════════════════════════════

        print("\n🔴 ATTACKER PHASE")
        print(f"   Generating {self.config.attacks_per_round} attacks...")

        successful_attacks = []

        for i in range(self.config.attacks_per_round):
            # Get diverse previous attacks for context
            previous = [
                Attack(
                    test_code=g.code,
                    description=g.description,
                    attack_type=g.attack_type,
                )
                for g in self.attack_archive.get_diverse_sample(5)
            ]

            # Generate attack
            attack = self.attacker.generate_attack(
                target_code=self.current_code,
                previous_attacks=previous,
                failed_attacks=[],
            )
            self.metrics["api_calls"] += 1

            if not attack:
                print(f"      ⚠️  Attack {i + 1}: failed to parse response")
                continue

            round_stats["attacks_generated"] += 1

            # Test against current defense
            result = self.evaluator.evaluate_attack(self.current_code, attack)

            # DEBUG: show test result
            print(
                f"      🔍 Attack {i + 1} [{attack.attack_type}]: score={result.score}, passed={result.passed}, failed={result.failed}"
            )
            if result.score == 0.0:
                # Show attack code to understand why it failed
                code_preview = attack.test_code.replace("\n", " ")[:100]
                print(f"         Code: {code_preview}...")
            if result.errors:
                print(f"         Errors: {result.errors[0][:80]}")

            if result.score >= 0.5:  # Attack successful
                # Determine error type
                error_type = "unknown"
                if result.errors:
                    error_msg = result.errors[0]
                    for et in MAPElitesArchive.ERROR_TYPES:
                        if et in error_msg:
                            error_type = et
                            break

                # Create genome
                genome = AttackGenome(
                    code=attack.test_code,
                    attack_type=attack.attack_type,
                    error_type=error_type,
                    description=attack.description,
                    fitness=result.score,
                    generation=round_num,
                )

                # RED QUEEN: Test against previous defenders
                genome = self._test_attack_generality(genome)

                # Add to archive
                if self.attack_archive.add(genome):
                    successful_attacks.append(attack)
                    round_stats["attacks_successful"] += 1
                    print(f"   ✅ [{attack.attack_type}] {attack.description[:50]}...")
                    print(f"      Generality: {genome.generality:.1%}")

        if not successful_attacks:
            print("   ⚠️  No successful attacks this round")

            # EVOLUTION: If no new attacks, mutate existing ones
            all_attacks = self.attack_archive.get_all()
            if len(all_attacks) >= 2:
                print("   🧬 Trying mutation/crossover...")

                # Try mutating best attack
                best = max(all_attacks, key=lambda g: g.fitness)
                best_attack = Attack(
                    test_code=best.code,
                    description=best.description,
                    attack_type=best.attack_type,
                )

                mutated = self.attacker.mutate_attack(best_attack)
                self.metrics["api_calls"] += 1

                if mutated:
                    result = self.evaluator.evaluate_attack(self.current_code, mutated)
                    if result.score >= 0.5:
                        genome = AttackGenome(
                            code=mutated.test_code,
                            attack_type=mutated.attack_type,
                            error_type="mutated",
                            description=mutated.description,
                            fitness=result.score,
                            generation=round_num,
                        )
                        if self.attack_archive.add(genome):
                            print(f"   ✅ Mutation successful: {mutated.attack_type}")
                            successful_attacks.append(mutated)

                # Try crossover of two random attacks
                if len(all_attacks) >= 2 and not successful_attacks:
                    import random

                    a1, a2 = random.sample(all_attacks, 2)
                    attack1 = Attack(
                        test_code=a1.code,
                        description=a1.description,
                        attack_type=a1.attack_type,
                    )
                    attack2 = Attack(
                        test_code=a2.code,
                        description=a2.description,
                        attack_type=a2.attack_type,
                    )

                    crossed = self.attacker.crossover_attacks(attack1, attack2)
                    self.metrics["api_calls"] += 1

                    if crossed:
                        result = self.evaluator.evaluate_attack(
                            self.current_code, crossed
                        )
                        if result.score >= 0.5:
                            genome = AttackGenome(
                                code=crossed.test_code,
                                attack_type=crossed.attack_type,
                                error_type="crossover",
                                description=crossed.description,
                                fitness=result.score,
                                generation=round_num,
                            )
                            if self.attack_archive.add(genome):
                                print(
                                    f"   ✅ Crossover successful: {crossed.attack_type}"
                                )
                                successful_attacks.append(crossed)

        # ═══════════════════════════════════════════════════════════
        # PHASE 2: DEFENSE
        # Defender must block ALL attacks in archive
        # ═══════════════════════════════════════════════════════════

        print("\n🟢 DEFENDER PHASE")

        # Get diverse sample of attacks to defend against
        attacks_to_defend = self.attack_archive.get_diverse_sample(
            self.config.test_against_previous
        )

        if not attacks_to_defend:
            print("   ⚠️  No attacks to defend against")
            return round_stats

        print(f"   Defending against {len(attacks_to_defend)} attacks...")

        # Convert to Attack for defender
        failing_attacks = [
            Attack(
                test_code=g.code, description=g.description, attack_type=g.attack_type
            )
            for g in attacks_to_defend
        ]

        # Generate defense
        defense = self.defender.generate_defense(
            target_code=self.current_code,
            failing_tests=failing_attacks[:3],  # Show top 3
            previous_fixes=[],
        )
        self.metrics["api_calls"] += 1

        if not defense:
            print("   ❌ Defender failed to generate defense")
            return round_stats

        # RED QUEEN: Test against ALL attacks in archive
        all_attacks = self.attack_archive.get_all()
        blocks_count = 0

        print(f"   Testing defense against {len(all_attacks)} attacks...")

        # Exceptions that count as "defense" (code handled edge case correctly)
        DEFENSIVE_PATTERNS = [
            "ValueError",
            "TypeError",
            "Input must be",
            "Input cannot be",
            "Input string cannot",
            "must be a string",
            "must be a dict",
            "cannot be empty",
            "cannot be None",
            "Invalid input",
        ]

        for genome in all_attacks:
            attack = Attack(
                test_code=genome.code,
                description=genome.description,
                attack_type=genome.attack_type,
            )

            # Attack is "blocked" if test PASSES (doesn't crash) on new code
            result = self.evaluator.evaluate_attack(defense.fixed_code, attack)

            # Check: is this a raw crash or defensive exception?
            is_defensive = False
            if result.errors:
                error_msg = str(result.errors[0]) if result.errors else ""
                for pattern in DEFENSIVE_PATTERNS:
                    if pattern in error_msg:
                        is_defensive = True
                        break

            # score < 0.5 = test passed (attack failed)
            # is_defensive = code threw descriptive exception (good!)
            if result.score < 0.5:
                blocks_count += 1
                print(f"      ✓ Blocked: {genome.attack_type}")
            elif is_defensive:
                blocks_count += 1
                print(f"      ✓ Handled: {genome.attack_type} (defensive exception)")
            else:
                print(
                    f"      ✗ Crashed: {genome.attack_type} - {result.errors[0][:50] if result.errors else 'unknown'}"
                )

        robustness = blocks_count / len(all_attacks) if all_attacks else 1.0

        # Create defense genome
        defense_genome = DefenseGenome(
            code=defense.fixed_code,
            description=defense.explanation,
            fitness=robustness,
            blocks_count=blocks_count,
            tested_against=len(all_attacks),
            generation=round_num,
        )

        # Compare with current best defense
        current_best = self.defense_archive.get_best()
        current_robustness = current_best.robustness if current_best else 0.0

        # Add to archive
        self.defense_archive.add(defense_genome)

        # Update current code ONLY if robustness improved
        if robustness > current_robustness:
            self.current_code = defense.fixed_code
            round_stats["defense_improved"] = True
            print(
                f"   ✅ Defense improved! {current_robustness:.1%} → {robustness:.1%}"
            )
        elif robustness == current_robustness and robustness > 0:
            print(f"   📊 Robustness: {robustness:.1%} (same as current)")
        else:
            print(
                f"   📊 Robustness: {robustness:.1%} (not better than {current_robustness:.1%})"
            )

        round_stats["new_robustness"] = robustness

        # Update metrics
        self.metrics["robustness_over_time"].append(robustness)
        self.metrics["estimated_cost"] = (
            self.metrics["api_calls"] * self.config.estimated_cost_per_call
        )

        # Round stats
        print(f"\n📊 Round {round_num} stats:")
        print(f"   Attacks in archive: {len(self.attack_archive.get_all())}")
        print(f"   Niches filled: {len(self.attack_archive.archive)}")
        print(f"   API calls: {self.metrics['api_calls']}")
        print(f"   ~Cost: ${self.metrics['estimated_cost']:.2f}")

        return round_stats

    def _test_attack_generality(self, genome: AttackGenome) -> AttackGenome:
        """
        RED QUEEN: Tests attack against previous defenders.

        Generality = fraction of defenders the attack defeats.
        """
        defenders = self.defense_archive.get_all()

        if not defenders:
            return genome

        # Same defensive exception patterns
        DEFENSIVE_PATTERNS = [
            "ValueError",
            "TypeError",
            "Input must be",
            "Input cannot be",
            "Input string cannot",
            "must be a string",
            "must be a dict",
            "cannot be empty",
            "cannot be None",
            "Invalid input",
        ]

        # Test against last N defenders
        test_defenders = defenders[-self.config.test_against_previous :]

        defeats = 0
        for defense in test_defenders:
            attack = Attack(
                test_code=genome.code,
                description=genome.description,
                attack_type=genome.attack_type,
            )
            result = self.evaluator.evaluate_attack(defense.code, attack)

            # Attack "wins" only if NOT a defensive exception
            is_defensive = False
            if result.errors:
                error_msg = str(result.errors[0]) if result.errors else ""
                for pattern in DEFENSIVE_PATTERNS:
                    if pattern in error_msg:
                        is_defensive = True
                        break

            # Attack wins = code crashes AND not a defensive exception
            if result.score >= 0.5 and not is_defensive:
                defeats += 1

        genome.defeats_count = defeats
        genome.tested_against = len(test_defenders)

        return genome

    def _measure_final_robustness(self) -> float:
        """Measures final robustness against all attacks."""
        all_attacks = self.attack_archive.get_all()
        if not all_attacks:
            return 1.0

        # Same patterns as main loop
        DEFENSIVE_PATTERNS = [
            "ValueError",
            "TypeError",
            "Input must be",
            "Input cannot be",
            "Input string cannot",
            "must be a string",
            "must be a dict",
            "cannot be empty",
            "cannot be None",
            "Invalid input",
        ]

        blocks = 0
        for genome in all_attacks:
            attack = Attack(
                test_code=genome.code,
                description=genome.description,
                attack_type=genome.attack_type,
            )
            result = self.evaluator.evaluate_attack(self.current_code, attack)

            # Check defensive exceptions
            is_defensive = False
            if result.errors:
                error_msg = str(result.errors[0]) if result.errors else ""
                for pattern in DEFENSIVE_PATTERNS:
                    if pattern in error_msg:
                        is_defensive = True
                        break

            if result.score < 0.5 or is_defensive:
                blocks += 1

        return blocks / len(all_attacks)

    def _measure_final_generality(self) -> float:
        """Measures average attack generality."""
        all_attacks = self.attack_archive.get_all()
        if not all_attacks:
            return 0.0

        return sum(g.generality for g in all_attacks) / len(all_attacks)

    def _save_checkpoint(self, round_num: int) -> None:
        """Saves intermediate results."""
        checkpoint = {
            "round": round_num,
            "current_code": self.current_code,
            "attack_stats": self.attack_archive.get_stats(),
            "defense_stats": self.defense_archive.get_stats(),
            "metrics": self.metrics,
        }

        path = self.output_dir / f"checkpoint_round_{round_num}.json"
        path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False))

    def _save_results(self) -> None:
        """Saves final results."""

        # Save evolved code
        evolved_path = self.target_path.parent / "target_evolved_drq.py"
        evolved_path.write_text(self.current_code)

        # Save archives
        self.attack_archive.save(self.output_dir / "attack_archive.json")

        # Save metrics
        results = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "n_rounds": self.config.n_rounds,
                "attacks_per_round": self.config.attacks_per_round,
                "attacker_model": self.config.attacker_model,
                "defender_model": self.config.defender_model,
            },
            "metrics": self.metrics,
            "attack_archive_stats": self.attack_archive.get_stats(),
            "defense_archive_stats": self.defense_archive.get_stats(),
        }

        results_path = self.output_dir / "results.json"
        results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

        print(f"\n{'=' * 70}")
        print("📊 FINAL RESULTS")
        print(f"{'=' * 70}")
        print(f"Robustness: {self.metrics['final_robustness']:.1%}")
        print(f"Attacks in archive: {len(self.attack_archive.get_all())}")
        print(f"Niches filled: {len(self.attack_archive.archive)}")
        print(f"API calls: {self.metrics['api_calls']}")
        print(f"Cost: ${self.metrics['estimated_cost']:.2f}")
        print(f"\n💾 Results: {self.output_dir}")
        print(f"💾 Evolved code: {evolved_path}")


def main():
    """Entry point."""

    # Enable logging for debug
    import logging
    import sys

    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

    # Check API
    if not get_api_config():
        print("❌ API key not set!")
        print("\nOpenRouter (recommended):")
        print("  export OPENROUTER_API_KEY='sk-or-...'")
        sys.exit(1)

    # Presets
    PRESETS = {
        "quick": {
            "name": "Quick Test",
            "rounds": 5,
            "attacks": 3,
            "attacker": MODEL_GPT4O_MINI,
            "defender": MODEL_GPT4O_MINI,
            "cost": "~$0.05",
        },
        "standard": {
            "name": "Standard",
            "rounds": 10,
            "attacks": 5,
            "attacker": MODEL_GPT4O_MINI,
            "defender": MODEL_GPT4O_MINI,
            "cost": "~$0.15",
        },
        "thorough": {
            "name": "Thorough",
            "rounds": 15,
            "attacks": 8,
            "attacker": MODEL_GPT4O_MINI,
            "defender": MODEL_GPT4O_MINI,
            "cost": "~$0.40",
        },
        "premium": {
            "name": "Premium (GPT-4o)",
            "rounds": 10,
            "attacks": 5,
            "attacker": "openai/gpt-4o",  # Better at finding bugs
            "defender": "openai/gpt-4o",  # Better at fixing
            "cost": "~$1.50",
        },
        "max": {
            "name": "Maximum (GPT-4o + More Rounds)",
            "rounds": 20,
            "attacks": 10,
            "attacker": "openai/gpt-4o",
            "defender": "openai/gpt-4o",
            "cost": "~$5.00",
        },
    }

    # CLI selection
    print("=" * 70)
    print("🔴🟢 pytest-adversarial")
    print("=" * 70)
    print("\nSelect mode:\n")

    for i, (key, preset) in enumerate(PRESETS.items(), 1):
        print(f"  {i}. {preset['name']}")
        print(
            f"     {preset['rounds']} rounds × {preset['attacks']} attacks | {preset['cost']}"
        )
        print()

    try:
        choice = input("Enter number (1-5) or press Enter for standard: ").strip()
        if not choice:
            choice = "2"

        preset_keys = list(PRESETS.keys())
        preset_key = preset_keys[int(choice) - 1]
        preset = PRESETS[preset_key]
    except (ValueError, IndexError):
        preset = PRESETS["standard"]
        preset_key = "standard"

    print(f"\n✅ Selected mode: {preset['name']}")
    print(f"   Estimated cost: {preset['cost']}\n")

    # Run DRQ
    config = DRQConfig(
        n_rounds=preset["rounds"],
        attacks_per_round=preset["attacks"],
        attacker_model=preset["attacker"],
        defender_model=preset["defender"],
        estimated_cost_per_call=0.01 if "gpt-4o" in preset["attacker"] else 0.002,
    )

    runner = DRQRunner(config)
    runner.run()

    print("\n✅ Complete!")


if __name__ == "__main__":
    main()
