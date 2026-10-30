from evals.run import matches, summarize


def test_field_matching_rules():
    assert matches("professor_name", "Alexey Vyacheslavovich Gorshkov", "Alexey Gorshkov", {})
    assert matches("university", "Massachusetts Institute of Technology", "MIT", {"university_aliases": ["MIT"]})
    assert matches("stipend_amount", "38500", "38,500", {})
    assert matches("pte_accepted", None, None, {}) and not matches("pte_accepted", None, "yes", {})


def test_summary_splits_reviewed_and_counts_evidence():
    results = [{"id": "a", "kind": "faculty", "reviewed": True, "fields": {"x": {"ok": True}}, "claims": 4,
                "supported": 4, "seconds": 2, "tokens": 10},
               {"id": "b", "kind": "program", "reviewed": False, "fields": {"y": {"ok": False}}, "claims": 4,
                "supported": 2, "seconds": 4, "tokens": 10},
               {"id": "c", "error": "boom"}]
    s = summarize(results)
    assert s["errors"] == 1 and s["reviewed_field_accuracy"] == 1.0 and s["program_field_accuracy"] == 0.0
    assert s["evidence_coverage"] == 0.75
