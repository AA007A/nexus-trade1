import os
from functools import lru_cache


class Settings:
    # Bybit (env vars com nomes antigos para compatibilidade)
    API_KEY:    str = os.environ.get("BINANCE_API_KEY", "")
    API_SECRET: str = os.environ.get("BINANCE_API_SECRET", "")

    # Trading
    SYMBOL:             str   = os.environ.get("SYMBOL", "BTCUSDT")
    LEVERAGE:           int   = int(os.environ.get("DEFAULT_LEVERAGE", "5"))
    TRADING_MODE:       str   = os.environ.get("TRADING_MODE", "conservative")
    MAX_RISK_PCT:       float = float(os.environ.get("MAX_RISK_PER_TRADE", "0.01"))
    MAX_DRAWDOWN:       float = float(os.environ.get("MAX_DRAWDOWN", "0.05"))
    MAX_CONSEC_LOSSES:  int   = int(os.environ.get("MAX_CONSECUTIVE_LOSSES", "5"))
    INITIAL_CAPITAL:    float = float(os.environ.get("INITIAL_CAPITAL", "10000"))
    MIN_CONFIDENCE:     float = float(os.environ.get("MIN_CONFIDENCE", "0.65"))

    # Notificações
    TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT:  str = os.environ.get("TELEGRAM_CHAT_ID", "")

    # Sistema
    PORT:      int = int(os.environ.get("PORT", "8000"))
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")


settings = Settings()
