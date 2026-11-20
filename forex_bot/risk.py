import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import RiskConfig, SymbolConfig


class RiskManager:
    def __init__(self, cfg: RiskConfig, state_path, kill_switch_path, start_balance: float):
        self.cfg = cfg
        self.state_path = Path(state_path)
        self.kill_path = Path(kill_switch_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load(float(start_balance))

    def _default_state(self, today: str, start_balance: float) -> dict:
        return {
            "date": today,
            "daily_pnl": 0.0,
            "day_start_equity": start_balance,
            "peak_equity": start_balance,
            "consecutive_losses": 0,
            "trades": 0,
            "cooldown_until": "",
        }

    def _load(self, start_balance: float) -> dict:
        today = date.today().isoformat()
        state = None
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                state = None
        if not state or state.get("date") != today:
            state = self._default_state(today, start_balance)
            self._save(state)
        return state

    def _save(self, state=None):
        self.state_path.write_text(json.dumps(state or self.state, indent=2), encoding="utf-8")

    def can_trade(self, now: datetime, equity: float):
        if self.kill_path.exists():
            return False, "kill_switch"
        peak = self.state["peak_equity"]
        if peak > 0 and equity <= peak * (1.0 - self.cfg.max_drawdown_pct / 100.0):
            return False, "max_drawdown"
        day_start = self.state["day_start_equity"]
        if day_start > 0 and self.state["daily_pnl"] <= -self.cfg.max_daily_loss_pct / 100.0 * day_start:
            return False, "daily_loss_limit"
        cooldown_until = self.state.get("cooldown_until") or ""
        if self.state["consecutive_losses"] >= self.cfg.max_consecutive_losses and cooldown_until:
            if now < datetime.fromisoformat(cooldown_until):
                return False, "cooldown"
        return True, ""

    def size_position(self, balance: float, entry: float, sl: float, symbol: SymbolConfig) -> float:
        risk_amount = balance * self.cfg.risk_per_trade_pct / 100.0
        sl_dist = abs(entry - sl)
        if sl_dist <= 0 or symbol.contract_size <= 0:
            return 0.0
        raw_lots = risk_amount / sl_dist / symbol.contract_size
        lots = math.floor(raw_lots / symbol.lot_step + 1e-9) * symbol.lot_step
        lots = round(lots, 8)
        if lots < symbol.min_lot:
            return 0.0
        return min(lots, symbol.max_lot)

    def record_result(self, profit: float, now: datetime, equity: float):
        s = self.state
        s["trades"] = s.get("trades", 0) + 1
        s["daily_pnl"] = s.get("daily_pnl", 0.0) + profit
        s["peak_equity"] = max(s.get("peak_equity", 0.0), equity)
        if profit < 0:
            s["consecutive_losses"] = s.get("consecutive_losses", 0) + 1
            if s["consecutive_losses"] >= self.cfg.max_consecutive_losses:
                s["cooldown_until"] = (now + timedelta(minutes=self.cfg.cooldown_minutes)).isoformat()
        else:
            s["consecutive_losses"] = 0
            s["cooldown_until"] = ""
        self._save()
