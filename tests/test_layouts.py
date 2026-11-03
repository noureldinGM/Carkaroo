import numpy as np

from agv_brain.dataset import generate
from agv_brain.layouts import _detectable, layout_pool
from agv_brain.models import load_settings
from agv_brain.simulator import load_context


def test_random_layouts_are_valid():
    for ctx in layout_pool(40, seed=5, base=load_settings()):
        fmap = ctx.fmap
        ends = [n for n in fmap.nodes if len(fmap.neighbors(n)) == 1]
        # racks, stations and the dock are line ends; junctions are T/cross/L
        for node in fmap.nodes.values():
            if node.type == "junction":
                edges = {frozenset((node.id, nb)) for nb in fmap.neighbors(node.id)}
                pos = {n.id: (n.x, n.y) for n in fmap.nodes.values()}
                assert _detectable(node.id, edges, pos)
            else:
                assert node.id in ends
        # every material has its rack, every end can reach every other end
        for m in ctx.settings.materials.values():
            assert fmap.nodes[m.rack].type == "rack"
        for a in ends:
            for b in ends:
                fmap.route(a, b, fmap.arrival_heading(a))


_FINGERPRINT = """
import numpy as np
from agv_brain.layouts import layout_pool
from agv_brain.models import load_settings
from agv_brain.simulator import random_scenario
rng = np.random.default_rng(1)
for ctx in layout_pool(8, seed=11, base=load_settings()):
    print(list(ctx.fmap._adj.items()), random_scenario(rng, ctx))
"""


def test_layouts_are_reproducible_across_runs():
    # set iteration order changes with Python's hash seed; layouts must not
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    outs = []
    for hash_seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(root)}
        outs.append(subprocess.run([sys.executable, "-c", _FINGERPRINT], env=env, cwd=root,
                                   capture_output=True, text=True, check=True).stdout)
    assert outs[0] == outs[1]


def test_dataset_mixes_layouts():
    ds = generate(load_context(), 60, seed=2, random_layouts=10, layout_share=0.5)
    layouts = {row["layout"] for row in ds.job_rows}
    assert "ours" in layouts and any(name.startswith("random-") for name in layouts)
    assert len(ds.y) == len(ds.X) and set(np.unique(ds.y)) <= {0, 1}
