# pytest-adversarial

[![PyPI version](https://img.shields.io/pypi/v/pytest-adversarial.svg)](https://pypi.org/project/pytest-adversarial/)
[![Python](https://img.shields.io/pypi/pyversions/pytest-adversarial.svg)](https://pypi.org/project/pytest-adversarial/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

LLM-powered adversarial test generation for Python using Quality-Diversity algorithms.

## Installation

```bash
pip install pytest-adversarial
```

## Quick Example

Test a JSON parser for edge cases:

```python
# target.py
import json

def parse_json(text: str) -> dict:
    """Parse JSON string."""
    return json.loads(text)
```

Run adversarial testing:

```bash
pytest-adversarial examples/json_parser/target.py --rounds 10
```

The tool will automatically:
- Generate adversarial test inputs using LLMs
- Find edge cases that crash your code
- Evolve attacks using Quality-Diversity search
- Report robustness metrics and discovered vulnerabilities

Sample output:
```
Round 5/10 | Robustness: 73.2% | Attacks: 42 | Types: 8
Found: malformed_unicode, extreme_nesting, special_chars...
```

## Documentation

For detailed usage, examples, and advanced features, visit:
**[github.com/nulone/pytest-adversarial](https://github.com/nulone/pytest-adversarial)**

## Requirements

- Python 3.10+
- OpenAI API key (set `OPENROUTER_API_KEY` environment variable)

## License

MIT License - see GitHub repository for details.
