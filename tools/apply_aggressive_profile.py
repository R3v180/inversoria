"""Aplica perfil agresivo en user_settings.json preservando API keys."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "user_settings.json"

AGGRESSIVE_PATCH = {
    "TRADING_EXECUTION_MODE": "auto",
    "DECISION_MODE": "ai_aggressive",
    "MIN_AUTO_DECISION_SCORE": 0.52,
    "MIN_CONFIDENCE_ENTRY": 0.48,
    "MANUAL_MAX_POSITIONS_PRIORITY": True,
    "MAX_OPEN_POSITIONS": 2,
    "RISK_PER_TRADE": 0.20,
    "MIN_PROFIT_NET": 0.6,
    "STOP_LOSS_PERCENT": 2.5,
    "MAX_DAILY_LOSS_PCT": 8.0,
    "MAX_PORTFOLIO_EXPOSURE_PCT": 90.0,
    "VOLATILITY_SIZING_ENABLED": False,
    "MAX_POSITION_RISK_PCT": 8.0,
    "MAX_VOLATILITY_POSITION_MULTIPLIER": 1.5,
    "MIN_POSITION_USDT": 15.0,
    "MAX_SYMBOL_EXPOSURE_PCT": 50.0,
    "MAX_ALT_EXPOSURE_PCT": 90.0,
    "MAX_BUCKET_EXPOSURE_PCT": 55.0,
    "ROTATION_ENABLED": True,
    "ROTATION_MIN_PROFIT": 0.5,
    "ROTATION_CONFIDENCE_GAP": 0.12,
    "ROTATION_MIN_NEW_CONFIDENCE": 0.68,
    "AI_ANALYSIS_INTERVAL": 300,
    "BUY_SLIPPAGE_LIMIT": 0.008,
    "SELL_SLIPPAGE_LIMIT": 0.012,
    "AGGRESSIVE_TRADING_PROFILE": True,
    "MACRO_VETO_ALTS_IN_RISK_OFF": False,
    "MACRO_RISK_OFF_BTC_DOM": 62.0,
    "MACRO_RISK_OFF_CAP_CHANGE_PCT": -3.5,
    "MACRO_CAUTION_BTC_DOM": 64.0,
    "MACRO_DXY_VETO_PCT": 2.0,
    "MACRO_SPY_VETO_PCT": -3.0,
    "MTF_ALLOW_COUNTER_TREND": True,
    "BACKTEST_HARD_VETO_WIN_RATE": 0.28,
    "SMALL_ACCOUNT_USDT_THRESHOLD": 150.0,
    "SMALL_ACCOUNT_FORCE_MIN_ORDER": True,
    "SMALL_ACCOUNT_MAX_STOP_DISTANCE_PCT": 8.0,
    "DAEMON_CYCLE_SECONDS": 45,
    "WATCHLIST_UPDATE_SECONDS": 10800,
}


def main():
    data = {}
    if SETTINGS_PATH.exists():
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    data.update(AGGRESSIVE_PATCH)
    SETTINGS_PATH.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"Perfil agresivo aplicado en {SETTINGS_PATH}")


if __name__ == "__main__":
    main()
