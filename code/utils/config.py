"""
Configuration Parameters for V2X RIS Mobility Management Simulation
==================================================================
This file contains all simulation parameters that MUST match Table I in the manuscript.

⚠️ IMPORTANT: Any changes to this file must be reflected in the manuscript Table I
and vice versa. Run sync_checklist.md verification before submission.

Manuscript Version: v2.1
Last Synced: 2026-03-24
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


def _default_device() -> str:
    """Resolve default RL device (cuda if available, else cpu)."""
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


@dataclass
class NetworkConfig:
    """
    Network configuration parameters.
    Matches Manuscript Table I: Network Parameters
    """
    # Carrier frequency (f_c in manuscript Eq. 2, 5)
    carrier_freq: float = 28e9  # 28 GHz
    carrier_freq_ghz: float = 28.0  # For display purposes

    # System bandwidth (W in manuscript Eq. 10)
    bandwidth: float = 400e6  # 400 MHz
    bandwidth_mhz: float = 400.0

    # Number of gNodeBs (|B| in manuscript)
    num_gnbs: int = 5

    # gNB positions along highway (km)
    gnb_positions: List[float] = None

    # Inter-site distance
    inter_site_distance: float = 500.0  # meters

    # Shared transmit power per gNB — single source of truth
    tx_power_dbm: float = 43.0
    tx_power_watt: float = 20.0

    # Antenna configuration
    num_antennas_per_gnb: int = 64
    antenna_gain_db: float = 8.0

    # Interference model: "all_gnb" | "nearest" | "none"
    interference_model: str = "all_gnb"

    # Resource allocation
    num_resource_blocks: int = 100

    def __post_init__(self):
        if self.gnb_positions is None:
            self.gnb_positions = [0.0, 0.5, 1.0, 1.5, 2.0]  # km positions


@dataclass
class RISConfig:
    """
    RIS configuration parameters.
    Matches Manuscript Table I: RIS Parameters
    """
    # Number of RIS panels (|R| in manuscript)
    num_ris: int = 3

    # Number of reflecting elements per RIS (N in manuscript Eq. 8)
    num_ris_elements: int = 64

    # RIS element grid dimensions
    ris_grid_rows: int = 8
    ris_grid_cols: int = 8

    # Phase shift quantization bits (k in manuscript Eq. 16)
    phase_quantization_bits: int = 4
    num_phase_levels: int = 16  # 2^4

    # RIS positions (between gNBs)
    ris_positions: List[float] = None

    # RIS element spacing
    element_spacing: float = 0.5  # wavelength

    # Operating frequency for element spacing calculation
    operating_freq: float = 28e9

    def __post_init__(self):
        if self.ris_positions is None:
            self.ris_positions = [0.25, 0.75, 1.25]  # km positions


@dataclass
class MobilityConfig:
    """
    Vehicle mobility configuration.
    Matches Manuscript Section III-E (Eq. 11)
    """
    # Vehicle speed range (km/h)
    min_speed_kmh: float = 80.0
    max_speed_kmh: float = 500.0

    # Vehicle arrival rate (vehicles/s/lane)
    arrival_rate: float = 0.5

    # Number of highway lanes
    num_lanes: int = 4

    # Highway segment length
    highway_length_km: float = 2.5

    # Gauss-Markov parameters (Eq. 11)
    memory_parameter: float = 0.8  # α in Eq. 11 — configurable
    velocity_std: float = 10.0  # km/h

    # Vehicle state dimensions
    position_dim: int = 3  # x, y, z
    velocity_dim: int = 3
    state_dim: int = 6  # position + velocity


@dataclass
class ChannelConfig:
    """
    Channel model parameters.
    Matches Manuscript Section III-B (Eqs. 1-5)
    """
    # Path loss model: 3GPP TR 38.901 UMa
    # LOS path loss (Eq. 2)
    pl_los_a: float = 28.0
    pl_los_b: float = 22.0
    pl_los_c: float = 20.0

    # NLOS path loss (Eq. 3)
    pl_nlos_a: float = 13.54
    pl_nlos_b: float = 39.08
    pl_nlos_c: float = 20.0
    pl_nlos_d: float = -0.6

    # UE height for NLOS correction
    ue_height: float = 1.5  # meters

    # LOS probability model (Eq. 4)
    los_prob_param1: float = 18.0
    los_prob_param2: float = 63.0
    los_prob_param3: float = 5.0 / 4.0

    # Shadow fading
    shadow_fading_std_los: float = 4.0  # dB
    shadow_fading_std_nlos: float = 6.0  # dB

    # Thermal noise (Eq. 9)
    boltzmann_constant: float = 1.38e-23
    temperature: float = 290.0  # Kelvin
    noise_figure_db: float = 7.0

    # Small-scale fading
    num_clusters: int = 4
    rays_per_cluster: int = 20


@dataclass
class URLCCConfig:
    """
    URLLC constraints.
    Matches Manuscript Section III-F (Eqs. 13-14)
    """
    # Maximum latency (τ_max in Eq. 13)
    max_latency_ms: float = 1.0

    # Reliability parameter (ε in Eq. 13)
    reliability_target: float = 1e-5  # 99.999% reliability

    # Minimum handover success rate (Eq. 14)
    min_hsr: float = 0.95  # 95%

    # Target HSR for evaluation
    target_hsr: float = 0.985  # 98.5%


@dataclass
class RLConfig:
    """
    Reinforcement learning parameters.
    Matches Manuscript Section VI-A
    """
    # Discount factor (γ in Eq. 12, 21)
    discount_factor: float = 0.99

    # Learning rate
    learning_rate: float = 5e-4

    # Batch size
    batch_size: int = 32

    # Training episodes
    num_episodes: int = 10000

    # Evaluation frequency
    eval_frequency: int = 100

    # QMIX specific
    mixing_embed_dim: int = 32
    hypernet_embed_dim: int = 64
    target_update_freq: int = 200

    # MAPPO specific
    ppo_clip: float = 0.2
    gae_lambda: float = 0.95
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5

    # Exploration
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay: int = 50000

    # Device
    device: str = field(default_factory=_default_device)


@dataclass
class AgentLoopConfig:
    """
    Agent Loop configuration from NetOps-Guardian-AI.
    Matches Manuscript Section IV
    """
    # Maximum retry attempts (validate phase)
    max_retries: int = 3

    # Task queue size
    task_queue_size: int = 100

    # Agent status values
    status_idle: str = "idle"
    status_waiting: str = "waiting"
    status_running: str = "running"
    status_error: str = "error"
    status_completed: str = "completed"

    # Inter-agent communication
    message_buffer_size: int = 1000
    broadcast_enabled: bool = True


@dataclass
class SimulationConfig:
    """
    Complete simulation configuration combining all parameters.

    .. note::
        ``episode_length`` was increased from 1000 to **5000** steps
        to give vehicles enough time to cross the 2.5 km highway at
        realistic speeds (80–500 km/h).
    """
    network: NetworkConfig = None
    ris: RISConfig = None
    mobility: MobilityConfig = None
    channel: ChannelConfig = None
    urllc: URLCCConfig = None
    rl: RLConfig = None
    agent_loop: AgentLoopConfig = None

    # Simulation timing
    episode_length: int = 5000      # steps per episode (was 1000)
    dt: float = 0.01                # seconds per step (10 ms)

    # Shared transmit power — single source of truth used by all modules
    tx_power_dbm: float = 43.0

    # Interference model selector
    interference_model: str = "all_gnb"

    # Resource blocks for OFDMA scheduling
    num_resource_blocks: int = 100

    def __post_init__(self):
        if self.network is None:
            self.network = NetworkConfig()
        if self.ris is None:
            self.ris = RISConfig()
        if self.mobility is None:
            self.mobility = MobilityConfig()
        if self.channel is None:
            self.channel = ChannelConfig()
        if self.urllc is None:
            self.urllc = URLCCConfig()
        if self.rl is None:
            self.rl = RLConfig()
        if self.agent_loop is None:
            self.agent_loop = AgentLoopConfig()

    def get_table_i_dict(self) -> Dict[str, Any]:
        """
        Export parameters in Table I format for manuscript verification.
        """
        return {
            "V": f"|V| ∈ [30, 150]",
            "B": f"|B| = {self.network.num_gnbs}",
            "R": f"|R| = {self.ris.num_ris}",
            "N": f"N = {self.ris.num_ris_elements}",
            "θ_{r,n}": "[0, 2π) rad",
            "γ_v": "[0, ∞) dB",
            "R_v": "Mbps",
            "T_{E2E,v}": f"[0, {self.urllc.max_latency_ms}] ms",
            "ε": f"10^{{-{int(-np.log10(self.urllc.reliability_target))}}}",
            "HSR": "[0, 1]",
            "π": "-",
            "γ": f"[0, {self.rl.discount_factor})",
            "f_c": f"{self.network.carrier_freq_ghz} GHz",
            "W": f"{self.network.bandwidth_mhz} MHz",
            "episode_length": str(self.episode_length),
            "interference_model": self.interference_model,
            "num_resource_blocks": str(self.num_resource_blocks),
            "tx_power_dbm": f"{self.tx_power_dbm} dBm",
        }


# Default configuration instance
DEFAULT_CONFIG = SimulationConfig()


def get_config() -> SimulationConfig:
    """Get default simulation configuration."""
    return DEFAULT_CONFIG


def verify_table_i_match() -> bool:
    """
    Verify that config values match Table I in manuscript.
    Returns True if all values match, False otherwise.
    """
    config = get_config()

    checks = [
        (config.network.carrier_freq_ghz == 28.0, "Carrier frequency mismatch"),
        (config.network.bandwidth_mhz == 400.0, "Bandwidth mismatch"),
        (config.network.num_gnbs == 5, "Number of gNBs mismatch"),
        (config.ris.num_ris == 3, "Number of RIS panels mismatch"),
        (config.ris.num_ris_elements == 64, "RIS elements mismatch"),
        (config.rl.discount_factor == 0.99, "Discount factor mismatch"),
        (config.rl.learning_rate == 5e-4, "Learning rate mismatch"),
        (config.rl.batch_size == 32, "Batch size mismatch"),
        (config.episode_length == 5000, "Episode length should be 5000"),
        (config.tx_power_dbm == 43.0, "Tx power mismatch"),
        (config.interference_model == "all_gnb", "Interference model mismatch"),
        (config.num_resource_blocks == 100, "Resource blocks mismatch"),
    ]

    all_passed = True
    for passed, msg in checks:
        if not passed:
            print(f"❌ {msg}")
            all_passed = False
        else:
            print(f"✅ {msg}")

    if all_passed:
        print("\n✅ All Table I parameters verified!")
    else:
        print("\n❌ Some parameters do not match — see above.")

    return all_passed


if __name__ == "__main__":
    import numpy as np  # Import here to avoid circular import

    print("=" * 60)
    print("Configuration Verification - Manuscript Table I")
    print("=" * 60)
    verify_table_i_match()
