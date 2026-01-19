"""
Конфигурация ACH (Adversarial Code Hardening)

Поддерживает:
- NanoGPT (https://nano-gpt.com)
- OpenRouter (https://openrouter.ai) — РЕКОМЕНДУЕТСЯ, быстрее
- OpenAI напрямую
"""

from dataclasses import dataclass, field
import os


# ═══════════════════════════════════════════════════════════════
# API ПРОВАЙДЕРЫ
# ═══════════════════════════════════════════════════════════════

API_NANOGPT = "https://nano-gpt.com/api/v1"
API_OPENROUTER = "https://openrouter.ai/api/v1"
API_OPENAI = "https://api.openai.com/v1"


# ═══════════════════════════════════════════════════════════════
# МОДЕЛИ
# ═══════════════════════════════════════════════════════════════

# OpenRouter модели (рекомендуется — быстрее)
MODEL_GPT4O_MINI = "openai/gpt-4o-mini"           # $0.15/$0.60 за 1M
MODEL_DEEPSEEK_CHAT = "deepseek/deepseek-chat"    # $0.14/$0.28 за 1M
MODEL_CLAUDE_HAIKU = "anthropic/claude-3-haiku"   # $0.25/$1.25 за 1M
MODEL_LLAMA_70B = "meta-llama/llama-3.1-70b-instruct"  # Бесплатно!

# Премиум
MODEL_CLAUDE_SONNET = "anthropic/claude-3.5-sonnet"
MODEL_GPT4O = "openai/gpt-4o"


def get_api_config():
    """Определяет какой API использовать по переменным окружения."""

    if os.environ.get("OPENROUTER_API_KEY"):
        return {
            "api_key": os.environ["OPENROUTER_API_KEY"],
            "base_url": API_OPENROUTER,
            "provider": "OpenRouter",
        }
    elif os.environ.get("NANOGPT_API_KEY"):
        return {
            "api_key": os.environ["NANOGPT_API_KEY"],
            "base_url": API_NANOGPT,
            "provider": "NanoGPT",
        }
    elif os.environ.get("OPENAI_API_KEY"):
        return {
            "api_key": os.environ["OPENAI_API_KEY"],
            "base_url": API_OPENAI,
            "provider": "OpenAI",
        }
    else:
        return None


@dataclass
class ModelConfig:
    """Настройки LLM моделей."""

    # API (определяется автоматически)
    api_base_url: str = ""
    api_key: str = ""
    provider: str = ""

    # Модели
    attacker_model: str = MODEL_GPT4O_MINI
    attacker_temperature: float = 1.0

    defender_model: str = MODEL_GPT4O_MINI
    defender_temperature: float = 0.5

    # Общие
    max_tokens: int = 2000
    timeout: int = 60

    def __post_init__(self):
        config = get_api_config()
        if config:
            self.api_base_url = config["base_url"]
            self.api_key = config["api_key"]
            self.provider = config["provider"]


@dataclass
class DRQConfig:
    """Настройки алгоритма DRQ."""
    n_rounds: int = 5
    n_iterations: int = 20
    use_map_elites: bool = False
    archive_size: int = 50
    fitness_threshold: float = 0.8
    history_length: int = 10


@dataclass
class ExperimentConfig:
    """Настройки эксперимента."""
    target_dir: str = "examples/json_parser"
    output_dir: str = "results"
    log_level: str = "INFO"
    save_every: int = 5
    seed: int = 42


@dataclass
class Config:
    """Главный конфиг."""
    model: ModelConfig = field(default_factory=ModelConfig)
    drq: DRQConfig = field(default_factory=DRQConfig)
    experiment: ExperimentConfig = field(default_factory=ExperimentConfig)


# ═══════════════════════════════════════════════════════════════
# ПРЕСЕТЫ
# ═══════════════════════════════════════════════════════════════

PRESET_FREE = Config(
    model=ModelConfig(
        attacker_model=MODEL_LLAMA_70B,
        defender_model=MODEL_LLAMA_70B,
    ),
    drq=DRQConfig(n_rounds=3),
)

PRESET_BUDGET = Config(
    model=ModelConfig(
        attacker_model=MODEL_DEEPSEEK_CHAT,
        defender_model=MODEL_DEEPSEEK_CHAT,
    ),
    drq=DRQConfig(n_rounds=5),
)

PRESET_BALANCED = Config(
    model=ModelConfig(
        attacker_model=MODEL_GPT4O_MINI,
        defender_model=MODEL_GPT4O_MINI,
    ),
    drq=DRQConfig(n_rounds=5),
)

PRESET_DEBUG = Config(
    model=ModelConfig(
        attacker_model=MODEL_GPT4O_MINI,
        defender_model=MODEL_GPT4O_MINI,
    ),
    drq=DRQConfig(n_rounds=2),
)
