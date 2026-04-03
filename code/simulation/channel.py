"""
Channel Models for V2X 6G RIS Mobility Management
==================================================

Implementation of 3GPP TR 38.901 channel model for 6G mmWave V2X scenarios.

Manuscript References:
- Section III-B: Channel Model (Equations 1-5)
- Equation 1: Combined received signal
- Equation 2: LOS path loss
- Equation 3: NLOS path loss
- Equation 4: LOS probability
- Equation 5: RIS-assisted channel
- Equation 9: SINR computation

Reference: 3GPP TR 38.901 V16.1.0 [12]

Authors: AlHussein A. Al-Sahati, Houda Chihi
Version: 2.1
Last Updated: 2026-03-24
"""

import numpy as np
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass


@dataclass
class ChannelConfig:
    """
    Channel model configuration.
    Matches Manuscript Table I.
    """
    carrier_freq: float = 28e9  # f_c = 28 GHz
    bandwidth: float = 400e6  # W = 400 MHz
    tx_power_dbm: float = 43.0  # gNB transmit power

    # Path loss parameters (3GPP TR 38.901 UMa)
    pl_los_a: float = 28.0
    pl_los_b: float = 22.0
    pl_los_c: float = 20.0

    pl_nlos_a: float = 13.54
    pl_nlos_b: float = 39.08
    pl_nlos_c: float = 20.0
    pl_nlos_d: float = -0.6

    # Shadow fading
    shadow_fading_std_los: float = 4.0
    shadow_fading_std_nlos: float = 6.0

    # Thermal noise
    temperature: float = 290.0  # Kelvin
    noise_figure_db: float = 7.0
    boltzmann_constant: float = 1.38e-23


class ChannelModel:
    """
    3GPP TR 38.901 Channel Model for 6G mmWave V2X.

    Manuscript Reference: Section III-B

    Implements:
        - LOS/NLOS path loss
        - Shadow fading
        - Small-scale fading
        - RIS-assisted channel
        - Inter-cell interference computation
    """

    def __init__(self, config: Optional[ChannelConfig] = None):
        self.config = config or ChannelConfig()
        self.fc = self.config.carrier_freq
        self.fc_ghz = self.fc / 1e9

        # Wavelength
        self.wavelength = 3e8 / self.fc

        # Thermal noise power (Equation 9)
        self.noise_power = (
            self.config.boltzmann_constant *
            self.config.temperature *
            self.config.bandwidth
        )
        self.noise_power_dbm = 10 * np.log10(self.noise_power * 1000)

    # ------------------------------------------------------------------
    # Path-loss models
    # ------------------------------------------------------------------

    def compute_path_loss_los(
        self,
        distance_2d: np.ndarray,
        distance_3d: np.ndarray,
        ue_height: float = 1.5,
        gnb_height: float = 25.0
    ) -> np.ndarray:
        """
        Compute LOS path loss.

        Manuscript Reference: Equation 2

        PL_LOS = 28 + 22·log10(d_3D) + 20·log10(f_c)

        Args:
            distance_2d: 2D distance in meters
            distance_3d: 3D distance in meters
            ue_height: User equipment height
            gnb_height: gNB antenna height

        Returns:
            Path loss in dB
        """
        # Equation 2
        pl = (
            self.config.pl_los_a +
            self.config.pl_los_b * np.log10(np.maximum(distance_3d, 1.0)) +
            self.config.pl_los_c * np.log10(self.fc_ghz)
        )

        return pl

    def compute_path_loss_nlos(
        self,
        distance_2d: np.ndarray,
        distance_3d: np.ndarray,
        ue_height: float = 1.5
    ) -> np.ndarray:
        """
        Compute NLOS path loss.

        Manuscript Reference: Equation 3

        PL_NLOS = 13.54 + 39.08·log10(d_3D) + 20·log10(f_c) - 0.6·(h_UE - 1.5)

        Args:
            distance_2d: 2D distance in meters
            distance_3d: 3D distance in meters
            ue_height: User equipment height

        Returns:
            Path loss in dB
        """
        # Equation 3
        pl = (
            self.config.pl_nlos_a +
            self.config.pl_nlos_b * np.log10(np.maximum(distance_3d, 1.0)) +
            self.config.pl_nlos_c * np.log10(self.fc_ghz) +
            self.config.pl_nlos_d * (ue_height - 1.5)
        )

        return pl

    def compute_los_probability(
        self,
        distance_2d: np.ndarray
    ) -> np.ndarray:
        """
        Compute LOS probability.

        Manuscript Reference: Equation 4

        P(LOS) = min(18/d_2D, 1) · (1 - exp(-d_2D/63)) + exp(-d_2D/63)

        Args:
            distance_2d: 2D distance in meters

        Returns:
            LOS probability
        """
        d = np.maximum(distance_2d, 1.0)

        # Equation 4
        p_los = (
            np.minimum(18.0 / d, 1.0) *
            (1 - np.exp(-d / 63.0)) +
            np.exp(-d / 63.0)
        )

        return p_los

    def compute_path_loss(
        self,
        distance_2d: np.ndarray,
        distance_3d: np.ndarray,
        ue_height: float = 1.5,
        gnb_height: float = 25.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute total path loss considering LOS/NLOS.

        Returns:
            Tuple of (path_loss_db, is_los)
        """
        # Compute LOS probability
        p_los = self.compute_los_probability(distance_2d)

        # Determine LOS/NLOS
        is_los = np.random.random(len(distance_2d)) < p_los

        # Compute path loss
        pl_los = self.compute_path_loss_los(
            distance_2d, distance_3d, ue_height, gnb_height
        )
        pl_nlos = self.compute_path_loss_nlos(
            distance_2d, distance_3d, ue_height
        )

        path_loss = np.where(is_los, pl_los, pl_nlos)

        # Add shadow fading
        shadow_std = np.where(
            is_los,
            self.config.shadow_fading_std_los,
            self.config.shadow_fading_std_nlos
        )
        shadow_fading = np.random.normal(0, shadow_std)
        path_loss += shadow_fading

        return path_loss, is_los

    # ------------------------------------------------------------------
    # Channel gain (fixed 2D / 3D distance handling)
    # ------------------------------------------------------------------

    def compute_channel_gain(
        self,
        distance_3d: np.ndarray,
        tx_height: float = 25.0,
        rx_height: float = 1.5,
        include_fading: bool = True
    ) -> np.ndarray:
        """
        Compute channel gain including small-scale fading.

        Manuscript Reference: Equation 1

        h = path_loss · small_scale_fading

        Args:
            distance_3d: 3D distance in meters.
                When only 3D distances are available the 2D distance
                is derived from the height difference:
                    d_2D = sqrt(d_3D² − (h_tx − h_rx)²)
            tx_height: Transmitter height in metres (default gNB).
            rx_height: Receiver height in metres (default UE).
            include_fading: Whether to include small-scale fading.

        Returns:
            Channel gain (linear scale)
        """
        distance_3d = np.asarray(distance_3d, dtype=float)
        height_diff = abs(tx_height - rx_height)

        # Derive 2D distance from 3D distance and antenna heights
        distance_2d = np.sqrt(
            np.maximum(distance_3d ** 2 - height_diff ** 2, 1.0)
        )

        pl_db, _ = self.compute_path_loss(distance_2d, distance_3d,
                                           rx_height, tx_height)

        # Convert to linear
        path_loss_linear = 10.0 ** (-pl_db / 10.0)

        # Add small-scale fading (Rayleigh for NLOS, Rician for LOS)
        if include_fading:
            # Rayleigh fading
            h_fading = (np.random.randn(len(pl_db))
                        + 1j * np.random.randn(len(pl_db))) / np.sqrt(2)
            channel_gain = path_loss_linear * np.abs(h_fading) ** 2
        else:
            channel_gain = path_loss_linear

        return channel_gain

    # ------------------------------------------------------------------
    # RIS channel
    # ------------------------------------------------------------------

    def compute_ris_channel(
        self,
        h_vehicle_ris: np.ndarray,
        g_ris_gnb: np.ndarray,
        ris_phases: np.ndarray
    ) -> np.ndarray:
        """
        Compute RIS-assisted channel.

        Manuscript Reference: Equation 5, 6, 7, 8

        h_RIS = Σ_n h_{v,r,n} · g_{r,b,n} · exp(j·θ_{r,n})

        Args:
            h_vehicle_ris: Vehicle-RIS channel gains (N elements)
            g_ris_gnb: RIS-gNB channel gains (N elements)
            ris_phases: RIS phase shifts θ (N elements)

        Returns:
            Combined RIS channel gain
        """
        # Equation 6: Element-wise channel product
        element_gain = h_vehicle_ris * g_ris_gnb

        # Equation 8: Phase alignment
        phase_factors = np.exp(1j * ris_phases)

        # Equation 5: Sum over all elements
        h_ris = np.sum(element_gain * phase_factors)

        return np.abs(h_ris) ** 2

    # ------------------------------------------------------------------
    # SNR / SINR
    # ------------------------------------------------------------------

    def compute_snr(
        self,
        signal_power_dbm: float,
        path_loss_db: float,
        bandwidth: Optional[float] = None
    ) -> float:
        """
        Compute SNR.

        Manuscript Reference: Equation 9 (part of SINR)

        SNR = P_rx / N_0

        Args:
            signal_power_dbm: Transmit power in dBm
            path_loss_db: Path loss in dB
            bandwidth: Bandwidth (uses config if None)

        Returns:
            SNR in dB
        """
        if bandwidth is None:
            bandwidth = self.config.bandwidth

        # Received power
        rx_power_dbm = signal_power_dbm - path_loss_db

        # Noise power
        noise_power_dbm = self.noise_power_dbm

        # SNR
        snr_db = rx_power_dbm - noise_power_dbm

        return snr_db

    def compute_sinr(
        self,
        signal_power_dbm: float,
        path_loss_db: float,
        interference_power_dbm: float
    ) -> float:
        """
        Compute SINR.

        Manuscript Reference: Equation 9

        SINR = P_signal / (N_0 + Σ P_interference)

        Args:
            signal_power_dbm: Signal power in dBm
            path_loss_db: Path loss in dB
            interference_power_dbm: Interference power in dBm

        Returns:
            SINR in dB
        """
        # Received signal power
        rx_signal_dbm = signal_power_dbm - path_loss_db

        # Noise + interference power
        noise_plus_interference_dbm = 10.0 * np.log10(
            10.0 ** (self.noise_power_dbm / 10.0) +
            10.0 ** (interference_power_dbm / 10.0)
        )

        # SINR
        sinr_db = rx_signal_dbm - noise_plus_interference_dbm

        return sinr_db

    # ------------------------------------------------------------------
    # Inter-cell interference model (NEW)
    # ------------------------------------------------------------------

    def compute_interference_power(
        self,
        vehicle_pos: np.ndarray,
        serving_gnb_id: int,
        all_gnb_positions: np.ndarray,
        tx_power_dbm: Optional[float] = None,
        mode: str = "all_gnb"
    ) -> float:
        """
        Compute total inter-cell interference power received at a vehicle.

        Interference comes from all OTHER gNBs transmitting on the same
        frequency.  The received interference from gNB *i* is:

            P_intf,i = tx_power_mW × 10^{−PL(gNB_i, vehicle) / 10}

        Two modes are supported:
            - "all_gnb" : sum over every non-serving gNB
            - "nearest" : sum only over the two adjacent gNBs
            - "none"    : return 0

        Args:
            vehicle_pos: Vehicle position [x, y, z] (metres).
            serving_gnb_id: Index of the serving gNB (excluded).
            all_gnb_positions: (num_gnbs, 3) array of gNB positions.
            tx_power_dbm: gNB transmit power (uses config if None).
            mode: Interference mode ("all_gnb", "nearest", "none").

        Returns:
            Total interference power in **milliwatts**.
        """
        if mode == "none":
            return 0.0

        if tx_power_dbm is None:
            tx_power_dbm = self.config.tx_power_dbm

        tx_power_mw = 10.0 ** (tx_power_dbm / 10.0)
        interference_mw = 0.0
        ue_h = float(vehicle_pos[2]) if len(vehicle_pos) > 2 else 1.5

        for gnb_id, gnb_pos in enumerate(all_gnb_positions):
            if gnb_id == serving_gnb_id:
                continue

            if mode == "nearest" and abs(gnb_id - serving_gnb_id) > 1:
                continue

            dist_3d = np.linalg.norm(vehicle_pos - gnb_pos)
            dist_2d = np.linalg.norm(vehicle_pos[:2] - gnb_pos[:2])

            pl_db, _ = self.compute_path_loss(
                np.array([dist_2d]),
                np.array([dist_3d]),
                ue_height=ue_h,
                gnb_height=float(gnb_pos[2])
            )
            interference_mw += tx_power_mw * 10.0 ** (-pl_db[0] / 10.0)

        return interference_mw


# ======================================================================
# Module-level convenience functions
# ======================================================================

def compute_path_loss(
    distance: np.ndarray,
    carrier_freq_ghz: float = 28.0
) -> np.ndarray:
    """
    Convenience function for path loss computation.

    Manuscript Reference: Equation 2
    """
    pl = (
        28.0 + 22.0 * np.log10(np.maximum(distance, 1.0))
        + 20.0 * np.log10(carrier_freq_ghz)
    )
    return pl


def compute_snr(
    tx_power_dbm: float,
    path_loss_db: float,
    noise_figure_db: float = 7.0,
    bandwidth_mhz: float = 400.0
) -> float:
    """
    Convenience function for SNR computation.

    Manuscript Reference: Equation 9
    """
    # Thermal noise
    noise_dbm = (
        -174 + 10 * np.log10(bandwidth_mhz * 1e6) + noise_figure_db
    )

    # Received power
    rx_dbm = tx_power_dbm - path_loss_db

    # SNR
    snr_db = rx_dbm - noise_dbm

    return snr_db


def compute_sinr(
    tx_power_dbm: float,
    path_loss_db: float,
    interference_power_dbm: float,
    noise_figure_db: float = 7.0,
    bandwidth_mhz: float = 400.0
) -> float:
    """
    Convenience function for SINR computation.

    Manuscript Reference: Equation 9
    """
    # Thermal noise
    noise_dbm = (
        -174 + 10 * np.log10(bandwidth_mhz * 1e6) + noise_figure_db
    )

    # Received power
    rx_dbm = tx_power_dbm - path_loss_db

    # Noise + interference (linear addition)
    ni_dbm = 10.0 * np.log10(
        10.0 ** (noise_dbm / 10.0)
        + 10.0 ** (interference_power_dbm / 10.0)
    )

    return rx_dbm - ni_dbm


# Main execution example
if __name__ == "__main__":
    # Initialize channel model
    channel = ChannelModel()

    print("3GPP TR 38.901 Channel Model")
    print(f"Carrier Frequency: {channel.fc_ghz} GHz")
    print(f"Bandwidth: {channel.config.bandwidth / 1e6} MHz")
    print(f"Noise Power: {channel.noise_power_dbm:.2f} dBm")

    # Test path loss
    distances = np.array([100, 200, 500, 1000])  # meters
    pl, is_los = channel.compute_path_loss(distances, distances)

    print("\nPath Loss Test:")
    for d, p, los in zip(distances, pl, is_los):
        print(f"  d={d}m: PL={p:.2f} dB, LOS={los}")

    # Test interference model
    gnb_positions = np.array([
        [0, 0, 25], [500, 0, 25], [1000, 0, 25],
        [1500, 0, 25], [2000, 0, 25]
    ])
    vehicle_pos = np.array([300, 5, 1.5])

    intf = channel.compute_interference_power(
        vehicle_pos, serving_gnb_id=0,
        all_gnb_positions=gnb_positions,
        mode="all_gnb"
    )
    print(f"\nInter-cell interference at vehicle: {intf:.6f} mW")
    print(f"Inter-cell interference at vehicle: {10*np.log10(intf+1e-30):.2f} dBm")
