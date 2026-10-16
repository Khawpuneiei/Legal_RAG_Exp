"""Experiment tests need the `experiments` extra (numpy, torch...). CI for the app installs only base + dev, so those
modules are skipped when their heavy dependencies are missing."""
import importlib.util

collect_ignore = []
if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("networkx") is None:
    collect_ignore += ["test_graph.py", "test_metrics.py", "test_generation_eval.py", "test_synthetic.py"]
