import importlib.util
from pathlib import Path


def test_persona_eval_rules_only():
    path = Path(__file__).parent / "evals" / "eval_persona.py"
    spec = importlib.util.spec_from_file_location("eval_persona", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    accuracy, wrongly_accepted = mod.report(mod.run(use_llm=False))
    assert accuracy >= 0.95
    assert wrongly_accepted == 0
