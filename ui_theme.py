PLOTLY_GRID_COLOR = "rgba(100, 116, 139, 0.28)"
PLOTLY_ZERO_LINE_COLOR = "rgba(100, 116, 139, 0.38)"
PLOTLY_EMA_SLOW = "#64748B"


def plotly_theme_values() -> dict:
    return {
        "grid_color": PLOTLY_GRID_COLOR,
        "zero_line_color": PLOTLY_ZERO_LINE_COLOR,
        "ema_slow": PLOTLY_EMA_SLOW,
    }


def apply_plotly_theme(fig, *, height=None, margin=None, xaxis_rangeslider_visible=None):
    values = plotly_theme_values()
    layout = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
    }
    if height is not None:
        layout["height"] = height
    if margin is not None:
        layout["margin"] = margin
    if xaxis_rangeslider_visible is not None:
        layout["xaxis_rangeslider_visible"] = xaxis_rangeslider_visible
    fig.update_layout(**layout)
    fig.update_xaxes(
        gridcolor=values["grid_color"],
        zerolinecolor=values["zero_line_color"],
        automargin=False,
    )
    fig.update_yaxes(
        gridcolor=values["grid_color"],
        zerolinecolor=values["zero_line_color"],
        automargin=False,
    )
    return fig
