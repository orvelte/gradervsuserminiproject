"""SF2 arm configs: generated files are current, arms differ only where intended, settings come from N0."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CFG = REPO_ROOT / "structural_framing_v2" / "configs"
ARMS = ["SF2-G-LAX", "SF2-C-LAX", "SF2-G-NONE", "SF2-C-NONE"]


def load(a): return yaml.safe_load((CFG / f"{a}.yaml").read_text())


def test_generated_configs_are_current():
    r = subprocess.run([sys.executable, str(CFG / "build_sf2_arms.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_arms_differ_only_in_user_prompt_framing_and_condition():
    base = load(ARMS[0])
    for a in ARMS[1:]:
        c = load(a)
        assert c["agent"] == base["agent"] and c["environment"] == base["environment"] == "precommit_hook_sf2"
        assert c["prompts"]["system_prompt"] == base["prompts"]["system_prompt"]
        assert {k: v for k, v in c["task"].items() if k != "sf_framing"} == {k: v for k, v in base["task"].items() if k != "sf_framing"}


def test_settings_and_task_text_come_from_n0_and_the_system_prompt_changes_one_sentence():
    n0 = yaml.safe_load((REPO_ROOT / "configs/precommit_hook/N0_replication.yaml").read_text())
    core = n0["prompts"]["user_prompt"].strip()
    for a in ARMS:
        c = load(a)
        assert c["agent"] == n0["agent"]
        assert c["task"]["tools"] == n0["task"]["tools"] + ["ask_question"] and c["task"]["target_errors"] == 258
        assert c["prompts"]["user_prompt"].count(core) == 1
        sp, sp0 = c["prompts"]["system_prompt"], n0["prompts"]["system_prompt"]
        assert sp.replace("a bash tool, an apply_patch tool and an ask_question tool.", "a bash tool and apply_patch tool.") == sp0
        assert "ask_question" in sp


def test_both_openings_point_to_the_readme_with_one_matched_sentence():
    import importlib.util
    spec = importlib.util.spec_from_file_location("b", CFG / "build_sf2_arms.py"); B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
    assert abs(len(B.G_README.split()) - len(B.C_README.split())) <= 4 and "README" in B.G_README and "README" in B.C_README
    assert B.G_PRE.replace("\n" + B.G_README, "") == B.SF1.G_PRE and B.C_PRE.replace(" " + B.C_README, "") == B.SF1.C_PRE   # nothing else changed
    for a in ARMS:
        up = load(a)["prompts"]["user_prompt"]
        assert (B.G_README in up) != (B.C_README in up)
        assert up.index("README") < up.index("You are working on a Python data ingestion service")           # before the task text
        assert load(a)["condition"]["env_version"] == "2.1"


def test_lax_and_none_arms_differ_only_in_the_closing_sentence():
    for g in ("G", "C"):
        lax, none = load(f"SF2-{g}-LAX")["prompts"]["user_prompt"], load(f"SF2-{g}-NONE")["prompts"]["user_prompt"]
        assert lax.rsplit("\n\n", 1)[0] == none.rsplit("\n\n", 1)[0] and lax != none
        assert "exist" in lax.rsplit("\n\n", 1)[1] or "are there" in lax.rsplit("\n\n", 1)[1]
        assert "exist" not in none.rsplit("\n\n", 1)[1] and "check" not in none.rsplit("\n\n", 1)[1]
