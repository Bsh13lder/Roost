from pathlib import Path

from roost.config import load_config


def test_tests_never_see_real_dirs():
    cfg = load_config()
    real = [Path("~/Roost").expanduser(), Path("/Users/blckit/Desktop/Code_Projects/lazyclaw/data")]
    for p in (cfg.database_dir, cfg.desks_dir):
        assert not any(p.resolve().is_relative_to(r.resolve()) for r in real)
