"""Unit tests for core/position.py's pos_group() — shared position-group
classifier for both FBref-style and WhoScored-style position strings."""
import math

from core.position import pos_group


def test_fbref_codes():
    assert pos_group("FW") == "attacker"
    assert pos_group("MF") == "midfielder"
    assert pos_group("DF") == "defender"
    assert pos_group("GK") == "goalkeeper"


def test_fbref_compound_code_uses_first_part():
    assert pos_group("DF,MF") == "defender"
    assert pos_group("MF,FW") == "midfielder"


def test_whoscored_exact_codes():
    assert pos_group("gk") == "goalkeeper"
    assert pos_group("fw") == "attacker"


def test_whoscored_defensive_and_attacking_mid_before_defender_midfielder():
    # DMC/AMC must resolve to midfielder, not get caught by the plain "d"/"m"
    # prefix checks first — this is the exact bug the prefix ORDER guards against.
    assert pos_group("DMC") == "midfielder"
    assert pos_group("DML") == "midfielder"
    assert pos_group("DMR") == "midfielder"
    assert pos_group("AMC") == "midfielder"
    assert pos_group("AML") == "midfielder"
    assert pos_group("AMR") == "midfielder"


def test_whoscored_plain_defender_and_midfielder_codes():
    assert pos_group("DC") == "defender"
    assert pos_group("DL") == "defender"
    assert pos_group("DR") == "defender"
    assert pos_group("MC") == "midfielder"
    assert pos_group("ML") == "midfielder"
    assert pos_group("MR") == "midfielder"


def test_whoscored_forward_codes():
    assert pos_group("FWL") == "attacker"
    assert pos_group("FWR") == "attacker"


def test_case_insensitive():
    assert pos_group("dmc") == "midfielder"
    assert pos_group("Fw") == "attacker"


def test_full_word_fallback():
    assert pos_group("Forward") == "attacker"
    assert pos_group("Goalkeeper") == "goalkeeper"
    assert pos_group("Centre Back") == "defender"


def test_unrecognized_and_missing_input_defaults_to_attacker():
    assert pos_group("Sub") == "attacker"
    assert pos_group("") == "attacker"
    assert pos_group(None) == "attacker"
    assert pos_group(float("nan")) == "attacker"
    assert pos_group(math.nan) == "attacker"
