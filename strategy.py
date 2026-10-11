"""Pure strategy rules. No network, no side effects - fully unit-testable.

Position fractions are of the ORIGINAL position:
  Rule 1: multiple >= 2.0 -> sell 50%
  Rule 4: multiple >= 3.0 -> sell 30%      (20% runner remains)
  Rule 2: multiple <= 0.5 -> close 100%    (highest priority)
  Rule 3: peak >= 3.0 and multiple <= peak*(1-0.35) -> close 100% of remainder
"""
from dataclasses import dataclass


@dataclass
class Cfg:
    r1_mult: float = 2.0
    r1_pct: float = 0.50
    r4_mult: float = 3.0
    r4_pct: float = 0.30
    stop_mult: float = 0.5
    trail_start: float = 3.0
    trail_retrace: float = 0.35


@dataclass
class PositionState:
    mint: str
    symbol: str
    entry_price: float
    initial_amount: float
    amount: float
    peak_mult: float = 1.0
    r1_fired: bool = False
    r4_fired: bool = False
    closed: bool = False
    realized_usd: float = 0.0
    opened_at: float = 0.0
    source: str = "manual"
    cost_usd: float = 0.0
    top10_pct: float = 0.0


@dataclass
class Action:
    kind: str
    pct_of_original: float
    reason: str


def evaluate(pos: PositionState, price: float, cfg: Cfg) -> list:
    """Return actions for this tick. Mutates peak_mult and fired flags."""
    actions = []
    if pos.closed or price <= 0 or pos.entry_price <= 0:
        return actions
    m = price / pos.entry_price
    if m > pos.peak_mult:
        pos.peak_mult = m
    if m <= cfg.stop_mult:
        actions.append(Action("close", 1.0,
                              f"规则2: {m:.2f}x 跌破止损 {cfg.stop_mult}x, 清仓"))
        return actions
    if pos.peak_mult >= cfg.trail_start and m <= pos.peak_mult * (1 - cfg.trail_retrace):
        actions.append(Action("close", 1.0,
                              f"规则3: 峰值{pos.peak_mult:.2f}x 回撤至 {m:.2f}x, 清仓"))
        return actions
    if m >= cfg.r1_mult and not pos.r1_fired:
        pos.r1_fired = True
        actions.append(Action("sell", cfg.r1_pct, f"规则1: {m:.2f}x, 卖出50%"))
    if m >= cfg.r4_mult and not pos.r4_fired:
        pos.r4_fired = True
        actions.append(Action("sell", cfg.r4_pct, f"规则4: {m:.2f}x, 卖出30%"))
    return actions
