import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ui_theme import apply_plotly_theme, plotly_theme_values


def build_technical_chart(ohlcv, height=400, rows="compact"):
    if not ohlcv:
        return None
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).tail(100)
    if df.empty:
        return None

    df["EMA_50"] = ta.ema(df["close"], length=50)
    df["EMA_200"] = ta.ema(df["close"], length=200)
    df["RSI_14"] = ta.rsi(df["close"], length=14)
    df["ATR_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    theme_values = plotly_theme_values()

    row_heights = [0.5, 0.25, 0.25] if rows == "compact" else [0.6, 0.2, 0.2]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights)
    fig.add_trace(
        go.Candlestick(
            x=df["ts"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(go.Scatter(x=df["ts"], y=df["EMA_50"], line=dict(color="orange", width=1.2), name="EMA50"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["ts"], y=df["EMA_200"], line=dict(color=theme_values["ema_slow"], width=1.6), name="EMA200"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["ts"], y=df["RSI_14"], line=dict(color="purple", width=1), name="RSI"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    fig.add_trace(go.Scatter(x=df["ts"], y=df["ATR_14"], line=dict(color="cyan", width=1), name="ATR"), row=3, col=1)
    apply_plotly_theme(fig, height=height, margin=dict(l=0, r=0, t=30, b=0), xaxis_rangeslider_visible=False)
    return fig

