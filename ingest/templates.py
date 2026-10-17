"""Drain3 template mining with masking. Template ids: BGL from 1, OpenStack from 100000 (contract)."""
from __future__ import annotations

from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

OFFSETS = {"bgl": 0, "openstack": 99_999}  # cluster ids start at 1

MASKS = [
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",  # uuid
    r"R\d\d-M\d(?:-[A-Z0-9:-]+)?",                                    # BGL node / location ids
    r"\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?",                              # ip[:port]
    r"(?:/[\w.-]+)+/?",                                                # paths
    r"0x[0-9a-fA-F]+|\b[0-9a-f]{8,}\b",                                # hex
    r"[-+]?\d+(?:\.\d+)?",                                             # numbers
]


def make_miner() -> TemplateMiner:
    cfg = TemplateMinerConfig()
    cfg.masking_instructions = [MaskingInstruction(p, "*") for p in MASKS]  # renders as <*>
    cfg.drain_sim_th = 0.5
    cfg.profiling_enabled = False
    return TemplateMiner(config=cfg)
