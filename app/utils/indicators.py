import numpy as np


def ema(prices: np.ndarray, period: int) -> np.ndarray:
    import pandas as pd
    return pd.Series(prices).ewm(span=period, adjust=False).mean().values


def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    import pandas as pd
    delta = pd.Series(prices).diff()
    gain  = delta.where(delta > 0, 0.0).ewm(span=period).mean()
    loss  = (-delta.where(delta < 0, 0.0)).ewm(span=period).mean()
    rs    = gain / (loss + 1e-10)
    return (100 - 100 / (1 + rs)).values


def macd(prices: np.ndarray, fast=12, slow=26, sig=9):
    import pandas as pd
    s      = pd.Series(prices)
    line   = s.ewm(span=fast).mean() - s.ewm(span=slow).mean()
    signal = line.ewm(span=sig).mean()
    return line.values, signal.values, (line - signal).values


def atr(high: np.ndarray, low: np.ndarray,
        close: np.ndarray, period: int = 14) -> np.ndarray:
    import pandas as pd
    prev  = np.roll(close, 1)
    prev[0] = close[0]
    tr    = np.maximum(high - low, np.maximum(
        np.abs(high - prev), np.abs(low - prev)
    ))
    return pd.Series(tr).ewm(span=period).mean().values


def bollinger(prices: np.ndarray, period: int = 20, std: float = 2.0):
    import pandas as pd
    s   = pd.Series(prices)
    mid = s.rolling(period).mean()
    dev = s.rolling(period).std()
    return (mid + dev * std).values, mid.values, (mid - dev * std).values
