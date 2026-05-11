import asyncio
from typing import Optional
from datetime import datetime

from app.config import settings
from app.core.bybit import BybitClient
from app.utils.logger import get_logger
from app.utils.indicators import rsi, macd, ema, atr

log = get_logger("engine")


class TradingEngine:
    def __init__(self, client: BybitClient):
        self.client    = client
        self.active    = False   # bot ligado/desligado
        self.connected = False   # bybit conectada
        self.position: Optional[dict] = None
        self.balance   = 0.0
        self.price     = 0.0
        self.peak_bal  = settings.INITIAL_CAPITAL
        self.cur_bal   = settings.INITIAL_CAPITAL
        self.drawdown  = 0.0
        self.consec_losses = 0
        self._running  = False
        log.info("🤖 TradingEngine criado")

    async def run(self):
        """Loop principal — nunca para, reconecta automaticamente"""
        self._running = True
        log.info("⚡ Engine iniciando...")

        # Testa conexão inicial
        await self._connect()

        while self._running:
            try:
                if not self.connected:
                    await asyncio.sleep(30)
                    await self._connect()
                    continue

                if self.active:
                    await self._cycle()

                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Engine loop: {e}")
                await asyncio.sleep(10)

    def stop(self):
        self.active = False
        log.info("⏸️ Bot pausado")

    def resume(self):
        self.active = True
        log.info("▶️ Bot retomado")

    async def _connect(self):
        """Testa conexão com Bybit"""
        try:
            # Teste público
            ok = await self.client.ping()
            if not ok:
                log.error("❌ Ping Bybit falhou")
                self.connected = False
                return

            # Teste autenticado
            bal = await self.client.get_balance()
            if bal < 0:
                log.error("❌ Auth Bybit falhou — verifique as chaves")
                self.connected = False
                return

            self.balance  = bal
            self.cur_bal  = bal
            self.peak_bal = max(self.peak_bal, bal)
            self.connected = True
            self.active    = True
            log.info(f"✅ Bybit conectada! Saldo: ${bal:.2f} USDT")

            # Configura leverage
            await self.client.set_leverage(settings.SYMBOL, settings.LEVERAGE)

        except Exception as e:
            log.error(f"_connect: {e}")
            self.connected = False

    async def _cycle(self):
        """Um ciclo de análise e trading"""
        try:
            # Atualiza saldo
            bal = await self.client.get_balance()
            if bal >= 0:
                self.balance = bal
                self.cur_bal = bal
                self.peak_bal = max(self.peak_bal, bal)
                self.drawdown = (self.peak_bal - bal) / self.peak_bal if self.peak_bal > 0 else 0

                # Para se drawdown muito alto
                if self.drawdown >= settings.MAX_DRAWDOWN:
                    log.warning(f"⚠️ Drawdown {self.drawdown:.1%} — pausando")
                    self.active = False
                    return

            # Busca dados de mercado
            klines = await self.client.get_klines(settings.SYMBOL, "5m", 100)
            if len(klines) < 20:
                return

            # Extrai preços
            closes = [float(k[4]) for k in klines]
            highs  = [float(k[2]) for k in klines]
            lows   = [float(k[3]) for k in klines]
            self.price = closes[-1]

            # Analisa sinal
            signal = self._analyze(closes, highs, lows)
            if signal and not self.position:
                await self._open(signal, closes[-1])

            # Monitora posição aberta
            if self.position:
                await self._monitor_position()

        except Exception as e:
            log.error(f"_cycle: {e}")

    def _analyze(self, closes, highs, lows) -> Optional[str]:
        """Análise técnica simples e robusta"""
        import numpy as np
        c = np.array(closes)
        h = np.array(highs)
        l = np.array(lows)

        if len(c) < 20:
            return None

        # Indicadores
        rsi_val  = rsi(c)[-1]
        ema9     = ema(c, 9)[-1]
        ema21    = ema(c, 21)[-1]
        ema50    = ema(c, 50)[-1] if len(c) >= 50 else ema21
        atr_val  = atr(h, l, c)[-1]
        price    = c[-1]

        # Contexto de tendência
        trend_up   = ema9 > ema21 > ema50
        trend_down = ema9 < ema21 < ema50

        score = 0

        # RSI
        if rsi_val < 35:  score += 2
        elif rsi_val < 45: score += 1
        elif rsi_val > 65: score -= 2
        elif rsi_val > 55: score -= 1

        # Tendência
        if trend_up:   score += 2
        if trend_down: score -= 2

        # Preço vs EMAs
        if price > ema9 > ema21: score += 1
        if price < ema9 < ema21: score -= 1

        # Confiança baseada no score
        if score >= 4:
            conf = min(0.95, 0.65 + (score - 4) * 0.05)
            if conf >= settings.MIN_CONFIDENCE:
                log.info(f"📊 LONG signal | RSI={rsi_val:.1f} score={score} conf={conf:.0%}")
                return "LONG"
        elif score <= -4:
            conf = min(0.95, 0.65 + (abs(score) - 4) * 0.05)
            if conf >= settings.MIN_CONFIDENCE:
                log.info(f"📊 SHORT signal | RSI={rsi_val:.1f} score={score} conf={conf:.0%}")
                return "SHORT"

        return None

    async def _open(self, direction: str, price: float):
        """Abre posição com SL e TP"""
        try:
            if self.balance <= 0:
                return

            # Position sizing — risco fixo
            risk_usd = self.balance * settings.MAX_RISK_PCT
            sl_pct   = 0.007  # 0.7% stop loss
            sl_dist  = price * sl_pct
            qty      = round(risk_usd / sl_dist, 3)
            qty      = max(0.001, qty)

            side = "Buy" if direction == "LONG" else "Sell"
            sl   = price * (1 - sl_pct) if direction == "LONG" else price * (1 + sl_pct)
            tp   = price * (1 + sl_pct * 2) if direction == "LONG" else price * (1 - sl_pct * 2)

            result = await self.client.place_order(
                symbol=settings.SYMBOL, side=side, qty=qty,
                stop_loss=sl, take_profit=tp
            )

            self.position = {
                "direction": direction,
                "entry":     price,
                "sl":        sl,
                "tp":        tp,
                "qty":       qty,
                "opened_at": str(datetime.utcnow()),
            }
            log.info(f"✅ {direction} aberto: qty={qty} entry={price:.0f} sl={sl:.0f} tp={tp:.0f}")

        except Exception as e:
            log.error(f"_open: {e}")

    async def _monitor_position(self):
        """Verifica se posição ainda está aberta"""
        try:
            pos = await self.client.get_position(settings.SYMBOL)
            size = float(pos.get("size", 0))
            if size == 0 and self.position:
                pnl = float(pos.get("unrealisedPnl", 0))
                log.info(f"📭 Posição fechada | PnL: ${pnl:.2f}")
                if pnl < 0:
                    self.consec_losses += 1
                else:
                    self.consec_losses = 0
                self.position = None
        except Exception as e:
            log.error(f"_monitor: {e}")

    def status(self) -> dict:
        return {
            "connected":    self.connected,
            "active":       self.active,
            "price":        self.price,
            "balance":      round(self.balance, 2),
            "drawdown_pct": round(self.drawdown * 100, 2),
            "consec_losses": self.consec_losses,
            "position":     self.position,
            "symbol":       settings.SYMBOL,
            "mode":         settings.TRADING_MODE,
        }
