import streamlit as st
import time
import plotly.graph_objects as go
import numpy as np
import pandas as pd
from utils.ris_simulator import V2XSimulator

st.set_page_config(page_title="V2X 6G RIS Demo", page_icon="📡", layout="wide")

# تصميم الواجهة (Premium Research Aesthetic)
st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Outfit', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #020024 0%, #090979 35%, #00d4ff 100%);
        padding: 2.5rem; border-radius: 24px; margin-bottom: 2rem; text-align: center;
        box-shadow: 0 10px 40px rgba(0, 212, 255, 0.2); border: 1px solid rgba(255,255,255,0.1);
    }
    .metric-card {
        background: rgba(15, 12, 41, 0.8); backdrop-filter: blur(10px); border-radius: 20px;
        padding: 1.5rem; border: 1px solid rgba(0, 212, 255, 0.15); text-align: center; margin-bottom: 15px;
    }
    .metric-value { font-size: 2rem; font-weight: 700; color: #00d4ff; }
    .metric-label { font-size: 0.8rem; color: #718096; text-transform: uppercase; letter-spacing: 1.5px; }
    .info-panel { background: rgba(0, 212, 255, 0.05); border-left: 4px solid #00d4ff; padding: 1rem; border-radius: 8px; margin: 10px 0; }
    .agent-card { background: linear-gradient(145deg, #1a1a2e, #0f3460); border-radius: 12px; padding: 1rem; border-left: 4px solid #00d4ff; margin-bottom: 0.8rem; text-align: center; }
</style>""", unsafe_allow_html=True)

# إدارة الحالة (State Management)
if "sim" not in st.session_state:
    st.session_state.sim = V2XSimulator()
    st.session_state.running = False
    st.session_state.steps = 0

sim = st.session_state.sim

# الشريط الجانبي (Sidebar)
with st.sidebar:
    st.image("https://img.icons8.com/wired/128/00d4ff/brain.png", width=60)
    st.markdown("### Simulation Controls")
    num_v = st.slider("Vehicle Count", 1, 30, 15)
    speed = st.slider("Speed (km/h)", 80, 500, 120, step=10)
    freq = st.select_slider("Frequency (GHz)", [28, 39, 60, 73], 28)
    st.markdown("---")
    ris_en = st.toggle("Enable RIS Nodes", True)
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        start_btn = st.button("START", type="primary", use_container_width=True)
    with c2:
        stop_btn = st.button("STOP", use_container_width=True)
    if st.button("RESET", use_container_width=True):
        st.session_state.sim = V2XSimulator(); st.session_state.steps = 0; st.session_state.running = False; st.rerun()

if start_btn: st.session_state.running = True
if stop_btn: st.session_state.running = False

st.markdown("""<div class="main-header"><h1>V2X 6G RIS Mobility Performance Hub</h1>
<p>MARL Framework Comparison | IEEE TVT 2026 | InnovCOM Lab</p></div>""", unsafe_allow_html=True)

def build_topology():
    fig = go.Figure()
    # Highway Environment
    fig.add_shape(type="rect", x0=-200, y0=460, x1=4700, y1=540, fillcolor="#1a1c23", line=dict(width=0), layer="below")
    # Road Lanes
    for y in [462, 500, 538]:
        fig.add_trace(go.Scatter(x=[-200, 4700], y=[y, y], mode="lines", 
                                 line=dict(color="rgba(255,255,255,0.2)", width=1, dash="dash" if y==500 else "solid"), showlegend=False))
    
    # 6G gNB & Field
    ff = 28/freq
    for g in sim.gnbs:
        fig.add_shape(type="circle", x0=g.position[0]-500*ff, y0=g.position[1]-500*ff, x1=g.position[0]+500*ff, y1=g.position[1]+500*ff,
                      line=dict(color="rgba(0, 212, 255, 0.1)"), fillcolor="rgba(0, 212, 255, 0.03)", layer="below")
        fig.add_trace(go.Scatter(x=[g.position[0]], y=[g.position[1]], mode="markers+text",
                                 marker=dict(size=40, color="white"), text=["📡"], textfont=dict(size=22), name=f"gNB-{g.gnb_id}"))

    # Connections
    if sim.vehicles:
        for v in sim.vehicles:
            target = next((g for g in sim.gnbs if g.gnb_id == v.connected_gnb), None)
            if target:
                fig.add_trace(go.Scatter(x=[v.position[0], target.position[0]], y=[v.position[1], target.position[1]],
                                         mode="lines", line=dict(color="rgba(72, 187, 120, 0.3)", width=1, dash="dot"), showlegend=False))

    # RIS & Vehicles
    if ris_en:
        fig.add_trace(go.Scatter(x=[r.position[0] for r in sim.ris_panels], y=[r.position[1] for r in sim.ris_panels], 
                                 mode="markers+text", marker=dict(size=25, color="white"), text=["🔳" for _ in sim.ris_panels], 
                                 textfont=dict(size=18), name="RIS Surfaces"))
    if sim.vehicles:
        vcols = ["#48bb78" if v.sinr_db > 12 else "#fbc531" if v.sinr_db > 0 else "#eb4d4b" for v in sim.vehicles]
        fig.add_trace(go.Scatter(x=[v.position[0] for v in sim.vehicles], y=[v.position[1] for v in sim.vehicles], 
                                 mode="markers+text", marker=dict(size=20, color=vcols, line=dict(width=1, color="white")),
                                 text=["🚗" if v.vehicle_id%2==0 else "🚐" for v in sim.vehicles], textfont=dict(size=14), name="Vehicles"))

    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0f1115", height=500,
                      xaxis=dict(range=[-300, 4600], showgrid=False, zeroline=False, showticklabels=False),
                      yaxis=dict(range=[200, 800], showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x"),
                      margin=dict(l=0, r=0, t=20, b=0))
    return fig

# --- Key Metrics (Always Visible) ---
m = sim.get_current_metrics()
st.markdown(f"""
<div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 1rem; margin-bottom: 20px;">
    <div class="metric-card"><div class="metric-label">Avg SINR</div><div class="metric-value">{m["sinr"]:.1f} dB</div></div>
    <div class="metric-card"><div class="metric-label">Latency</div><div class="metric-value">{m["latency"]:.2f} ms</div></div>
    <div class="metric-card"><div class="metric-label">Throughput</div><div class="metric-value">{m["throughput"]:.0f} Mb</div></div>
    <div class="metric-card"><div class="metric-label">HO Success</div><div class="metric-value">{m["hsr"]:.1f}%</div></div>
    <div class="metric-card"><div class="metric-label">Sim Step</div><div class="metric-value">{st.session_state.steps}</div></div>
</div>
""", unsafe_allow_html=True)

# --- Tabs Structure ---
tabs = st.tabs(["🌐 Live Simulation", "📈 Performance Metrics", "📊 Tables (I & II) & Baselines", "🤖 AI Agents Intel", "🔬 RIS & 3D Coverage"])

with tabs[0]:
    st.plotly_chart(build_topology(), width="stretch", config={'displayModeBar': False}, key="live_topology_main")
    
    st.markdown("#### 🚗 Live Connected Vehicles (Telemetry)")
    if len(sim.vehicles) > 0:
        v_data = []
        for v in sim.vehicles:
            status = "Good" if v.sinr_db > 10 else ("Fair" if v.sinr_db > 0 else "Poor")
            v_data.append({
                "ID": v.vehicle_id,
                "Position": f"({int(v.position[0])}, {int(v.position[1])})",
                "Speed": int(v.speed_kmh),
                "gNB": f"gNB-{v.connected_gnb}",
                "SINR": round(v.sinr_db, 1),
                "Latency": round(v.latency_ms, 2),
                "Throughput": round(v.throughput_mbps, 0),
                "EE": round(v.energy_efficiency, 1),
                "SE": round(v.spectral_efficiency, 1),
                "Status": status
            })
        st.dataframe(pd.DataFrame(v_data), width=None, use_container_width=True, hide_index=True)
    else:
        st.info("No active vehicles initialized yet. Start the simulation!")

with tabs[1]:
    st.markdown("#### 🚀 Performance Metrics Over Time")
    mh = sim.metrics_history
    if len(mh.get("time", [])) > 1:
        t = mh["time"]
        c1, c2 = st.columns(2)
        with c1:
            f1 = go.Figure(go.Scatter(x=t, y=mh["sinr"], mode="lines", name="SINR (dB)", line=dict(color="#00d4ff", width=3)))
            f1.update_layout(template="plotly_dark", height=300, title="Avg SINR Progression", uirevision="constant")
            st.plotly_chart(f1, width="stretch", key="perf_sinr")
        with c2:
            f2 = go.Figure(go.Scatter(x=t, y=mh["latency"], mode="lines", name="Latency (ms)", line=dict(color="#f6ad55", width=3)))
            f2.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="URLLC Limit")
            f2.update_layout(template="plotly_dark", height=300, title="E2E Latency Trends", uirevision="constant")
            st.plotly_chart(f2, width="stretch", key="perf_latency")
            
        c3, c4 = st.columns(2)
        with c3:
            f3 = go.Figure(go.Scatter(x=t, y=mh["throughput"], mode="lines", name="Throughput", line=dict(color="#48bb78", width=3)))
            f3.update_layout(template="plotly_dark", height=300, title="Network Throughput (Mbps)", uirevision="constant")
            st.plotly_chart(f3, width="stretch", key="perf_throughput")
        with c4:
            f4 = go.Figure(go.Scatter(x=t, y=mh["hsr"], mode="lines", name="HSR (%)", line=dict(color="#fc8181", width=3)))
            f4.update_layout(template="plotly_dark", height=300, title="Handover Success Rate", uirevision="constant")
            st.plotly_chart(f4, width="stretch", key="perf_hsr")
    else:
        st.info("Start the simulation to generate telemetry data.")

with tabs[2]:
    st.markdown("#### ⚙️ Table I: Simulation Parameters")
    st.markdown('<div class="info-panel">Core network and MARL parameters actively used in this simulation (Synced with config.py & Manuscript Sec. III).</div>', unsafe_allow_html=True)
    
    table1_data = {
        "Parameter": ["Carrier Frequency (f_c)", "System Bandwidth (W)", "Number of gNBs (|B|)", "RIS Panels (|R|)", 
                      "RIS Elements (N)", "Vehicle Speed Domain", "RL Discount Factor (γ)", "RL Learning Rate", "RL Batch Size"],
        "Value": [f"{freq} GHz", "400 MHz", f"{len(sim.gnbs)}", f"{len(sim.ris_panels) if ris_en else 0}", "64", f"{speed} km/h", "0.99", "5e-4", "32"],
        "Manuscript Reference": ["Eq. 2, 5", "Eq. 10", "Section III-A", "Section III-A", "Eq. 8", "Eq. 11", "Eq. 12", "Section VI-A", "Section VI-A"]
    }
    st.dataframe(pd.DataFrame(table1_data), use_container_width=True, hide_index=True)
    st.markdown("---")

    st.markdown("#### 📋 Table II: Comparative Performance Results")
    st.markdown('<div class="info-panel">This table compares the Agent Loop + MARL model (Live Average) against 4 static baseline techniques.</div>', unsafe_allow_html=True)
    
    # Calculate Live averages for "Ours"
    live_vals = [8.2, 0.85, 98.5, 1842.0] # Fallback initial values (Paper values)
    if len(sim.metrics_history.get("sinr", [])) > 0:
        live_vals = [
            round(np.mean(sim.metrics_history["sinr"]), 2),
            round(np.mean(sim.metrics_history["latency"]), 2),
            round(np.mean(sim.metrics_history["hsr"]), 2),
            round(np.mean(sim.metrics_history["throughput"]), 2)
        ]

    comp_data = {
        "Method": ["Agent Loop + MARL (Live)", "MARL Only", "Conventional HO", "Static RIS", "Single-Agent RL"],
        "HSR (%)": [f"{live_vals[2]:.1f}", "95.2", "87.3", "91.8", "89.6"],
        "SINR (dB)": [f"+{live_vals[0]:.1f}", "+7.8", "N/A", "+5.1", "+4.3"],
        "Latency (ms)": [f"{live_vals[1]:.2f}", "0.92", "1.45", "1.12", "1.28"],
        "Throughput": [
            f"+{((live_vals[3]-1597.0)/1597.0)*100:.1f}%" if live_vals[3] > 0 else "+15.3%", 
            "Baseline", "-23.7%", "-12.4%", "-18.5%"
        ]
    }
    df = pd.DataFrame(comp_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    # Radar Chart based on dynamic live vals
    r_live = [
        min(10, max(0, live_vals[0])),               # SINR mapping (~0-10)
        min(10, max(0, 10 - live_vals[1] * 4)),      # Latency Inv mapping (lower latency = higher score)
        min(10, max(0, live_vals[2] / 10)),          # HSR mapping 0-100 -> 0-10
        min(10, max(0, live_vals[3] / 200))          # Throughput ~1800 Mbps -> 10
    ]
    cats = ["SINR", "Latency (Inv)", "HSR", "Throughput"]
    fig_r = go.Figure()
    fig_r.add_trace(go.Scatterpolar(r=[1, 2, 4, 3], theta=cats, fill="toself", name="Conventional HO"))
    fig_r.add_trace(go.Scatterpolar(r=r_live, theta=cats, fill="toself", name="Agent Loop + MARL (Live)", line_color="#00d4ff"))
    fig_r.update_layout(template="plotly_dark", polar=dict(radialaxis=dict(visible=False, range=[0, 10])), height=450, title="Live Relative Performance Radar", uirevision="constant")
    st.plotly_chart(fig_r, width="stretch", key="radar_performance")

with tabs[3]:
    st.markdown("#### 🤖 AI Agent Intelligence Architecture (3 Autonomous Agents)")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="agent-card"><b>📡 RIS Agent</b><br><small>Phase Shift Optimization using QMIX</small></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="agent-card"><b>🔄 HO Agent</b><br><small>Handover Management using MAPPO</small></div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="agent-card"><b>📊 Resource Agent</b><br><small>Proportional Fair Spectrum & Power</small></div>', unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("#### ⚙️ The Agent Loop Pattern")
    st.markdown("""
    <div style="background: rgba(26,26,46,0.5); padding: 1.5rem; border-radius: 12px; text-align: center; color: #a0aec0; border: 1px dashed rgba(0,212,255,0.3); margin-bottom: 1rem;">
        <b style="color:#00d4ff">Analyze</b> (Channel State) &rarr; <b style="color:#00d4ff">Select</b> (Action Policy) &rarr; <b style="color:#00d4ff">Execute</b> (Update Network) &rarr; <b style="color:#00d4ff">Validate</b> (Check QoS) &rarr; <b style="color:#00d4ff">Iterate</b>
    </div>
    """, unsafe_allow_html=True)

    mh = sim.metrics_history
    if len(mh.get("time", [])) > 1:
        st.markdown("#### 📈 MARL Convergence Real-Time Progress")
        c1, c2 = st.columns(2)
        with c1:
            fig_r = go.Figure(go.Scatter(x=mh["time"], y=mh.get("convergence_reward", []), mode="lines", line=dict(color="#48bb78")))
            fig_r.update_layout(template="plotly_dark", height=250, title="MARL Cumulative Reward", margin=dict(l=0, r=0, t=30, b=0), uirevision="constant")
            st.plotly_chart(fig_r, width="stretch", key="marl_reward")
        with c2:
            fig_l = go.Figure(go.Scatter(x=mh["time"], y=mh.get("convergence_loss", []), mode="lines", line=dict(color="#fc8181")))
            fig_l.update_layout(template="plotly_dark", height=250, title="Actor-Critic Policy Loss", margin=dict(l=0, r=0, t=30, b=0), uirevision="constant")
            st.plotly_chart(fig_l, width="stretch", key="marl_loss")

with tabs[4]:
    st.markdown("#### 🔬 RIS Phase Shift Analysis")
    panel = sim.ris_panels[0]
    fig_bar = go.Figure(data=[go.Bar(x=list(range(64)), y=panel.phases, marker_color="#00d4ff")])
    fig_bar.update_layout(template="plotly_dark", height=350, title="Phase Configuration (Panel 0)", xaxis_title="Element Index", yaxis_title="Phase (rad)", uirevision="constant")
    st.plotly_chart(fig_bar, width="stretch", key="ris_phases_chart")


# --- Global Simulation Update Loop ---
# This executes at the end of every page load. If running, it steps the sim and triggers a rerun.
if st.session_state.running:
    # Lifecycle
    if len(sim.vehicles) < num_v: 
        for _ in range(num_v - len(sim.vehicles)): sim.add_vehicle(speed)
    elif len(sim.vehicles) > num_v: 
        sim.vehicles = sim.vehicles[:num_v]
    for v in sim.vehicles: 
        v.speed_kmh = speed
    
    sim.step(ris_en, 64, 4, freq, 400)
    st.session_state.steps += 1
    
    time.sleep(0.3)
    st.rerun()

# --- Global Footer (Always Visible) ---
st.markdown("""
<div style="text-align: center; margin-top: 50px; padding: 20px; border-top: 1px solid rgba(255,255,255,0.1); color: #718096; line-height: 1.8;">
    <p><b>V2X 6G RIS Mobility Demo</b> | IEEE TVT 2026</p>
    <p>AlHussein A. Al-Sahati & Houda Chihi | InnovCOM Laboratory, Sup'Com</p>
    <p style="color: #00d4ff;">Agent Loop Pattern + QMIX + MAPPO | 6G mmWave 28GHz</p>
</div>
""", unsafe_allow_html=True)
