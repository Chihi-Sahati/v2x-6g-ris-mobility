# V2X 6G RIS Mobility Demo

Interactive demonstration of AI Agent-Based Mobility Management with Reconfigurable Intelligent Surfaces for 6G V2X Networks.

## Quick Start

### Windows
```bash
run_demo.bat
```

### Manual
```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Features

- **Real-Time Network Topology** - Live visualization of vehicles, gNBs, and RIS panels
- **Performance Charts** - SINR, Latency, Throughput, and HSR over time
- **AI Agent Dashboard** - Monitor Agent Loop Pattern and MARL decisions
- **RIS Analysis** - Phase shift visualization and gain comparison
- **Results Table** - Comparative performance with radar charts

## Controls

| Control | Description |
|---------|-------------|
| Vehicles | Adjust number of simulated vehicles (1-30) |
| Speed | Set vehicle speed (80-500 km/h) |
| RIS Toggle | Enable/disable RIS assistance |
| RIS Elements | Configure RIS panel size (16-256) |
| Phase Bits | Set phase quantization (1-6 bits) |

## Technologies

- Streamlit
- Plotly
- NumPy / Pandas
- SciPy
