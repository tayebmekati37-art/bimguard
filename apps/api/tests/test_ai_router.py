from app.ai.router import QuestionType, Router


def route(q):
    return Router().route(q)


def test_affected_by_vs_affects_pair():
    assert route("What is affected by A-101?") == QuestionType.AFFECTED_BY
    assert route("What does A-101 affect?") == QuestionType.AFFECTS


def test_affected_by_variants():
    assert route("which documents are affected by A-101") == QuestionType.AFFECTED_BY
    assert route("affected by A-101, what is?") == QuestionType.AFFECTED_BY


def test_affects_variants():
    assert route("what does S-201 impact") == QuestionType.AFFECTS
    assert route("what does A-101 affect") == QuestionType.AFFECTS


def test_status():
    assert route("status of S-201") == QuestionType.STATUS
    assert route("is M-301 stale?") == QuestionType.STATUS
    assert route("what state is Q-101 in") == QuestionType.STATUS


def test_validation():
    assert route("validation issues for A-101") == QuestionType.VALIDATION
    assert route("what is wrong with S-201") == QuestionType.VALIDATION
    assert route("problems with M-301") == QuestionType.VALIDATION


def test_dependencies():
    assert route("what depends on A-101") == QuestionType.DEPENDENCIES
    assert route("dependencies of S-201") == QuestionType.DEPENDENCIES
    assert route("what is related to M-301") == QuestionType.DEPENDENCIES


def test_summary_beats_status():
    assert route("summary of S-201 status") == QuestionType.SUMMARY
    assert route("summarize A-101") == QuestionType.SUMMARY


def test_unknown():
    assert route("hello") == QuestionType.UNKNOWN
    assert route("") == QuestionType.UNKNOWN
    assert route("   ") == QuestionType.UNKNOWN


def test_case_insensitive():
    assert route("STATUS OF A-101") == QuestionType.STATUS
    assert route("Is A-101 Stale") == QuestionType.STATUS