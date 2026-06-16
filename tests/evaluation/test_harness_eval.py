from evaluation.harness_eval import load_cases, run_cases


def test_harness_eval_cases_cover_required_categories():
    cases = load_cases()
    categories = {case.category for case in cases}
    languages = {case.language for case in cases if case.language}

    assert {"cache-poison", "path-list", "raw-code", "thin-evidence", "no-hit", "useful-answer"} <= categories
    assert {"python", "cpp", "typescript", "go", "rust", "java", "csharp"} <= languages


def test_harness_eval_passes_acceptance_thresholds():
    report = run_cases(load_cases())

    assert report.policy_cache_safety_pass_rate == 1.0
    assert report.multilingual_concrete_pass_rate >= 0.95
    assert report.failed == 0
