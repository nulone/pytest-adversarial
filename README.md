# pytest-adversarial

[![CI](https://github.com/nulone/pytest-adversarial/actions/workflows/ci.yml/badge.svg)](https://github.com/nulone/pytest-adversarial/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Generate adversarial pytest tests using LLM.

![Demo](demo.gif)

Attempts to find edge cases in your Python code by generating attack tests. Can also suggest fixes.

## What it does

```
Your code → LLM generates attacks → Tests that break your code → Export as pytest
```

**Example output:**
```
Found 6 potential issues:
├── parse_json: RecursionError on deeply nested input
├── merge_dicts: KeyError on circular references  
├── validate_schema: TypeError on None input
└── ...

Exported to: tests/test_adversarial.py
```

## Quick Start

```bash
# Install
pip install pytest-adversarial

# Set API key (choose one)
export OPENROUTER_API_KEY=your_key   # OpenRouter
export OPENAI_API_KEY=your_key       # OpenAI

# Run
pytest-adversarial
```

## How it works

1. **Analyze** — Extracts functions from your code using AST
2. **Attack** — LLM generates adversarial test cases targeting edge cases
3. **Verify** — Runs tests to confirm issues
4. **Export** — Saves successful attacks as pytest file
5. **Fix** — LLM suggests patches for found issues

## Modes

| Mode | Rounds | Attacks | Est. Cost |
|------|--------|---------|-----------|
| Quick | 5 | 3/round | ~$0.05 |
| Standard | 10 | 5/round | ~$0.15 |
| Thorough | 15 | 8/round | ~$0.40 |
| Premium (GPT-4o) | 10 | 5/round | ~$1.50 |
| Maximum | 20 | 10/round | ~$5.00 |

## Requirements

- Python 3.10+
- API key: OpenRouter or OpenAI
- ~$0.05-5.00 per run depending on mode

## Limitations

- Works best on pure functions
- LLM-generated tests may have false positives
- Not a replacement for professional security audit
- Requires API costs per run

## Example

```python
# Your code (target.py)
def parse_json(text: str) -> dict:
    return json.loads(text)

# pytest-adversarial generates:
def test_parse_json_overflow():
    """Deeply nested JSON causes RecursionError"""
    malicious = '{"a":' * 1000 + '1' + '}' * 1000
    with pytest.raises(RecursionError):
        parse_json(malicious)
```

## Project Structure

```
src/
├── drq.py      — Main runner
├── agents.py   — Attacker/Defender LLM agents
├── utils.py    — Function extraction (AST)
├── export.py   — Test export
└── config.py   — Model configuration

examples/
└── json_parser/ — Sample target code
```

## Cost

Uses OpenRouter or OpenAI API. Typical costs:
- Quick test: $0.03-0.08
- Standard run: $0.15-0.30
- Premium (GPT-4o): $1-2
- Models: GPT-4o-mini (default), DeepSeek, Claude Haiku

## License

MIT
