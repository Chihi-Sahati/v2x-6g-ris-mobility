# AI Agent-Based Mobility Management with Reconfigurable Intelligent Surfaces for 6G V2X Networks

[![IEEE TVT](https://img.shields.io/badge/IEEE%20Transactions%20on%20Vehicular%20Technology-Submitted-blue)](https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=25)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Authors

**AlHussein A. Al-Sahati**<sup>1</sup>, Member, IEEE and **Houda Chihi**<sup>2</sup>, Senior Member, IEEE

<sup>1</sup> Military Academy for Security and Strategic Sciences, Benghazi, Libya  
<sup>2</sup> Higher School of Communication of Tunis (Sup'Com), University of Carthage, Ariana, Tunisia

**Contact:** hussein.alagore@gmail.com, houda.chihi@supcom.tn

---

## Abstract

The convergence of sixth-generation (6G) wireless networks, vehicle-to-everything (V2X) communications, and Reconfigurable Intelligent Surfaces (RIS) presents unprecedented opportunities for revolutionizing mobility management in high-speed vehicular scenarios. This paper proposes a novel decentralized AI Agent framework that synergistically integrates Multi-Agent Reinforcement Learning (MARL) with the Agent Loop Pattern from NetOps-Guardian-AI for dynamic optimization of RIS phase shifts and handover protocols in ultra-reliable low-latency communication (URLLC) scenarios. Our framework comprises three specialized agents implementing the iterative decision cycle: a RIS Optimization Agent that dynamically adjusts phase shifts for coverage enhancement, a Handover Management Agent that makes proactive handover decisions based on trajectory prediction, and a Resource Allocation Agent that optimizes spectrum and power allocation.

We formulate the joint optimization problem as a constrained Markov Decision Process (CMDP) and employ QMIX and Multi-Agent Proximal Policy Optimization (MAPPO) algorithms with centralized training and decentralized execution. Extensive simulations under realistic 6G mmWave channel conditions demonstrate that our proposed framework achieves a 98.5% handover success rate at vehicle speeds up to 500 km/h, while maintaining URLLC latency requirements below 1 ms with 99.999% reliability. The RIS-assisted scheme provides an average SINR improvement of 8.2 dB compared to non-RIS baselines, and the Agent Loop-enhanced multi-agent approach outperforms single-agent and traditional methods by 15.3% and 41.3%, respectively, in terms of overall network throughput. Comprehensive convergence analysis using Lyapunov stability theory validates the theoretical guarantees of the proposed algorithms.

---

## Document Statistics

| Metric | Value |
|--------|-------|
| Manuscript Pages | 22 |
| Equations | 28 |
| Figures | 10 |
| Tables | 2 |
| References | 15 |

---

## Repository Contents

| Directory | Description |
|-----------|-------------|
| `code/` | Core implementation of AI agents and MARL algorithms |
| `code/agents/` | RIS Optimization, Handover Management, Resource Allocation agents |
| `code/algorithms/` | QMIX and MAPPO implementations |
| `code/simulation/` | Channel and mobility models |
| `code/utils/` | Configuration and metrics utilities |
| `simulations/results/` | Simulation results (CSV/JSON) |
| `docs/` | Documentation and manuscript |
| `docs/figures/` | 10 illustrative figures |
| `manuscript_sync/` | Synchronization verification files |

---

## Key Features

- **Agent Loop Pattern**: Iterative decision cycle (analyze → select → execute → validate → iterate) from NetOps-Guardian-AI
- **Multi-Agent RL**: QMIX value-decomposition and MAPPO policy optimization
- **RIS Optimization**: Dynamic phase shift configuration with 4-bit quantization
- **Proactive Handover**: Gauss-Markov mobility-based trajectory prediction
- **URLLC Compliance**: <1ms latency, 99.999% reliability
- **6G mmWave**: 28 GHz carrier, 400 MHz bandwidth

---

## Simulation Parameters (Table I - Manuscript)

| Parameter | Value | Config Variable |
|-----------|-------|-----------------|
| Carrier Frequency (f_c) | 28 GHz | `carrier_freq` |
| Bandwidth (W) | 400 MHz | `bandwidth` |
| Number of gNBs (\|B\|) | 5 | `num_gnbs` |
| Number of RIS Panels (\|R\|) | 3 | `num_ris` |
| RIS Elements (N) | 64 (8×8 grid) | `num_ris_elements` |
| Phase Quantization | 4-bit (16 levels) | `phase_quantization_bits` |
| Vehicle Speed Range | 80-500 km/h | `min_speed_kmh`, `max_speed_kmh` |
| Vehicle Arrival Rate | 0.5 vehicles/s/lane | `arrival_rate` |
| Discount Factor (γ) | 0.99 | `discount_factor` |
| Learning Rate | 5×10⁻⁴ | `learning_rate` |
| Batch Size | 32 | `batch_size` |
| Training Episodes | 10,000 | `num_episodes` |

---

## Performance Results (Table II - Manuscript)

| Method | HSR (%) | SINR (dB) | Latency (ms) | Throughput |
|--------|---------|-----------|--------------|------------|
| **Agent Loop + MARL** | **98.5** | **+8.2** | **0.85** | **+15.3%** |
| MARL Only | 95.2 | +7.8 | 0.92 | Baseline |
| Conventional HO | 87.3 | N/A | 1.45 | -23.7% |
| Static RIS | 91.8 | +5.1 | 1.12 | -12.4% |
| Single-Agent RL | 89.6 | +4.3 | 1.28 | -18.5% |

---

## Figures

| Figure | Title | Section Reference |
|--------|-------|-------------------|
| Fig. 1 | Network Topology | III-A |
| Fig. 2 | RIS Architecture | III-C |
| Fig. 3 | Agent Loop Pattern | IV-A |
| Fig. 4 | QMIX Architecture | V-A |
| Fig. 5 | MAPPO Architecture | V-B |
| Fig. 6 | SINR vs Vehicle Speed | VI-B |
| Fig. 7 | Handover Success Rate vs Speed | VI-C |
| Fig. 8 | Latency CDF | VI-D |
| Fig. 9 | Throughput Comparison | VI-E |
| Fig. 10 | Training Convergence | VI-F |

---

## Installation

```bash
# Clone repository
git clone https://github.com/Chihi-Sahati/v2x-6g-ris-mobility.git
cd v2x-6g-ris-mobility

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Quick Start

```python
from code.agents import RISOptimizationAgent, HandoverManagementAgent
from code.simulation import V2XEnvironment

# Initialize environment
env = V2XEnvironment(config="configs/main_experiments.yaml")

# Initialize agents
ris_agent = RISOptimizationAgent(agent_id=0, num_elements=64)
ho_agent = HandoverManagementAgent(agent_id=1, velocity_range=(80, 500))

# Run simulation
results = env.run(episodes=1000, agents=[ris_agent, ho_agent])
print(f"Handover Success Rate: {results['hsr']:.2%}")
```

---

## Mathematical Formulation

The joint optimization is formulated as a CMDP: **M** = ⟨**S**, **A**, **P**, **R**, **γ**, **C**⟩

**Objective (Eq. 12):**
```
max_π E[∑_{t=0}^{∞} γ^t · ∑_{v∈V} w_v · R_v(t) | π]
```

**Constraints:**
- URLLC Latency (Eq. 13): P(T_{E2E,v}(t) > τ_max) ≤ ε, ε = 10⁻⁵
- Handover Success (Eq. 14): HSR(t) ≥ 95%
- Power: ∑_k p_{v,k}(t) ≤ P_v^{max}
- RIS Phase (Eq. 8): θ_{r,n} ∈ {0, 2π/16, ..., 30π/16}

See manuscript for complete mathematical formulation with 28 equations.

---

## Manuscript Compatibility Verification

| Component | Manuscript | Repository | Sync Status |
|-----------|-----------|------------|-------------|
| Abstract | Section "Abstract" | README.md | ✅ Identical |
| Equations | Sections III, V | code/**/*.py | ✅ Referenced |
| Parameters | Table I | code/utils/config.py | ✅ Match |
| Results | Table II | simulations/results/*.csv | ✅ Match |
| Authors | Title Page | README.md, CITATION.cff | ✅ Match |
| Version | v2.0 | GitHub Release v2.0 | ✅ Match |
| Figures | Throughout | docs/figures/*.png | ✅ Match |

**Verification Date:** 2026-03-24  
**All Checks Passed:** ✅ 10/10

---

## Related Work

This repository integrates concepts from:
- **NetOps-Guardian-AI**: Agent Loop Pattern architecture [9]
- **3GPP TR 38.901**: Channel model specifications [11]
- **QMIX**: Value-decomposition MARL [5]
- **PPO/MAPPO**: Policy gradient methods [6]

---

## Citation

```bibtex
@article{alsahati2026aiagent,
  title={AI Agent-Based Mobility Management with Reconfigurable Intelligent Surfaces for 6G V2X Networks},
  author={Al-Sahati, AlHussein A. and Chihi, Houda},
  journal={IEEE Transactions on Vehicular Technology},
  year={2026},
  note={Submitted}
}
```

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v2.0 | March 2026 | Complete manuscript: 22 pages, 28 equations, 10 figures |
| v1.5 | March 2026 | Agent Loop Pattern integration |
| v1.0 | January 2026 | Initial implementation |

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

---

## Acknowledgments

This work was conducted at the InnovCOM Laboratory, Higher School of Communication of Tunis (Sup'Com), University of Carthage, Tunisia, under the supervision of Dr. Houda Chihi.

---

**Last Updated:** March 2026  
**Manuscript Version:** v2.0  
**Repository Sync Status:** ✅ Verified
