"""
V2X Environment for 6G RIS Mobility Management
===============================================

OpenAI Gym compatible environment for V2X simulation.

Manuscript Reference: Section III-F (CMDP Formulation)
Equation 15: State space
Equation 16: Action space
Equation 12-14: Reward and constraints

Authors: AlHussein A. Al-Sahati, Houda Chihi
Version: 2.1
Last Updated: 2026-03-24
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
import gymnasium as gym
from gymnasium import spaces

from .channel import ChannelModel, ChannelConfig
from .mobility import GaussMarkovMobility, MobilityConfig, Vehicle


@dataclass
class V2XConfig:
    """Complete V2X simulation configuration."""
    # Network
    num_gnbs: int = 5
    num_ris: int = 3
    num_ris_elements: int = 64
    phase_quantization_bits: int = 4

    # Shared transmit power (dBm) — used consistently everywhere
    tx_power_dbm: float = 43.0

    # Interference model: "all_gnb" | "nearest" | "none"
    interference_model: str = "all_gnb"

    # Resource allocation
    num_resource_blocks: int = 100

    # URLLC constraints (Equations 13-14)
    max_latency_ms: float = 1.0
    reliability_target: float = 1e-5
    min_hsr: float = 0.95

    # RL
    discount_factor: float = 0.99

    # Simulation — increased to 5000 to allow vehicles to cross the highway
    episode_length: int = 5000
    dt: float = 0.01  # 10 ms per step


class V2XObservation:
    """Observation structure matching manuscript Equation 15."""

    def __init__(
        self,
        vehicle_states: np.ndarray,
        gnb_states: np.ndarray,
        ris_states: np.ndarray,
        channel_states: np.ndarray
    ):
        self.vehicle_states = vehicle_states
        self.gnb_states = gnb_states
        self.ris_states = ris_states
        self.channel_states = channel_states


class V2XEnvironment(gym.Env):
    """
    V2X Environment for RIS-assisted mobility management.

    Manuscript Reference: Section III-F (CMDP Formulation)

    State Space (Equation 15):
        s(t) = [s_V(t), s_B(t), s_R(t), s_C(t)]
        where:
            s_V(t): Vehicle states (position, velocity, channel quality)
            s_B(t): gNB states (load, available resources)
            s_R(t): RIS states (phase configurations)
            s_C(t): Channel states (CSI, interference)

    Action Space (Equation 16):
        a(t) = [a_RIS(t), a_HO(t), a_RA(t)]
        where:
            a_RIS: RIS phase shifts θ_{r,n} ∈ {0, 2π/16, ..., 30π/16}
            a_HO: Handover decisions
            a_RA: Resource allocation

    Reward (Equation 12):
        R(t) = Σ_v w_v · R_v(t)

    Constraints (Equations 13-14):
        P(T_{E2E,v}(t) > τ_max) ≤ ε
        HSR(t) ≥ 95%
    """

    metadata = {'render_modes': ['human']}

    def __init__(
        self,
        config: Optional[V2XConfig] = None,
        render_mode: Optional[str] = None
    ):
        super().__init__()

        self.config = config or V2XConfig()
        self.render_mode = render_mode

        # Initialize components
        channel_cfg = ChannelConfig(tx_power_dbm=self.config.tx_power_dbm)
        self.channel = ChannelModel(config=channel_cfg)
        self.mobility = GaussMarkovMobility()

        # Network topology
        self.gnb_positions = self._init_gnb_positions()
        self.ris_positions = self._init_ris_positions()

        # RIS state — one phase vector per panel
        self.ris_phases = np.zeros(
            (self.config.num_ris, self.config.num_ris_elements)
        )

        # Resource-allocation bookkeeping
        self.vehicle_rb_allocation: Dict[int, int] = {}
        self.vehicle_power_fraction: Dict[int, float] = {}

        # Pre-compute noise power in mW for fast SINR calculation
        self.noise_power_mw = 10.0 ** (self.channel.noise_power_dbm / 10.0)

        # Pre-compute tx power in mW
        self.tx_power_mw = 10.0 ** (self.config.tx_power_dbm / 10.0)

        # Action spaces
        # RIS: Each element of EVERY panel has 2^k phase levels
        total_ris_elements = self.config.num_ris * self.config.num_ris_elements
        self.ris_action_space = spaces.MultiDiscrete(
            [2 ** self.config.phase_quantization_bits] * total_ris_elements
        )

        # Handover: For each vehicle, select target gNB (0..num_gnbs-1)
        # or no handover (num_gnbs)
        self.ho_action_space = spaces.Discrete(self.config.num_gnbs + 1)

        # Combined observation space
        max_vehicles = 150  # Maximum vehicles in simulation
        self.observation_space = spaces.Dict({
            'vehicle_states': spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=(max_vehicles, 6),  # pos + vel
                dtype=np.float32
            ),
            'gnb_states': spaces.Box(
                low=0,
                high=1,
                shape=(self.config.num_gnbs, 4),  # load, position
                dtype=np.float32
            ),
            'ris_states': spaces.Box(
                low=0,
                high=2 * np.pi,
                shape=(self.config.num_ris, self.config.num_ris_elements),
                dtype=np.float32
            ),
            'num_vehicles': spaces.Discrete(max_vehicles + 1)
        })

        # Episode tracking
        self.current_step = 0
        self.total_reward = 0.0
        self.handover_successes = 0
        self.handover_attempts = 0

        # Reset state
        self.reset()

    # ------------------------------------------------------------------
    # Network topology helpers
    # ------------------------------------------------------------------

    def _init_gnb_positions(self) -> np.ndarray:
        """Initialize gNB positions along highway."""
        inter_site_distance = 500.0  # meters
        positions = np.zeros((self.config.num_gnbs, 3))

        for i in range(self.config.num_gnbs):
            positions[i] = [i * inter_site_distance, 0, 25.0]  # x, y, height

        return positions

    def _init_ris_positions(self) -> np.ndarray:
        """Initialize RIS positions between gNBs."""
        inter_site_distance = 500.0
        positions = np.zeros((self.config.num_ris, 3))

        for i in range(self.config.num_ris):
            positions[i] = [(i + 0.5) * inter_site_distance, 0, 10.0]

        return positions

    # ------------------------------------------------------------------
    # Gym API
    # ------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict] = None
    ) -> Tuple[Dict, Dict]:
        """Reset environment to initial state."""
        super().reset(seed=seed)

        # Clear vehicles
        self.mobility.vehicles.clear()

        # Reset RIS phases
        self.ris_phases = np.zeros(
            (self.config.num_ris, self.config.num_ris_elements)
        )

        # Reset resource-allocation state
        self.vehicle_rb_allocation.clear()
        self.vehicle_power_fraction.clear()

        # Reset counters
        self.current_step = 0
        self.total_reward = 0.0
        self.handover_successes = 0
        self.handover_attempts = 0

        # Add initial vehicles
        for _ in range(30):
            self.mobility.add_vehicle()

        observation = self._get_observation()
        info = self._get_info()

        return observation, info

    def step(
        self,
        action: Dict[str, np.ndarray]
    ) -> Tuple[Dict, float, bool, bool, Dict]:
        """
        Execute one environment step.

        Manuscript Reference: Section III-F

        Args:
            action: Dictionary with optional keys
                    'ris'        – RIS phase-shift actions
                    'handover'   – per-vehicle handover decisions
                    'resource'   – dict with 'rb_allocation', 'power_allocation'

        Returns:
            Tuple of (observation, reward, terminated, truncated, info)
        """
        self.current_step += 1

        # Execute RIS action (all panels)
        if 'ris' in action:
            self._apply_ris_action(action['ris'])

        # Update mobility (Equation 11)
        departed = self.mobility.update(self.config.dt)

        # Generate new arrivals
        self.mobility.generate_arrivals(self.config.dt)

        # Execute handover actions
        if 'handover' in action:
            self._apply_handover_actions(action['handover'])

        # Execute resource-allocation actions
        if 'resource' in action:
            self._apply_resource_actions(action['resource'])

        # Compute channel and SINR (with interference)
        self._update_channel_states()

        # Compute reward (Equation 12)
        reward = self._compute_reward()
        self.total_reward += reward

        # Check constraints (Equations 13-14)
        constraint_violated = self._check_constraints()

        # Check termination
        terminated = constraint_violated
        truncated = self.current_step >= self.config.episode_length

        observation = self._get_observation()
        info = self._get_info()

        return observation, reward, terminated, truncated, info

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _apply_ris_action(self, action: np.ndarray):
        """
        Apply RIS phase shift action for ALL panels.

        Manuscript Reference: Equation 16

        θ_{r,n} ∈ {0, 2π/16, ..., 30π/16}

        The action is a flat array of length
            num_ris × num_ris_elements.
        The first num_ris_elements entries belong to panel 0, the next
        num_ris_elements to panel 1, etc.
        """
        phase_step = 2.0 * np.pi / (2 ** self.config.phase_quantization_bits)
        n_elements = self.config.num_ris_elements

        for ris_id in range(self.config.num_ris):
            start = ris_id * n_elements
            end = start + n_elements
            self.ris_phases[ris_id] = action[start:end] * phase_step

    def _apply_handover_actions(self, actions):
        """
        Apply handover decisions — one per vehicle.

        Args:
            actions: Array-like of length >= num_vehicles.
                     actions[i] is the target gNB for vehicle i.
                     Values 0..num_gnbs-1 trigger handover; num_gnbs
                     means "no handover".
        """
        actions = np.atleast_1d(np.asarray(actions, dtype=int))

        for i, vehicle in enumerate(self.mobility.vehicles):
            if i >= len(actions):
                break

            target_gnb = int(actions[i])

            if (target_gnb < self.config.num_gnbs
                    and target_gnb != vehicle.serving_gnb):
                # Attempt handover
                self.handover_attempts += 1

                # SINR-based packet delivery probability
                if vehicle.sinr > 0:
                    success_probability = 1.0 - np.exp(-vehicle.sinr / 10.0)
                else:
                    success_probability = 0.0
                success = np.random.random() < success_probability

                if success:
                    vehicle.serving_gnb = target_gnb
                    self.handover_successes += 1

                self.mobility.record_handover(success)

    def _apply_resource_actions(self, resource_action: Dict):
        """
        Apply resource-allocation actions from the RL agent.

        Args:
            resource_action: Dict with optional keys
                - 'rb_allocation':     array of per-vehicle RB counts
                - 'power_allocation':  array of per-vehicle power fractions
        """
        rb_alloc = resource_action.get('rb_allocation')
        if rb_alloc is not None:
            rb_alloc = np.atleast_1d(np.asarray(rb_alloc, dtype=int))
            for i, vehicle in enumerate(self.mobility.vehicles):
                if i < len(rb_alloc):
                    self.vehicle_rb_allocation[vehicle.id] = int(rb_alloc[i])

        pwr_alloc = resource_action.get('power_allocation')
        if pwr_alloc is not None:
            pwr_alloc = np.atleast_1d(np.asarray(pwr_alloc, dtype=float))
            for i, vehicle in enumerate(self.mobility.vehicles):
                if i < len(pwr_alloc):
                    self.vehicle_power_fraction[vehicle.id] = float(
                        np.clip(pwr_alloc[i], 0.0, 1.0)
                    )

    # ------------------------------------------------------------------
    # Channel & SINR (core fix)
    # ------------------------------------------------------------------

    def _update_channel_states(self):
        """
        Update channel states for all vehicles.

        For each vehicle the following is computed:
          1. Direct-path SINR from every gNB.
          2. Inter-gNB interference (sum of received power from OTHER gNBs).
          3. Inter-vehicle (intra-cell) interference — vehicles served by
             the same gNB share resources in OFDMA, reducing effective
             bandwidth per user.
          4. RIS-reflected path gain for ALL panels, combined in the
             LINEAR (mW) domain.
          5. The gNB offering the highest SINR is selected as the serving
             gNB.

        RIS gain model (per panel):
            g_vr  = 10^{−PL_LOS(vehicle,RIS)/10}
            g_rg  = 10^{−PL_LOS(RIS,gNB)/10}
            φ     = |mean(exp(j·θ_n))|          (phase alignment ∈ [0,1])
            G_coh = (N·φ)²                       (coherent array gain)
            P_RIS = G_coh · g_vr · g_rg          (reflected power, mW)

        Final: SINR = (P_direct + P_RIS) / (N₀ + P_interference)
        """
        tx_mw = self.tx_power_mw
        noise_mw = self.noise_power_mw

        # Pre-count vehicles per gNB (for intra-cell load model)
        vehicles_per_gnb: Dict[int, int] = {}
        for v in self.mobility.vehicles:
            g = v.serving_gnb if v.serving_gnb >= 0 else 0
            vehicles_per_gnb[g] = vehicles_per_gnb.get(g, 0) + 1

        for vehicle in self.mobility.vehicles:
            best_sinr_db = -np.inf
            best_gnb = -1
            ue_h = float(vehicle.position[2]) if len(vehicle.position) > 2 else 1.5

            for gnb_id in range(self.config.num_gnbs):
                gnb_pos = self.gnb_positions[gnb_id]

                # ----- Direct path -----
                dist_3d = np.linalg.norm(vehicle.position - gnb_pos)
                dist_2d = np.linalg.norm(
                    vehicle.position[:2] - gnb_pos[:2]
                )

                pl_db, _ = self.channel.compute_path_loss(
                    np.array([dist_2d]),
                    np.array([dist_3d]),
                    ue_height=ue_h,
                    gnb_height=float(gnb_pos[2])
                )
                direct_linear = tx_mw * 10.0 ** (-pl_db[0] / 10.0)

                # ----- Inter-gNB interference -----
                interference_mw = 0.0
                if self.config.interference_model != "none":
                    for other_id in range(self.config.num_gnbs):
                        if other_id == gnb_id:
                            continue
                        if (self.config.interference_model == "nearest"
                                and abs(other_id - gnb_id) > 1):
                            continue
                        other_pos = self.gnb_positions[other_id]
                        o_dist_3d = np.linalg.norm(vehicle.position - other_pos)
                        o_dist_2d = np.linalg.norm(
                            vehicle.position[:2] - other_pos[:2]
                        )
                        o_pl, _ = self.channel.compute_path_loss(
                            np.array([o_dist_2d]),
                            np.array([o_dist_3d]),
                            ue_height=ue_h,
                            gnb_height=float(other_pos[2])
                        )
                        interference_mw += (
                            tx_mw * 10.0 ** (-o_pl[0] / 10.0)
                        )

                # ----- Intra-cell (inter-vehicle) load factor -----
                # OFDMA: resources shared equally among N users on same gNB
                n_users = vehicles_per_gnb.get(gnb_id, 1)
                if n_users > 1:
                    load_factor = 1.0 / n_users
                    direct_linear *= load_factor

                # ----- RIS reflected gain — ALL panels (LINEAR domain) -----
                ris_power_linear = 0.0
                N_elements = self.config.num_ris_elements

                for ris_id in range(self.config.num_ris):
                    ris_pos = self.ris_positions[ris_id]

                    # Vehicle → RIS hop
                    d_vr_3d = np.linalg.norm(vehicle.position - ris_pos)
                    d_vr_2d = np.linalg.norm(
                        vehicle.position[:2] - ris_pos[:2]
                    )
                    pl_vr = self.channel.compute_path_loss_los(
                        np.array([d_vr_2d]),
                        np.array([d_vr_3d]),
                        ue_height=ue_h,
                        gnb_height=float(ris_pos[2])
                    )[0]

                    # RIS → gNB hop
                    d_rg_3d = np.linalg.norm(ris_pos - gnb_pos)
                    d_rg_2d = np.linalg.norm(ris_pos[:2] - gnb_pos[:2])
                    pl_rg = self.channel.compute_path_loss_los(
                        np.array([d_rg_2d]),
                        np.array([d_rg_3d]),
                        ue_height=float(ris_pos[2]),
                        gnb_height=float(gnb_pos[2])
                    )[0]

                    # Linear channel gains for two hops
                    g_vr = 10.0 ** (-pl_vr / 10.0)
                    g_rg = 10.0 ** (-pl_rg / 10.0)

                    # Phase alignment factor ∈ [0, 1]
                    phases = self.ris_phases[ris_id]
                    phase_alignment = float(
                        np.abs(np.mean(np.exp(1j * phases)))
                    )

                    # Coherent array gain: (N · φ)²
                    coherent_gain = (N_elements * phase_alignment) ** 2

                    ris_power_linear += coherent_gain * g_vr * g_rg

                # ----- Combine in LINEAR domain -----
                combined_signal_mw = direct_linear + ris_power_linear

                # ----- SINR -----
                total_noise_plus_intf = noise_mw + interference_mw
                sinr_linear = combined_signal_mw / total_noise_plus_intf

                sinr_db = (
                    10.0 * np.log10(sinr_linear)
                    if sinr_linear > 0 else -100.0
                )

                if sinr_db > best_sinr_db:
                    best_sinr_db = sinr_db
                    best_gnb = gnb_id

            vehicle.sinr = best_sinr_db
            if vehicle.serving_gnb < 0:
                vehicle.serving_gnb = best_gnb

    # ------------------------------------------------------------------
    # Rate / latency helpers
    # ------------------------------------------------------------------

    def _sinr_to_rate_mbps(self, sinr_db: float) -> float:
        """
        Convert SINR to achievable data rate using Shannon Capacity.

        Manuscript Reference: Equation 10
        R_v(t) = W · log₂(1 + γ_v(t))

        Args:
            sinr_db: SINR value in dB

        Returns:
            Data rate in Mbps
        """
        sinr_linear = 10.0 ** (sinr_db / 10.0)
        bandwidth_hz = self.channel.config.bandwidth  # 400e6 Hz
        rate_bps = bandwidth_hz * np.log2(1.0 + sinr_linear)
        return rate_bps / 1e6  # Convert to Mbps

    def _sinr_to_rate_bps(self, sinr_db: float) -> float:
        """Return rate in bits-per-second (convenient for latency calc)."""
        sinr_linear = 10.0 ** (sinr_db / 10.0)
        bandwidth_hz = self.channel.config.bandwidth
        return bandwidth_hz * np.log2(1.0 + sinr_linear)

    def _compute_estimated_latency_ms(self, vehicle) -> float:
        """
        Estimate E2E latency with realistic URLLC components.

        Manuscript Reference: Equation 13
        P(T_E2E,v > τ_max) ≤ ε,  τ_max = 1 ms

        Model:
            T_E2E = T_processing + T_scheduling + T_tx + T_retransmission

            T_processing     = 0.15 ms   (baseband / PHY processing)
            T_scheduling     = 0.05 ms   (slot alignment)
            T_tx             = L / R_v   (transmission time)
            T_retransmission = T_tx × P_HARQ
                              where P_HARQ ≈ BLER estimated from SINR
                              (K=1 retransmission provisioned for URLLC)

        L = 80 Kbits (10 KB reference V2X safety packet).
        """
        rate_bps = max(self._sinr_to_rate_bps(vehicle.sinr), 1.0)
        packet_size_bits = 80_000.0  # 80 Kbits = 10 KB

        # Individual latency components
        T_processing = 0.15   # ms — baseband processing
        T_scheduling = 0.05   # ms — slot alignment
        T_tx = packet_size_bits / rate_bps * 1000.0  # ms

        # BLER-based HARQ retransmission probability
        if vehicle.sinr > 10.0:
            harq_prob = 1e-5       # well above threshold
        elif vehicle.sinr > 0.0:
            harq_prob = np.exp(-vehicle.sinr / 2.0)
        else:
            harq_prob = 1.0

        T_retransmission = T_tx * harq_prob  # K=1 retransmission

        return T_processing + T_scheduling + T_tx + T_retransmission

    # ------------------------------------------------------------------
    # Reward & constraints
    # ------------------------------------------------------------------

    def _compute_reward(self) -> float:
        """
        Compute reward.

        Manuscript Reference: Equation 12

        R(t) = Σ_v w_v · R_v(t)
        where R_v(t) = W · log₂(1 + γ_v(t))  [Equation 10]
        """
        if not self.mobility.vehicles:
            return 0.0

        # Weighted sum of Shannon capacities (Equations 10 & 12)
        # w_v = 1/|V| for uniform weighting
        num_vehicles = len(self.mobility.vehicles)
        total_throughput = sum(
            self._sinr_to_rate_mbps(vehicle.sinr)
            for vehicle in self.mobility.vehicles
        ) / num_vehicles  # normalise to per-vehicle average (Mbps)

        # Handover success bonus (Equation 14 incentive)
        hsr_bonus = 0.0
        if self.handover_attempts > 0:
            hsr = self.handover_successes / self.handover_attempts
            hsr_bonus = 10.0 * (hsr - 0.95)  # Bonus for HSR > 95%

        # URLLC latency penalty (Equation 13)
        # Vehicles with SINR < 0 dB → rate too low → estimated latency > τ_max
        latency_penalty = 0.0
        for vehicle in self.mobility.vehicles:
            if vehicle.sinr < 0.0:       # Below 0 dB → URLLC violation risk
                latency_penalty -= 2.0
            elif vehicle.sinr < 5.0:     # 0–5 dB → marginal URLLC compliance
                latency_penalty -= 0.5

        return total_throughput * 0.01 + hsr_bonus + latency_penalty

    def _check_constraints(self) -> bool:
        """
        Check URLLC constraints.

        Manuscript Reference: Equations 13-14

        Constraint 1 (Equation 13): P(T_E2E,v > τ_max) ≤ ε
            τ_max = 1 ms, ε = 10⁻⁵ (99.999% reliability)
        Constraint 2 (Equation 14): HSR ≥ HSR_min = 95%

        Returns:
            True if any constraint is violated
        """
        # --- Constraint 1: URLLC Latency (Equation 13) ---
        if self.mobility.vehicles:
            latency_violations = sum(
                1 for v in self.mobility.vehicles
                if self._compute_estimated_latency_ms(v)
                > self.config.max_latency_ms
            )
            violation_rate = latency_violations / len(self.mobility.vehicles)
            # ε = 10⁻⁵ → allow at most 1 violation per 100,000 packets.
            # In simulation: if >0.1% of vehicles violate → triggered
            if violation_rate > 0.001:  # soft threshold for simulation stability
                return True

        # --- Constraint 2: Handover Success Rate (Equation 14) ---
        if self.handover_attempts > 10:
            hsr = self.handover_successes / self.handover_attempts
            if hsr < self.config.min_hsr:
                return True

        return False

    # ------------------------------------------------------------------
    # Observation / info
    # ------------------------------------------------------------------

    def _get_observation(self) -> Dict:
        """Get current observation."""
        max_vehicles = 150
        num_vehicles = len(self.mobility.vehicles)

        # Vehicle states
        vehicle_states = np.zeros((max_vehicles, 6), dtype=np.float32)
        if num_vehicles > 0:
            states = self.mobility.get_vehicle_states()
            vehicle_states[:min(num_vehicles, max_vehicles),
                           :states.shape[1]] = states[:max_vehicles]

        # gNB states
        gnb_states = np.zeros(
            (self.config.num_gnbs, 4), dtype=np.float32
        )
        for i, pos in enumerate(self.gnb_positions):
            gnb_states[i, :3] = pos
            gnb_states[i, 3] = np.random.random() * 0.5  # Simulated load

        # RIS states
        ris_states = self.ris_phases.astype(np.float32)

        return {
            'vehicle_states': vehicle_states,
            'gnb_states': gnb_states,
            'ris_states': ris_states,
            'num_vehicles': num_vehicles
        }

    def _get_info(self) -> Dict:
        """Get environment info."""
        hsr = 0.0
        if self.handover_attempts > 0:
            hsr = self.handover_successes / self.handover_attempts

        return {
            'step': self.current_step,
            'num_vehicles': len(self.mobility.vehicles),
            'handover_success_rate': hsr,
            'total_reward': self.total_reward
        }

    def render(self):
        """Render environment state."""
        if self.render_mode == 'human':
            print(
                f"Step {self.current_step}: "
                f"{len(self.mobility.vehicles)} vehicles, "
                f"HSR={self._get_info()['handover_success_rate']:.2%}"
            )


# Main execution example
if __name__ == "__main__":
    # Create environment
    env = V2XEnvironment()

    print("V2X Environment")
    print(f"gNBs: {env.config.num_gnbs}")
    print(f"RIS panels: {env.config.num_ris}")
    print(f"RIS elements per panel: {env.config.num_ris_elements}")
    print(f"Episode length: {env.config.episode_length}")
    print(f"Interference model: {env.config.interference_model}")
    print(f"Tx power: {env.config.tx_power_dbm} dBm")

    # Run episode
    obs, info = env.reset()

    total_reward = 0
    for step_i in range(100):
        # Random actions
        total_elements = env.config.num_ris * env.config.num_ris_elements
        action = {
            'ris': env.ris_action_space.sample(),
            'handover': np.random.randint(
                0, env.config.num_gnbs + 1,
                len(env.mobility.vehicles)
            ),
            'resource': {
                'rb_allocation': np.ones(
                    len(env.mobility.vehicles), dtype=int
                ),
                'power_allocation': np.ones(len(env.mobility.vehicles)),
            },
        }

        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward

        if terminated or truncated:
            break

    print(f"\nEpisode finished after {info['step']} steps")
    print(f"Total reward: {total_reward:.2f}")
    print(f"Handover success rate: {info['handover_success_rate']:.2%}")
