"""Shared test helpers. Case classes live in test_*.py so pytest collects them."""
import json
import os
import tempfile


def make_cfg(**over):
    from super import config as C

    root = tempfile.mkdtemp(prefix="super-test-")
    state = os.path.join(root, ".super")
    cfg = json.loads(json.dumps(C.DEFAULTS))
    cfg["_config_path"] = os.path.join(root, "super.config.json")
    cfg["_root"] = root
    cfg["state_dir"] = state
    cfg["envelope"]["best_of_n"] = 1
    for k, v in over.items():
        cfg[k] = v
    os.makedirs(state, exist_ok=True)
    # Pre-seed token to avoid generation in tests.
    cfg["server"]["token"] = "test-token"
    with open(os.path.join(state, ".token"), "w") as f:
        f.write("test-token")
    return cfg, root
