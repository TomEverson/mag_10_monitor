# Plotly Visualization Specs

All visualizations use the trader-focused dashboard theme. Interactive, exportable as PNG.

---

## Global Configuration (All Charts)

```python
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

TEMPLATE = "plotly_dark"
FONT = dict(family="Inter, sans-serif", size=12, color="#e5e5e5")
COLORS = ["#4a9eed", "#f59e0b", "#22c55e", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"]
MARGIN = dict(l=60, r=30, t=60, b=60)
CONFIG = {"displayModeBar": True, "toImageButtonOptions": {"format": "png", "scale": 2}}
```

---

## Chart 1: Multi-Signal Confirmation

**Purpose:** Show when volume spikes and momentum signals fire together within 5 minutes

**Type:** Scatter plot (faceted by direction)

```python
fig = make_subplots(
    rows=1, cols=2,
    subplot_titles=("Direction: UP", "Direction: DOWN"),
    horizontal_spacing=0.15
)

up_data = df_1[df_1['direction'] == 'UP']
down_data = df_1[df_1['direction'] == 'DOWN']

fig.add_trace(
    go.Scatter(
        x=up_data['seconds_apart'],
        y=up_data['spike_ratio'],
        mode='markers',
        marker=dict(size=10, color=COLORS[2], opacity=0.7, line=dict(width=1, color='white')),
        text=[f"{row['symbol']}<br>Spike: {row['spike_ratio']:.2f}x<br>Gap: {row['seconds_apart']:.0f}s<br>Mom: {row['momentum_pct']:.1f}%" 
              for _, row in up_data.iterrows()],
        hovertemplate='<b>%{text}</b><extra></extra>',
        name='UP',
        showlegend=False
    ),
    row=1, col=1
)

fig.add_trace(
    go.Scatter(
        x=down_data['seconds_apart'],
        y=down_data['spike_ratio'],
        mode='markers',
        marker=dict(size=10, color=COLORS[3], opacity=0.7, line=dict(width=1, color='white')),
        text=[f"{row['symbol']}<br>Spike: {row['spike_ratio']:.2f}x<br>Gap: {row['seconds_apart']:.0f}s<br>Mom: {row['momentum_pct']:.1f}%" 
              for _, row in down_data.iterrows()],
        hovertemplate='<b>%{text}</b><extra></extra>',
        name='DOWN',
        showlegend=False
    ),
    row=1, col=2
)

fig.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5, row=1, col=1)
fig.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5, row=1, col=2)

fig.update_xaxes(title_text="Seconds Apart", row=1, col=1)
fig.update_xaxes(title_text="Seconds Apart", row=1, col=2)
fig.update_yaxes(title_text="Spike Ratio", row=1, col=1)
fig.update_yaxes(title_text="Spike Ratio", row=1, col=2)

fig.update_layout(
    title="Multi-Signal Confirmation (Volume + Momentum)",
    template=TEMPLATE,
    font=FONT,
    height=450,
    margin=MARGIN,
    hovermode='closest'
)

fig.show(config=CONFIG)
```

---

## Chart 2: Sector Rotation Detection

**Purpose:** See which signal types are active each hour and which symbols are moving

**Type:** Grouped bar chart + table

```python
fig = go.Figure()

fig.add_trace(go.Bar(
    x=df_2['trading_hour'],
    y=df_2['volume_count'],
    name='Volume Signals',
    marker=dict(color=COLORS[0]),
    hovertemplate='Hour %{x}<br>Volume: %{y}<extra></extra>'
))

fig.add_trace(go.Bar(
    x=df_2['trading_hour'],
    y=df_2['momentum_count'],
    name='Momentum Signals',
    marker=dict(color=COLORS[1]),
    hovertemplate='Hour %{x}<br>Momentum: %{y}<extra></extra>'
))

fig.add_trace(go.Bar(
    x=df_2['trading_hour'],
    y=df_2['volatility_count'],
    name='Volatility Signals',
    marker=dict(color=COLORS[3]),
    hovertemplate='Hour %{x}<br>Volatility: %{y}<extra></extra>'
))

fig.update_layout(
    title="Signal Distribution by Trading Hour",
    xaxis_title="Hour (UTC)",
    yaxis_title="Signal Count",
    barmode='group',
    template=TEMPLATE,
    font=FONT,
    height=450,
    margin=MARGIN,
    hovermode='x unified'
)

fig.show(config=CONFIG)
```

---

## Chart 3: Signal Accuracy / Win Rate

**Purpose:** Show historical profitability of volume spike signals

**Type:** Bar chart + gauge

```python
fig = make_subplots(
    rows=1, cols=2,
    subplot_titles=("Win Rate by Return Threshold", "Average Return per Signal"),
    specs=[[{"type": "bar"}, {"type": "indicator"}]],
    horizontal_spacing=0.2
)

win_rate_pct = df_3['win_rate_pct'].iloc[0]
avg_return = df_3['avg_return_pct'].iloc[0]
total = df_3['total_signals'].iloc[0]

# Win rate bars
thresholds = ['0.5%+', '1%+', '2%+']
counts = [df_3['profitable_half_pct'].iloc[0],
          df_3['profitable_1pct'].iloc[0],
          df_3['profitable_2pct'].iloc[0]]

fig.add_trace(
    go.Bar(
        x=thresholds,
        y=[c / total * 100 for c in counts],
        marker=dict(color=COLORS[2]),
        text=[f'{c/total*100:.1f}%' for c in counts],
        textposition='outside',
        hovertemplate='%{x}<br>Win Rate: %{y:.1f}%<extra></extra>',
        showlegend=False
    ),
    row=1, col=1
)

# Gauge
fig.add_trace(
    go.Indicator(
        mode="gauge+number+delta",
        value=avg_return,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"Avg Return: {avg_return:.3f}%"},
        gauge={'axis': {'range': [-1, 1]},
               'bar': {'color': COLORS[2] if avg_return > 0 else COLORS[3]},
               'steps': [{'range': [-1, 0], 'color': '#fcc'},
                        {'range': [0, 1], 'color': '#ccf'}],
               'threshold': {'line': {'color': 'white'}, 'thickness': 4, 'value': 0}},
        delta={'reference': 0, 'suffix': '%'},
        showlegend=False
    ),
    row=1, col=2
)

fig.update_xaxes(title_text="Return Threshold", row=1, col=1)
fig.update_yaxes(title_text="Win Rate (%)", range=[0, 100], row=1, col=1)

fig.update_layout(
    title=f"Signal Win Rate Analysis (Total Signals: {int(total)})",
    template=TEMPLATE,
    font=FONT,
    height=450,
    margin=MARGIN,
    hovermode='x unified'
)

fig.show(config=CONFIG)
```

---

## Chart 4: Best Trading Hours

**Purpose:** Identify peak trading hours and signal strength patterns

**Type:** Dual axis (bar + line)

```python
fig = make_subplots(
    rows=2, cols=1,
    subplot_titles=("Signal Volume per Hour", "Signal Strength Trend"),
    vertical_spacing=0.2,
    shared_xaxes=True
)

# Bar: signal count
fig.add_trace(
    go.Bar(
        x=df_4['trading_hour'],
        y=df_4['signal_count'],
        marker=dict(color=COLORS[0]),
        name='Signal Count',
        hovertemplate='Hour %{x}<br>Count: %{y}<extra></extra>'
    ),
    row=1, col=1
)

# Line: avg spike ratio
fig.add_trace(
    go.Scatter(
        x=df_4['trading_hour'],
        y=df_4['avg_spike_ratio'],
        mode='lines+markers',
        line=dict(color=COLORS[1], width=2),
        marker=dict(size=8),
        name='Avg Spike Ratio',
        hovertemplate='Hour %{x}<br>Avg: %{y:.2f}x<extra></extra>'
    ),
    row=2, col=1
)

# Line: max spike ratio
fig.add_trace(
    go.Scatter(
        x=df_4['trading_hour'],
        y=df_4['max_spike_ratio'],
        mode='lines+markers',
        line=dict(color=COLORS[3], width=2, dash='dash'),
        marker=dict(size=8, symbol='diamond'),
        name='Max Spike Ratio',
        hovertemplate='Hour %{x}<br>Max: %{y:.2f}x<extra></extra>'
    ),
    row=2, col=1
)

fig.update_xaxes(title_text="Hour (UTC)", row=2, col=1)
fig.update_yaxes(title_text="Count", row=1, col=1)
fig.update_yaxes(title_text="Spike Ratio", row=2, col=1)

fig.update_layout(
    title="Signal Activity by Trading Hour",
    template=TEMPLATE,
    font=FONT,
    height=600,
    margin=MARGIN,
    hovermode='x unified'
)

fig.show(config=CONFIG)
```

---

## Chart 5: Volatility Regime Check

**Purpose:** Monitor daily volatility levels to adjust risk

**Type:** Combo (bar + line)

```python
df_5['date'] = pd.to_datetime(df_5['date']).dt.strftime('%Y-%m-%d')

fig = make_subplots(
    rows=2, cols=1,
    subplot_titles=("Daily Volatility Signal Count", "Z-Score Trend"),
    vertical_spacing=0.15,
    shared_xaxes=True
)

# Bar: volatility signals per day
fig.add_trace(
    go.Bar(
        x=df_5['date'],
        y=df_5['volatility_signals'],
        marker=dict(color=COLORS[4]),
        name='Volatility Signals',
        hovertemplate='%{x}<br>Signals: %{y}<extra></extra>'
    ),
    row=1, col=1
)

# Line: avg z-score
fig.add_trace(
    go.Scatter(
        x=df_5['date'],
        y=df_5['avg_z_score'],
        mode='lines+markers',
        line=dict(color=COLORS[2], width=2),
        marker=dict(size=6),
        name='Avg Z-Score',
        hovertemplate='%{x}<br>Avg Z: %{y:.2f}<extra></extra>'
    ),
    row=2, col=1
)

# Line: max z-score
fig.add_trace(
    go.Scatter(
        x=df_5['date'],
        y=df_5['max_z_score'],
        mode='lines+markers',
        line=dict(color=COLORS[3], width=2, dash='dash'),
        marker=dict(size=6, symbol='diamond'),
        name='Max Z-Score',
        hovertemplate='%{x}<br>Max Z: %{y:.2f}<extra></extra>'
    ),
    row=2, col=1
)

# Reference line
fig.add_hline(y=2.0, line_dash="dot", line_color="gray", annotation_text="Z=2 threshold",
              annotation_position="right", row=2, col=1)

fig.update_xaxes(title_text="Date", row=2, col=1)
fig.update_yaxes(title_text="Count", row=1, col=1)
fig.update_yaxes(title_text="Z-Score", row=2, col=1)

fig.update_layout(
    title="Daily Volatility Regime",
    template=TEMPLATE,
    font=FONT,
    height=600,
    margin=MARGIN,
    hovermode='x unified'
)

fig.show(config=CONFIG)
```

---

## Chart 6: Stock Correlation

**Purpose:** Identify which stocks move together (pairs trading)

**Type:** Heatmap + bar chart

```python
fig = make_subplots(
    rows=1, cols=2,
    subplot_titles=("Co-Signal Heatmap", "Top 10 Correlated Pairs"),
    specs=[[{"type": "heatmap"}, {"type": "bar"}]],
    horizontal_spacing=0.15
)

# Build correlation matrix
symbols = sorted(set(df_6['stock_a'].tolist() + df_6['stock_b'].tolist()))
matrix = pd.DataFrame(0, index=symbols, columns=symbols, dtype=int)
for _, row in df_6.iterrows():
    matrix.loc[row['stock_a'], row['stock_b']] = row['co_signal_count']
    matrix.loc[row['stock_b'], row['stock_a']] = row['co_signal_count']

# Heatmap
fig.add_trace(
    go.Heatmap(
        z=matrix.values,
        x=matrix.columns,
        y=matrix.index,
        colorscale='Blues',
        text=matrix.values,
        texttemplate='%{text}',
        textfont={"size": 10},
        name='',
        showscale=True,
        colorbar=dict(title="Co-Signals")
    ),
    row=1, col=1
)

# Top 10 pairs bar chart
top_pairs = df_6.nlargest(10, 'co_signal_count').copy()
top_pairs['pair'] = top_pairs['stock_a'] + '-' + top_pairs['stock_b']

fig.add_trace(
    go.Bar(
        x=top_pairs['co_signal_count'],
        y=top_pairs['pair'],
        orientation='h',
        marker=dict(color=COLORS[5]),
        text=top_pairs['co_signal_count'],
        textposition='outside',
        hovertemplate='%{y}<br>Count: %{x}<extra></extra>',
        showlegend=False
    ),
    row=1, col=2
)

fig.update_xaxes(title_text="", row=1, col=1)
fig.update_xaxes(title_text="Co-Signal Count", row=1, col=2)

fig.update_layout(
    title="Stock Correlation: Which Stocks Move Together",
    template=TEMPLATE,
    font=FONT,
    height=500,
    margin=MARGIN,
    hovermode='closest'
)

fig.show(config=CONFIG)
```

---

## Chart 7: Signal Strength vs Price Movement

**Purpose:** Validate signal thresholds — bigger breaches = bigger moves?

**Type:** Range chart with markers

```python
order = ['Mild (1.0-1.5x)', 'Moderate (1.5-2.0x)', 'Strong (2.0-3.0x)', 'Extreme (3.0x+)']
df_7['breach_category'] = pd.Categorical(df_7['breach_category'], categories=order, ordered=True)
df_7_sorted = df_7.sort_values('breach_category')

fig = go.Figure()

# Range (min to max) as error bars
fig.add_trace(go.Scatter(
    x=df_7_sorted['breach_category'],
    y=df_7_sorted['avg_price_move'],
    error_y=dict(
        type='data',
        symmetric=False,
        array=df_7_sorted['max_price_move'] - df_7_sorted['avg_price_move'],
        arrayminus=df_7_sorted['avg_price_move'] - df_7_sorted['min_price_move']
    ),
    mode='markers',
    marker=dict(size=12, color=COLORS[2]),
    line=dict(width=2),
    name='Avg Price Move',
    hovertemplate='%{x}<br>Avg: %{y:.3f}%<br>Min: %{customdata[0]:.3f}%<br>Max: %{customdata[1]:.3f}%<extra></extra>',
    customdata=df_7_sorted[['min_price_move', 'max_price_move']].values
))

# Zero line
fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

fig.update_layout(
    title="Signal Strength vs Actual Price Movement",
    xaxis_title="Spike Magnitude Category",
    yaxis_title="Price Change (%)",
    template=TEMPLATE,
    font=FONT,
    height=450,
    margin=MARGIN,
    hovermode='closest'
)

fig.show(config=CONFIG)
```

---

## Chart 8: Real-Time Alert Board

**Purpose:** Live trading signals — what's happening RIGHT NOW

**Type:** Indicator cards + scatter + pie

```python
fig = make_subplots(
    rows=1, cols=3,
    subplot_titles=("Max Spike by Symbol", "Confirmation Rate", "Price Timeline"),
    specs=[[{"type": "bar"}, {"type": "pie"}, {"type": "scatter"}]],
    horizontal_spacing=0.12
)

df_8['timestamp'] = pd.to_datetime(df_8['timestamp'])

# Max spike by symbol
symbol_max = df_8.groupby('symbol')['spike_ratio'].max().sort_values(ascending=True)
colors_bar = [COLORS[2] if v >= 2 else COLORS[0] for v in symbol_max.values]

fig.add_trace(
    go.Bar(
        y=symbol_max.index,
        x=symbol_max.values,
        orientation='h',
        marker=dict(color=colors_bar),
        text=[f'{v:.2f}x' for v in symbol_max.values],
        textposition='outside',
        hovertemplate='%{y}<br>Max Spike: %{x:.2f}x<extra></extra>',
        showlegend=False
    ),
    row=1, col=1
)

# Confirmation pie
conf_counts = df_8['confidence'].value_counts()
colors_pie = [COLORS[2] if c == 'CONFIRMED' else COLORS[1] for c in conf_counts.index]

fig.add_trace(
    go.Pie(
        labels=conf_counts.index,
        values=conf_counts.values,
        marker=dict(colors=colors_pie),
        textposition='inside',
        textinfo='label+percent',
        hovertemplate='%{label}<br>Count: %{value}<extra></extra>',
        showlegend=False
    ),
    row=1, col=2
)

# Timeline scatter
for sym in df_8['symbol'].unique():
    sym_data = df_8[df_8['symbol'] == sym]
    fig.add_trace(
        go.Scatter(
            x=sym_data['timestamp'],
            y=sym_data['price'],
            mode='markers',
            marker=dict(
                size=sym_data['spike_ratio'] * 6,  # bubble size proportional to spike
                color=COLORS[0],
                opacity=0.7,
                line=dict(width=1, color='white')
            ),
            text=[f"{s}<br>Price: ${p:.2f}<br>Spike: {sr:.2f}x<br>Direction: {d}" 
                  for s, p, sr, d in zip(sym_data['symbol'], sym_data['price'], 
                                         sym_data['spike_ratio'], sym_data['direction'])],
            hovertemplate='%{text}<extra></extra>',
            name=sym,
            showlegend=True
        ),
        row=1, col=3
    )

fig.update_xaxes(title_text="Max Spike Ratio", row=1, col=1)
fig.update_xaxes(title_text="Time", row=1, col=3)
fig.update_yaxes(title_text="Symbol", row=1, col=1)
fig.update_yaxes(title_text="Price (USD)", row=1, col=3)

fig.update_layout(
    title="Real-Time Signal Dashboard (Last 10 Minutes)",
    template=TEMPLATE,
    font=FONT,
    height=500,
    margin=MARGIN,
    hovermode='closest',
    legend=dict(orientation="v", yanchor="top", y=0.99, xanchor="left", x=1.02)
)

fig.show(config=CONFIG)
```

---

## Implementation Notes

**Color Scheme (Trader-Focused):**
- Blue (#4a9eed): Primary data, volume
- Orange (#f59e0b): Secondary, warnings, pending
- Green (#22c55e): Success, profit, buy signals
- Red (#ef4444): Risk, loss, sell signals
- Purple (#8b5cf6): Volatility, special metrics
- Cyan (#06b6d4): Info, secondary signals

**Interactivity:**
- Hover tooltips show exact values (3 decimal places for ratios)
- Click legend items to toggle traces on/off
- Double-click legend to isolate one trace
- Use zoom/pan tools in top-right
- Export as PNG via camera icon

**Responsive:**
- Charts automatically reflow on screen resize
- Mobile-friendly layout (reduce to 1 column if needed)
- All text readable at 100% zoom

**Dashboard Integration:**
- Each chart is self-contained (can be embedded in Jupyter, Dash, or standalone HTML)
- Share as HTML or export as PNG for presentations
- Connect to live BigQuery via `pd.read_gbq()` for auto-refresh
