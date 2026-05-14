"""MAG10 Monitor — Real-Time Trading Signal Dashboard (Streamlit)"""
import os
import time
from datetime import datetime, date, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
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


def signal_score(signal_type: str, strength: float, session_pct: float, confirmation: str = None) -> int:
    """Score a signal 1-10 based on type, strength, and session momentum"""
    score = 0
    s = strength or 0
    if signal_type == 'volume':
        score += min(s * 1.5, 4)
        score += 3 if confirmation == 'CONFIRMED' else 0
        score += 1 if s >= 3.0 else 0
    elif signal_type == 'momentum':
        score += min(s * 2, 5)
        score += 1 if s >= 1.0 else 0
    elif signal_type == 'volatility':
        score += min(s * 1.5, 5)
        score += 1 if s >= 3.0 else 0
    score += 2 if (session_pct or 0) > 1 else 1 if (session_pct or 0) > 0 else 0
    return min(10, round(score))


def score_badge(score: int) -> str:
    if score >= 8:   return f"🔥 {score}/10"
    if score >= 6:   return f"🟢 {score}/10"
    if score >= 4:   return f"🟡 {score}/10"
    return f"🔴 {score}/10"


def age_badge(timestamp) -> str:
    minutes = (datetime.now(timestamp.tzinfo) - timestamp).total_seconds() / 60
    if minutes < 5:   return f"🟢 {minutes:.0f}m ago"
    if minutes < 15:  return f"🟡 {minutes:.0f}m ago"
    return f"🔴 {minutes:.0f}m ago (stale)"


# ── Main title ────────────────────────────────────────────────────────────────
st.title("MAG10 Monitor — Trading Signal Dashboard")
st.caption(f"Showing data for **{date_str}** | Symbols: **{', '.join(selected_symbols)}**")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🔴 Live Signals",
    "📊 Volume Analysis",
    "🔗 Momentum & Correlation",
    "📈 Volatility & Sector",
    "📉 Analytics",
    "📰 News & Sentiment",
])

# ── Tab 1: Live Signals ───────────────────────────────────────────────────────
with tab1:

    # ── Row 1: Market Breadth Bar ─────────────────────────────────────────────
    try:
        breadth_df = queries.get_market_breadth()
        if not breadth_df.empty:
            up   = int((breadth_df['pct_change'] > 0).sum())
            down = int((breadth_df['pct_change'] < 0).sum())
            flat = int((breadth_df['pct_change'] == 0).sum())
            total = len(breadth_df)

            if up >= 7:
                sentiment, color = "BULLISH SESSION", "#22c55e"
            elif up >= 5:
                sentiment, color = "MIXED SESSION", "#f59e0b"
            else:
                sentiment, color = "BEARISH SESSION", "#ef4444"

            advice = "Trade aggressively" if up >= 7 else "Trade selectively" if up >= 5 else "Reduce size or sit out"
            st.markdown(
                f"""<div style="background:{color}18;border-left:5px solid {color};
                    padding:12px 18px;border-radius:6px;margin-bottom:16px">
                    <b style="color:{color};font-size:15px">{sentiment}</b>
                    <span style="color:#475569;margin-left:16px">
                        {up}/10 UP &nbsp;·&nbsp; {down}/10 DOWN &nbsp;·&nbsp; {flat}/10 FLAT
                    </span>
                    <span style="color:#64748b;margin-left:16px;font-style:italic">{advice}</span>
                </div>""",
                unsafe_allow_html=True
            )
    except Exception:
        pass

    # ── Row 2: Signal Cluster Alert ───────────────────────────────────────────
    try:
        clusters_df = queries.get_signal_clusters(minutes_back=60)
        if not clusters_df.empty:
            clusters_df['bucket_start'] = pd.to_datetime(clusters_df['bucket_start'], utc=True)
            # Banner for any cluster in the last 5 minutes
            cutoff = pd.Timestamp.now(tz='UTC') - pd.Timedelta(minutes=5)
            hot = clusters_df[clusters_df['bucket_start'] >= cutoff]
            if not hot.empty:
                r = hot.iloc[0]
                t_label = r['bucket_start'].strftime('%H:%M')
                type_parts = []
                if int(r.get('volume_count', 0)) > 0:
                    type_parts.append(f"{int(r['volume_count'])} VOL")
                if int(r.get('momentum_count', 0)) > 0:
                    type_parts.append(f"{int(r['momentum_count'])} MOM")
                if int(r.get('volatility_count', 0)) > 0:
                    type_parts.append(f"{int(r['volatility_count'])} VOLA")
                type_breakdown = ' · '.join(type_parts)
                st.markdown(
                    f"""<div style="background:#fef2f2;border-left:5px solid #ef4444;
                        padding:12px 18px;border-radius:6px;margin-bottom:8px">
                        <b style="color:#ef4444;font-size:15px">🚨 CLUSTER ALERT</b>
                        <span style="color:#0f172a;margin-left:12px">
                            {r['symbols_count']} stocks fired within 2 min at {t_label} UTC —
                            <b>{r['symbols_list']}</b>
                        </span>
                        <span style="color:#64748b;margin-left:12px;font-size:13px">
                            {type_breakdown} &nbsp;·&nbsp; only VOL spikes appear in Active Signals below
                        </span>
                    </div>""",
                    unsafe_allow_html=True
                )

            # Cluster history (last hour)
            with st.expander(f"Signal Clusters — last 60 min ({len(clusters_df)} found)", expanded=False):
                display = clusters_df.copy()
                display['time'] = display['bucket_start'].dt.strftime('%H:%M UTC')
                st.caption("Clusters count all signal types. Only VOL spikes appear in Active Signals.")
                st.dataframe(
                    display[['time', 'symbols_count', 'symbols_list', 'volume_count', 'momentum_count', 'volatility_count']]
                    .rename(columns={'symbols_count': '# stocks', 'symbols_list': 'symbols',
                                     'volume_count': 'VOL', 'momentum_count': 'MOM',
                                     'volatility_count': 'VOLA'}),
                    hide_index=True
                )
    except Exception:
        pass

    # ── Row 3: Session Leaderboard ────────────────────────────────────────────
    try:
        lb_df = queries.get_session_leaderboard()
        if not lb_df.empty:
            st.markdown("**Today's Focus Stocks:**")
            cols = st.columns(min(len(lb_df), 5))
            for i, (_, row) in enumerate(lb_df.head(5).iterrows()):
                with cols[i]:
                    st.metric(
                        label=row['symbol'],
                        value=f"{int(row['total_signals'])} signals",
                        delta=f"V:{int(row['volume_count'])} M:{int(row['momentum_count'])} Vol:{int(row['volatility_count'])}"
                    )
    except Exception:
        pass

    # ── Row 4: Opening Range Breakout ────────────────────────────────────────
    try:
        orb_df = queries.get_opening_range(date_str, symbols=selected_symbols)
        if not orb_df.empty:
            breakouts = orb_df[orb_df['orb_status'] != 'IN RANGE']
            label = f"Opening Range Breakout — {len(breakouts)} breakout signals today"
            with st.expander(label, expanded=len(breakouts) > 0):
                orb_df['timestamp'] = pd.to_datetime(orb_df['timestamp'])
                orb_df['time'] = orb_df['timestamp'].dt.strftime('%H:%M:%S')

                # OR levels table
                or_levels = (orb_df[['symbol', 'or_high', 'or_low', 'or_size']]
                             .drop_duplicates('symbol')
                             .sort_values('symbol'))
                st.caption("Opening range levels (first 30 min)")
                st.dataframe(or_levels.rename(columns={
                    'or_high': 'OR High', 'or_low': 'OR Low', 'or_size': 'Range Size'
                }), hide_index=True)

                if not breakouts.empty:
                    st.caption("Signals that broke the opening range")
                    for _, r in breakouts.iterrows():
                        is_up   = r['orb_status'] == 'BREAKOUT ↑'
                        color   = '#22c55e' if is_up else '#ef4444'
                        pct_val = r['pct_above_high'] if is_up else r['pct_above_low']
                        st.markdown(
                            f'<div style="border-left:4px solid {color};padding:8px 14px;'
                            f'margin-bottom:6px;background:#f8fafc;border-radius:4px">'
                            f'<b style="color:#0f172a">{r["symbol"]}</b> '
                            f'<span style="background:{"#dcfce7" if is_up else "#fef2f2"};'
                            f'color:{color};font-size:11px;font-weight:700;padding:2px 8px;'
                            f'border-radius:12px">{r["orb_status"]}</span> '
                            f'<span style="color:#475569;margin-left:8px">${r["price"]:.2f} '
                            f'· Spike {r["spike_ratio"]:.2f}x · {r["time"]}</span> '
                            f'<span style="color:{color};margin-left:8px">{pct_val:+.2f}% vs OR</span>'
                            f'</div>',
                            unsafe_allow_html=True
                        )
    except Exception:
        pass

    st.markdown("---")

    # ── Row 5: All Active Signals ─────────────────────────────────────────────
    st.subheader("Active Signals (Last 10 Minutes)")
    try:
        df = queries.get_all_realtime_signals(minutes_back=10, symbols=selected_symbols)

        if df.empty:
            st.info("No signals in the last 10 minutes. Market may be closed or quiet.")
        else:
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            df['score'] = df.apply(
                lambda r: signal_score(r['signal_type'], r['strength'],
                                       r.get('session_pct_change', 0),
                                       r.get('confirmation')), axis=1
            )
            df['score_badge'] = df['score'].apply(score_badge)
            df['age_badge']   = df['timestamp'].apply(age_badge)
            df = df.sort_values('score', ascending=False)

            # ── Signal cards (top 5) ──────────────────────────────────────────
            TYPE_STYLE = {
                'volume':     ('#dbeafe', '#1d4ed8'),
                'momentum':   ('#dcfce7', '#15803d'),
                'volatility': ('#fff7ed', '#c2410c'),
            }
            TYPE_BORDER = {
                'volume':     lambda r: '#22c55e' if r.get('confirmation') == 'CONFIRMED' else '#f59e0b',
                'momentum':   lambda r: '#22c55e',
                'volatility': lambda r: '#f97316',
            }

            def strength_label(r) -> str:
                stype, s = r['signal_type'], r.get('strength') or 0
                if stype == 'volume':
                    return f"Spike: <b>{s:.2f}x</b>"
                if stype == 'momentum':
                    candles = int(r['extra_metric']) if r.get('extra_metric') else 0
                    return f"Move: <b>{s:.2f}%</b> · {candles} candles"
                return f"Z-score: <b>{s:.2f}σ</b>"

            st.markdown("**Top Signals:**")
            for _, r in df.head(5).iterrows():
                stype        = r['signal_type']
                type_bg, type_color = TYPE_STYLE.get(stype, ('#f1f5f9', '#475569'))
                border_color = TYPE_BORDER[stype](r)
                direction_icon = "↑" if r.get('direction') == 'UP' else "↓" if r.get('direction') == 'DOWN' else ""
                session_pct  = r.get('session_pct_change') or 0
                session_color = "#16a34a" if session_pct > 0 else "#dc2626"
                confirmation  = r.get('confirmation') or ''
                conf_html = (
                    f'<span style="color:{border_color};font-weight:600">{confirmation}</span>'
                    if confirmation else ''
                )
                price = r.get('price') or 0

                card_html = (
                    f'<div style="border:1px solid #e2e8f0;border-left:4px solid {border_color};'
                    f'border-radius:6px;padding:12px 16px;margin-bottom:8px;'
                    f'background:#f8fafc;display:flex;align-items:center;gap:16px;flex-wrap:wrap">'
                    f'<span style="font-size:18px;font-weight:bold;color:#0f172a;min-width:60px">{r["symbol"]}</span>'
                    f'<span style="background:{type_bg};color:{type_color};font-size:11px;'
                    f'font-weight:700;padding:2px 8px;border-radius:12px;white-space:nowrap">{stype.upper()}</span>'
                    f'<span style="font-size:16px">{r["score_badge"]}</span>'
                    f'<span style="color:#2563eb;font-size:16px;font-weight:600">${price:.2f}</span>'
                    f'<span style="color:#475569">{strength_label(r)}</span>'
                    + (f'<span style="color:{border_color};font-weight:600">{confirmation}</span>' if confirmation else '')
                    + f'<span style="color:{session_color}">{direction_icon} {session_pct:.2f}% session</span>'
                    f'<span style="color:#94a3b8;font-size:13px;margin-left:auto">{r["age_badge"]}</span>'
                    f'</div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)

            st.markdown("---")

            # ── Charts ────────────────────────────────────────────────────────
            TYPE_COLORS = {'volume': COLORS[0], 'momentum': COLORS[2], 'volatility': COLORS[3]}

            def bubble_size(row):
                s = row.get('strength') or 0
                if row['signal_type'] == 'volume':
                    return max(10, min(50, s * 7))
                if row['signal_type'] == 'momentum':
                    return max(10, min(50, s * 30))
                return max(10, min(50, s * 9))  # volatility

            fig = go.Figure()
            for stype in df['signal_type'].unique():
                d = df[df['signal_type'] == stype]
                fig.add_trace(go.Scatter(
                    x=d['timestamp'], y=d['price'],
                    mode='markers',
                    marker=dict(
                        size=[bubble_size(r) for _, r in d.iterrows()],
                        opacity=0.8,
                        color=TYPE_COLORS.get(stype, COLORS[5]),
                        line=dict(width=1, color='white')
                    ),
                    text=[f"{r['symbol']} [{r['signal_type']}]<br>"
                          f"Price: ${(r.get('price') or 0):.2f}<br>"
                          f"Strength: {(r.get('strength') or 0):.2f}<br>"
                          f"Score: {r['score']}/10"
                          for _, r in d.iterrows()],
                    hovertemplate='%{text}<extra></extra>',
                    name=stype
                ))
            fig.update_layout(title="Signal Timeline (bubble = strength)",
                              xaxis_title="Time", yaxis_title="Price (USD)",
                              template=TEMPLATE, height=520, hovermode='closest')
            st.plotly_chart(fig, width='stretch')

            # Signal type breakdown pie
            type_counts = df['signal_type'].value_counts()
            pie_colors  = [TYPE_COLORS.get(t, COLORS[5]) for t in type_counts.index]
            fig2 = go.Figure(go.Pie(
                labels=type_counts.index, values=type_counts.values,
                marker=dict(colors=pie_colors),
                textinfo='label+percent', hole=0.4
            ))
            fig2.update_layout(title="Signal Mix", template=TEMPLATE, height=380)
            st.plotly_chart(fig2, width='stretch')

            st.dataframe(
                df[['symbol', 'signal_type', 'score_badge', 'price', 'strength', 'direction', 'age_badge']]
                .rename(columns={'score_badge': 'score', 'age_badge': 'age',
                                 'signal_type': 'type', 'direction': 'dir'})
                .head(15),
                hide_index=True
            )

    except Exception as e:
        st.error(f"Query failed: {e}")


# ── Tab 2: Volume Analysis ────────────────────────────────────────────────────
with tab2:

    # ── RVOL ──────────────────────────────────────────────────────────────────
    st.subheader("Relative Volume (RVOL) — Today vs 30-Day Average")
    try:
        rvol_df = queries.get_rvol(date_str, symbols=selected_symbols)
        if rvol_df.empty:
            st.plotly_chart(empty_fig("No RVOL data for this date"), width='stretch')
        else:
            rvol_df['rvol_signals'] = rvol_df['rvol_signals'].fillna(0)
            bar_colors = [
                '#22c55e' if v >= 1.5 else '#f59e0b' if v >= 1.0 else '#ef4444'
                for v in rvol_df['rvol_signals']
            ]
            fig_rvol = go.Figure(go.Bar(
                x=rvol_df['trading_hour'],
                y=rvol_df['rvol_signals'],
                marker_color=bar_colors,
                text=[f"{v:.1f}x" for v in rvol_df['rvol_signals']],
                textposition='outside',
                customdata=rvol_df[['today_count', 'avg_signal_count']].values,
                hovertemplate=(
                    'Hour %{x}:00<br>'
                    'RVOL: %{y:.2f}x<br>'
                    'Today: %{customdata[0]} signals<br>'
                    'Avg: %{customdata[1]:.1f} signals'
                    '<extra></extra>'
                ),
                name='RVOL'
            ))
            fig_rvol.add_hline(y=1.0, line_dash='dash', line_color='white',
                               opacity=0.5, annotation_text='Baseline (1x)')
            fig_rvol.add_hline(y=1.5, line_dash='dot', line_color='#22c55e',
                               opacity=0.4, annotation_text='Hot (1.5x)')
            fig_rvol.update_layout(
                xaxis_title="Trading Hour (UTC)", yaxis_title="Relative Volume",
                template=TEMPLATE, height=320, showlegend=False
            )
            st.plotly_chart(fig_rvol, width='stretch')
    except Exception as e:
        st.error(f"RVOL query failed: {e}")

    st.markdown("---")

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
    st.subheader("Signal Win Rate Analysis")

    fc1, fc2 = st.columns(2)
    with fc1:
        analytics_days = st.select_slider(
            "Lookback period",
            options=[7, 14, 30, 60, 90],
            value=30,
            format_func=lambda x: f"{x} days"
        )
    with fc2:
        min_spike = st.slider(
            "Min spike ratio filter",
            min_value=1.0, max_value=5.0, value=1.0, step=0.5,
            format="%.1fx"
        )

    try:
        df3 = queries.get_signal_accuracy(date_range_days=analytics_days, symbols=selected_symbols,
                                          min_spike_ratio=min_spike)

        if df3.empty or df3['total_signals'].iloc[0] == 0:
            st.plotly_chart(empty_fig(f"No win rate data for the last {analytics_days} days"), width='stretch')
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

    # ── Symbol-level win rates ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Win Rate by Symbol")
    try:
        sym_df = queries.get_symbol_win_rates(
            date_range_days=analytics_days, symbols=selected_symbols,
            min_spike_ratio=min_spike
        )
        if sym_df.empty:
            st.info("Not enough data for symbol breakdown.")
        else:
            sym_df = sym_df[sym_df['total_signals'] >= 3]
            bar_colors = ['#22c55e' if r >= 50 else '#f59e0b' if r >= 35 else '#ef4444'
                          for r in sym_df['win_rate_pct'].fillna(0)]
            fig_sym = go.Figure(go.Bar(
                y=sym_df['symbol'], x=sym_df['win_rate_pct'],
                orientation='h',
                marker_color=bar_colors,
                text=[f"{r['win_rate_pct']:.1f}% ({int(r['total_signals'])} signals)"
                      for _, r in sym_df.iterrows()],
                textposition='outside',
                hovertemplate='%{y}<br>Win Rate: %{x:.1f}%<extra></extra>'
            ))
            fig_sym.add_vline(x=50, line_dash='dash', line_color='white',
                              opacity=0.4, annotation_text='50%')
            fig_sym.update_layout(
                xaxis=dict(title="Win Rate (1%+ return)", range=[0, 100]),
                yaxis=dict(autorange='reversed'),
                template=TEMPLATE, height=max(300, len(sym_df) * 45)
            )
            st.plotly_chart(fig_sym, width='stretch')

            st.dataframe(
                sym_df[['symbol', 'total_signals', 'win_rate_pct', 'avg_return_pct',
                         'profitable_1pct', 'profitable_2pct']]
                .rename(columns={'total_signals': 'signals', 'win_rate_pct': 'win_rate_%',
                                 'avg_return_pct': 'avg_return_%',
                                 'profitable_1pct': '1%+ wins', 'profitable_2pct': '2%+ wins'}),
                hide_index=True
            )
    except Exception as e:
        st.error(f"Symbol win rate query failed: {e}")

    # ── Per-signal P&L ────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Per-Signal P&L (5 / 15 / 30 min)")
    try:
        pnl_df = queries.get_per_signal_pnl(
            date_range_days=analytics_days, symbols=selected_symbols
        )
        if pnl_df.empty:
            st.info("No per-signal P&L data available.")
        else:
            pnl_df['signal_time'] = pd.to_datetime(pnl_df['signal_time'])

            fig_pnl = go.Figure()
            for label, col, color in [
                ('5 min',  'pnl_5m_pct',  COLORS[0]),
                ('15 min', 'pnl_15m_pct', COLORS[2]),
                ('30 min', 'pnl_30m_pct', COLORS[1]),
            ]:
                valid = pnl_df[pnl_df[col].notna()]
                fig_pnl.add_trace(go.Scatter(
                    x=valid['spike_ratio'], y=valid[col],
                    mode='markers',
                    marker=dict(size=7, color=color, opacity=0.65),
                    name=label,
                    hovertemplate=f'{label}<br>Spike: %{{x:.2f}}x<br>P&L: %{{y:.2f}}%<extra></extra>'
                ))
            fig_pnl.add_hline(y=0, line_dash='dash', line_color='white', opacity=0.4)
            fig_pnl.update_layout(
                title="P&L vs Spike Ratio — does a bigger spike mean a bigger move?",
                xaxis_title="Spike Ratio", yaxis_title="Price Change (%)",
                template=TEMPLATE, height=420, hovermode='closest'
            )
            st.plotly_chart(fig_pnl, width='stretch')

            display_pnl = pnl_df[['signal_time', 'symbol', 'spike_ratio', 'entry_price',
                                   'pnl_5m_pct', 'pnl_15m_pct', 'pnl_30m_pct']].copy()
            display_pnl['signal_time'] = display_pnl['signal_time'].dt.strftime('%Y-%m-%d %H:%M')

            def color_pnl(val):
                if pd.isna(val): return ''
                return 'color: #16a34a' if val > 0 else 'color: #dc2626'

            st.dataframe(
                display_pnl.rename(columns={
                    'signal_time': 'time', 'spike_ratio': 'spike',
                    'entry_price': 'entry', 'pnl_5m_pct': '5m %',
                    'pnl_15m_pct': '15m %', 'pnl_30m_pct': '30m %'
                }).head(50),
                hide_index=True
            )
    except Exception as e:
        st.error(f"Per-signal P&L query failed: {e}")


# ── Tab 6: News & Sentiment ───────────────────────────────────────────────────
FINNHUB_KEY = os.getenv('FINNHUB_API_KEY', '')

POS_WORDS = {'record','beat','surge','rally','gain','rise','high','growth','profit',
             'upgrade','strong','buy','soar','exceed','boost'}
NEG_WORDS = {'miss','fall','drop','decline','loss','cut','downgrade','concern',
             'warning','weak','sell','crash','layoff','lawsuit','investigation'}

@st.cache_data(ttl=900)
def fetch_news(symbol: str, from_date: str, to_date: str) -> list:
    if not FINNHUB_KEY:
        return []
    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={symbol}&from={from_date}&to={to_date}&token={FINNHUB_KEY}",
            timeout=5
        )
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

with tab6:
    if not FINNHUB_KEY:
        st.warning("Set `FINNHUB_API_KEY` in your .env file to enable this tab.")
        st.stop()

    if st.button("Load / Refresh News", type="primary"):
        st.cache_data.clear()
        st.session_state['news_loaded'] = True

    if not st.session_state.get('news_loaded'):
        st.info("Click **Load / Refresh News** to fetch headlines from Finnhub.")
        st.stop()

    st.subheader("News & Sentiment")
    st.caption(f"Showing news from **{date_str}** → today · symbols from sidebar")

    # date_str comes from the sidebar date picker
    to_date   = date.today().strftime('%Y-%m-%d')
    from_date = date_str  # sidebar date

    # ── Sentiment scores from headlines ──────────────────────────────────────
    st.markdown("**Headline Sentiment by Symbol**")
    sent_cols = st.columns(min(len(selected_symbols), 5))
    for i, sym in enumerate(selected_symbols[:5]):
        arts = fetch_news(sym, from_date, to_date)
        pos = sum(1 for a in arts if any(w in a.get('headline','').lower() for w in POS_WORDS))
        neg = sum(1 for a in arts if any(w in a.get('headline','').lower() for w in NEG_WORDS))
        total_arts = len(arts)
        bull_pct = round(pos / (pos + neg) * 100) if (pos + neg) > 0 else 50
        with sent_cols[i]:
            st.metric(sym, f"{bull_pct}% bull",
                      delta=f"{bull_pct - 50:+d}% vs neutral",
                      delta_color="normal" if bull_pct >= 50 else "inverse",
                      help=f"{total_arts} articles · {pos} positive · {neg} negative")

    st.markdown("---")

    # ── News headlines (all sidebar symbols, combined feed) ──────────────────
    all_articles = []
    for sym in selected_symbols:
        for a in fetch_news(sym, from_date, to_date):
            a['_symbol'] = sym
            all_articles.append(a)

    if not all_articles:
        st.info(f"No news found for selected symbols from {from_date}.")
    else:
        all_articles = sorted(all_articles, key=lambda x: x.get('datetime', 0), reverse=True)
        st.caption(f"{len(all_articles)} articles across {len(selected_symbols)} symbols · showing latest 30")
        for a in all_articles[:30]:
            dt_str   = datetime.utcfromtimestamp(a.get('datetime', 0)).strftime('%b %d %H:%M UTC')
            headline = a.get('headline', '')
            source   = a.get('source', '')
            url      = a.get('url', '#')
            sym_tag  = a.get('_symbol', '')
            summary  = a.get('summary', '')[:200] + ('…' if len(a.get('summary', '')) > 200 else '')
            h_lower  = headline.lower()
            is_pos   = any(w in h_lower for w in POS_WORDS)
            is_neg   = any(w in h_lower for w in NEG_WORDS)
            border   = '#22c55e' if is_pos else '#ef4444' if is_neg else '#cbd5e1'
            dot      = '🟢' if is_pos else '🔴' if is_neg else '⚪'
            st.markdown(
                f'<div style="border:1px solid #e2e8f0;border-left:4px solid {border};'
                f'border-radius:6px;padding:12px 16px;margin-bottom:8px;background:#f8fafc">'
                f'<span style="color:#64748b;font-size:12px">{dot} '
                f'<b style="color:#1d4ed8">{sym_tag}</b> · {source} · {dt_str}</span>'
                f'<br><a href="{url}" target="_blank" style="color:#0f172a;font-weight:600;'
                f'text-decoration:none;font-size:14px">{headline}</a>'
                f'<p style="color:#475569;font-size:13px;margin:6px 0 0">{summary}</p>'
                f'</div>',
                unsafe_allow_html=True
            )


# ── Auto-refresh ──────────────────────────────────────────────────────────────
time.sleep(refresh_interval)
st.rerun()
