"""MAG10 Monitor — Real-Time Trading Signal Dashboard (Streamlit)"""
import os
import time
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from dotenv import load_dotenv

import queries

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MAG10 Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Authentication ─────────────────────────────────────────────────────────────
DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'mag10monitor')

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("## 📈 MAG10 Monitor")
        st.markdown("---")
        password = st.text_input("Password", type="password", placeholder="Enter dashboard password")
        if st.button("Login", use_container_width=True):
            if password == DASHBOARD_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password")
    st.stop()

COLORS = ["#4a9eed", "#f59e0b", "#22c55e", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"]
TEMPLATE = "plotly_dark"


# ── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.title("📈 MAG10 Monitor")
st.sidebar.markdown("---")

selected_date = st.sidebar.date_input("Date", value=date.today())
date_str = selected_date.strftime('%Y-%m-%d')

all_symbols = queries.get_all_symbols()
selected_symbols = st.sidebar.multiselect(
    "Symbols",
    options=all_symbols,
    default=all_symbols
)

refresh_interval = st.sidebar.selectbox(
    "Auto-refresh interval",
    options=[15, 30, 60, 120],
    index=1,
    format_func=lambda x: f"{x} seconds"
)

st.sidebar.markdown("---")
st.sidebar.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
st.sidebar.caption(f"Project: {os.getenv('GCP_PROJECT_ID', 'data-engineering-hs')}")
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()


# ── Helper ────────────────────────────────────────────────────────────────────
def empty_fig(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color="#888"))
    fig.update_layout(template=TEMPLATE, height=400)
    return fig


# ── Main title ────────────────────────────────────────────────────────────────
st.title("MAG10 Monitor — Trading Signal Dashboard")
st.caption(f"Showing data for **{date_str}** | Symbols: **{', '.join(selected_symbols)}**")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔴 Live Signals",
    "📊 Volume Analysis",
    "🔗 Momentum & Correlation",
    "📈 Volatility & Sector",
    "📉 Analytics"
])

# ── Tab 1: Live Signals ───────────────────────────────────────────────────────
with tab1:
    st.subheader("Real-Time Signals (Last 10 Minutes)")
    try:
        df = queries.get_realtime_alerts(minutes_back=10, symbols=selected_symbols)

        col1, col2 = st.columns([7, 3])

        with col1:
            if df.empty:
                st.plotly_chart(empty_fig("No signals in the last 10 minutes"), width='stretch')
            else:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                fig = go.Figure()
                for sym in df['symbol'].unique():
                    d = df[df['symbol'] == sym]
                    fig.add_trace(go.Scatter(
                        x=d['timestamp'], y=d['price'],
                        mode='markers',
                        marker=dict(size=d['spike_ratio'] * 7, opacity=0.8,
                                    line=dict(width=1, color='white')),
                        text=[f"{r['symbol']}<br>Price: ${r['price']:.2f}<br>Spike: {r['spike_ratio']:.2f}x<br>"
                              f"Dir: {r.get('direction','N/A')}"
                              for _, r in d.iterrows()],
                        hovertemplate='%{text}<extra></extra>',
                        name=sym
                    ))
                fig.update_layout(title="Signal Timeline (bubble size = spike ratio)",
                                  xaxis_title="Time", yaxis_title="Price (USD)",
                                  template=TEMPLATE, height=450, hovermode='closest')
                st.plotly_chart(fig, width='stretch')

        with col2:
            if not df.empty:
                conf = df['confidence'].value_counts()
                fig2 = go.Figure(go.Pie(
                    labels=conf.index, values=conf.values,
                    marker=dict(colors=[COLORS[2] if c == 'CONFIRMED' else COLORS[1] for c in conf.index]),
                    textinfo='label+percent', hole=0.4
                ))
                fig2.update_layout(title="Confirmation Rate", template=TEMPLATE, height=300)
                st.plotly_chart(fig2, width='stretch')

                # Signal table
                st.dataframe(
                    df[['timestamp', 'symbol', 'price', 'spike_ratio', 'direction', 'confidence']]
                    .sort_values('timestamp', ascending=False)
                    .head(10)
                    .style.format({'price': '${:.2f}', 'spike_ratio': '{:.2f}x'}),
                    width='stretch', hide_index=True
                )
            else:
                st.info("No signals yet. The market may be closed or no thresholds have been crossed.")

    except Exception as e:
        st.error(f"Query failed: {e}")


# ── Tab 2: Volume Analysis ────────────────────────────────────────────────────
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Signal Activity by Hour")
        try:
            df4 = queries.get_best_hours(date_str, symbols=selected_symbols)
            if df4.empty:
                st.plotly_chart(empty_fig("No volume data for this date"), width='stretch')
            else:
                fig = make_subplots(rows=2, cols=1,
                                    subplot_titles=("Signal Count per Hour", "Spike Ratio Trend"),
                                    vertical_spacing=0.2, shared_xaxes=True)
                fig.add_trace(go.Bar(x=df4['trading_hour'], y=df4['signal_count'],
                                     marker_color=COLORS[0], name='Count',
                                     hovertemplate='Hour %{x}<br>Count: %{y}<extra></extra>'),
                              row=1, col=1)
                fig.add_trace(go.Scatter(x=df4['trading_hour'], y=df4['avg_spike_ratio'],
                                         mode='lines+markers', line=dict(color=COLORS[1], width=2),
                                         name='Avg Spike', hovertemplate='Hour %{x}<br>Avg: %{y:.2f}x<extra></extra>'),
                              row=2, col=1)
                fig.add_trace(go.Scatter(x=df4['trading_hour'], y=df4['max_spike_ratio'],
                                         mode='lines+markers', line=dict(color=COLORS[3], width=2, dash='dash'),
                                         name='Max Spike', hovertemplate='Hour %{x}<br>Max: %{y:.2f}x<extra></extra>'),
                              row=2, col=1)
                fig.update_layout(template=TEMPLATE, height=500, hovermode='x unified')
                st.plotly_chart(fig, width='stretch')
        except Exception as e:
            st.error(f"Query failed: {e}")

    with col2:
        st.subheader("Signal Strength vs Price Move (30-day)")
        try:
            df7 = queries.get_signal_strength(date_range_days=30, symbols=selected_symbols)
            if df7.empty:
                st.plotly_chart(empty_fig("No data available"), width='stretch')
            else:
                order = ['Mild (1.0-1.5x)', 'Moderate (1.5-2.0x)', 'Strong (2.0-3.0x)', 'Extreme (3.0x+)']
                df7['breach_category'] = pd.Categorical(df7['breach_category'], categories=order, ordered=True)
                df7 = df7.sort_values('breach_category')
                fig = go.Figure(go.Bar(
                    x=df7['breach_category'], y=df7['avg_price_move'],
                    marker_color=COLORS[2], text=df7['occurrences'].apply(lambda x: f"n={x}"),
                    textposition='outside',
                    hovertemplate='%{x}<br>Avg Move: %{y:.3f}%<extra></extra>'
                ))
                fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                fig.update_layout(title="Avg Price Move by Spike Magnitude",
                                  xaxis_title="Category", yaxis_title="Price Change (%)",
                                  template=TEMPLATE, height=400)
                st.plotly_chart(fig, width='stretch')
        except Exception as e:
            st.error(f"Query failed: {e}")


# ── Tab 3: Momentum & Correlation ─────────────────────────────────────────────
with tab3:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Multi-Signal Confirmation")
        try:
            df1 = queries.get_multi_signal_confirmation(date_str, symbols=selected_symbols)
            if df1.empty:
                st.plotly_chart(empty_fig("No confirmed signals for this date"), width='stretch')
            else:
                fig = make_subplots(rows=1, cols=2,
                                    subplot_titles=("Direction: UP", "Direction: DOWN"),
                                    horizontal_spacing=0.12)
                for i, (direction, color) in enumerate(zip(['UP', 'DOWN'], [COLORS[2], COLORS[3]]), start=1):
                    d = df1[df1['direction'] == direction] if 'direction' in df1.columns else pd.DataFrame()
                    if not d.empty:
                        fig.add_trace(go.Scatter(
                            x=d['seconds_apart'], y=d['spike_ratio'],
                            mode='markers',
                            marker=dict(size=10, color=color, opacity=0.7),
                            text=d['symbol'],
                            hovertemplate='%{text}<br>Gap: %{x:.0f}s<br>Spike: %{y:.2f}x<extra></extra>',
                            showlegend=False
                        ), row=1, col=i)
                fig.update_xaxes(title_text="Seconds Apart")
                fig.update_yaxes(title_text="Spike Ratio", col=1)
                fig.update_layout(template=TEMPLATE, height=400, hovermode='closest')
                st.plotly_chart(fig, width='stretch')
        except Exception as e:
            st.error(f"Query failed: {e}")

    with col2:
        st.subheader("Top Correlated Pairs (30-day)")
        try:
            df6 = queries.get_stock_correlation(date_range_days=30, symbols=selected_symbols)
            if df6.empty:
                st.plotly_chart(empty_fig("No correlated pairs found"), width='stretch')
            else:
                top = df6.nlargest(10, 'co_signal_count').copy()
                top['pair'] = top['stock_a'] + ' — ' + top['stock_b']
                fig = go.Figure(go.Bar(
                    y=top['pair'], x=top['co_signal_count'],
                    orientation='h', marker_color=COLORS[5],
                    text=top['co_signal_count'], textposition='outside',
                    hovertemplate='%{y}<br>Co-Signals: %{x}<extra></extra>'
                ))
                fig.update_layout(yaxis={'autorange': 'reversed'},
                                  xaxis_title="Co-Signal Count",
                                  template=TEMPLATE, height=400)
                st.plotly_chart(fig, width='stretch')
        except Exception as e:
            st.error(f"Query failed: {e}")


# ── Tab 4: Volatility & Sector ────────────────────────────────────────────────
with tab4:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Volatility Regime (7-day)")
        try:
            df5 = queries.get_volatility_regime(date_range_days=7, symbols=selected_symbols)
            if df5.empty:
                st.plotly_chart(empty_fig("No volatility data"), width='stretch')
            else:
                df5['date'] = pd.to_datetime(df5['date']).dt.strftime('%Y-%m-%d')
                fig = make_subplots(rows=2, cols=1,
                                    subplot_titles=("Daily Signal Count", "Z-Score Trend"),
                                    vertical_spacing=0.15, shared_xaxes=True)
                fig.add_trace(go.Bar(x=df5['date'], y=df5['volatility_signals'],
                                     marker_color=COLORS[4], name='Signals'), row=1, col=1)
                fig.add_trace(go.Scatter(x=df5['date'], y=df5['avg_z_score'],
                                         mode='lines+markers', line=dict(color=COLORS[2], width=2),
                                         name='Avg Z'), row=2, col=1)
                fig.add_trace(go.Scatter(x=df5['date'], y=df5['max_z_score'],
                                         mode='lines+markers', line=dict(color=COLORS[3], dash='dash'),
                                         name='Max Z'), row=2, col=1)
                fig.add_hline(y=2.0, line_dash="dot", line_color="gray", row=2, col=1,
                              annotation_text="Z=2")
                fig.update_layout(template=TEMPLATE, height=500, hovermode='x unified')
                st.plotly_chart(fig, width='stretch')
        except Exception as e:
            st.error(f"Query failed: {e}")

    with col2:
        st.subheader("Sector Rotation by Hour")
        try:
            df2 = queries.get_sector_rotation(date_str, symbols=selected_symbols)
            if df2.empty:
                st.plotly_chart(empty_fig("No sector data for this date"), width='stretch')
            else:
                fig = go.Figure()
                for label, col_name, color in [
                    ('Volume', 'volume_count', COLORS[0]),
                    ('Momentum', 'momentum_count', COLORS[1]),
                    ('Volatility', 'volatility_count', COLORS[3])
                ]:
                    fig.add_trace(go.Bar(
                        x=df2['trading_hour'], y=df2[col_name],
                        name=label, marker_color=color,
                        hovertemplate=f'Hour %{{x}}<br>{label}: %{{y}}<extra></extra>'
                    ))
                fig.update_layout(barmode='group', xaxis_title="Hour (UTC)",
                                  yaxis_title="Signal Count", template=TEMPLATE,
                                  height=500, hovermode='x unified')
                st.plotly_chart(fig, width='stretch')
        except Exception as e:
            st.error(f"Query failed: {e}")


# ── Tab 5: Analytics ──────────────────────────────────────────────────────────
with tab5:
    st.subheader("Signal Win Rate Analysis (30-day)")
    try:
        df3 = queries.get_signal_accuracy(date_range_days=30, symbols=selected_symbols)

        if df3.empty or df3['total_signals'].iloc[0] == 0:
            st.plotly_chart(empty_fig("No win rate data — need 30 days of history"), width='stretch')
        else:
            row = df3.iloc[0]
            total = int(row['total_signals'])
            avg_return = float(row['avg_return_pct'])

            # Metric cards
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Signals", total)
            c2.metric("Win Rate (1%+)", f"{row['win_rate_pct']:.1f}%")
            c3.metric("Avg Return", f"{avg_return:.3f}%",
                      delta=f"{avg_return:.3f}%", delta_color="normal")
            c4.metric("2%+ Profitable", int(row['profitable_2pct']))

            # Win rate bar chart
            thresholds = ['0.5%+', '1%+', '2%+']
            counts = [int(row['profitable_half_pct']), int(row['profitable_1pct']), int(row['profitable_2pct'])]

            col1, col2 = st.columns(2)
            with col1:
                fig = go.Figure(go.Bar(
                    x=thresholds,
                    y=[c / total * 100 for c in counts],
                    marker_color=COLORS[2],
                    text=[f"{c/total*100:.1f}%" for c in counts],
                    textposition='outside',
                    hovertemplate='%{x}<br>Win Rate: %{y:.1f}%<extra></extra>'
                ))
                fig.update_layout(title="Win Rate by Return Threshold",
                                  yaxis=dict(title="Win Rate (%)", range=[0, 100]),
                                  template=TEMPLATE, height=400)
                st.plotly_chart(fig, width='stretch')

            with col2:
                fig2 = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=avg_return,
                    title={'text': "Avg Return per Signal (%)"},
                    gauge={
                        'axis': {'range': [-0.5, 0.5]},
                        'bar': {'color': COLORS[2] if avg_return > 0 else COLORS[3]},
                        'steps': [
                            {'range': [-0.5, 0], 'color': '#2a1a1a'},
                            {'range': [0, 0.5], 'color': '#1a2a1a'}
                        ],
                        'threshold': {'line': {'color': 'white', 'width': 3}, 'value': 0}
                    }
                ))
                fig2.update_layout(template=TEMPLATE, height=400)
                st.plotly_chart(fig2, width='stretch')

    except Exception as e:
        st.error(f"Query failed: {e}")


# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(refresh_interval)
st.rerun()
