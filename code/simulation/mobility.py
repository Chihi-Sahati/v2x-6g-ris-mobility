"""
Mobility Models for V2X 6G RIS Mobility Management
===================================================

Implementation of vehicle mobility models for V2X simulation.

Manuscript References:
- Section III-E: Mobility Model (Equation 11)
- Gauss-Markov mobility model

Authors: AlHussein A. Al-Sahati, Houda Chihi
Version: 2.1
Last Updated: 2026-03-24
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass
import random


@dataclass
class MobilityConfig:
    """
    Mobility model configuration.
    Matches Manuscript Table I.
    """
    min_speed_kmh: float = 80.0
    max_speed_kmh: float = 500.0
    mean_speed_kmh: float = 120.0

    # Gauss-Markov parameters (Equation 11)
    memory_parameter: float = 0.8  # α — configurable via constructor
    velocity_std: float = 10.0  # km/h

    # Highway parameters
    highway_length_km: float = 2.5
    num_lanes: int = 4
    lane_width: float = 3.5  # meters

    # Arrival rate
    arrival_rate: float = 0.5  # vehicles/s/lane


class Vehicle:
    """Vehicle state representation."""

    def __init__(
        self,
        vehicle_id: int,
        position: np.ndarray,
        velocity: np.ndarray,
        lane: int = 0
    ):
        self.id = vehicle_id
        self.position = position  # [x, y, z] in meters
        self.velocity = velocity  # [vx, vy, vz] in m/s
        self.lane = lane
        self.serving_gnb = -1
        self.sinr = 0.0
        self.throughput = 0.0

    @property
    def speed_kmh(self) -> float:
        return np.linalg.norm(self.velocity) * 3.6

    @property
    def state(self) -> np.ndarray:
        return np.concatenate([self.position, self.velocity])


class MobilityModel:
    """
    Base class for mobility models.
    """

    def __init__(self, config: Optional[MobilityConfig] = None):
        self.config = config or MobilityConfig()
        self.vehicles: List[Vehicle] = []
        self.vehicle_counter = 0

    def update(self, dt: float):
        """Update all vehicle positions."""
        raise NotImplementedError

    def add_vehicle(self, lane: int = 0) -> Vehicle:
        """Add new vehicle to simulation."""
        raise NotImplementedError

    def remove_vehicle(self, vehicle_id: int):
        """Remove vehicle from simulation."""
        self.vehicles = [v for v in self.vehicles if v.id != vehicle_id]


class GaussMarkovMobility(MobilityModel):
    """
    Gauss-Markov Mobility Model.

    Manuscript Reference: Equation 11

    v(t+Δt) = α·v(t) + (1-α)·μ + σ·√(1-α²)·ξ

    where:
        α: Memory parameter (0 ≤ α ≤ 1)  — **configurable**
        μ: Mean velocity
        σ: Standard deviation
        ξ: Gaussian random variable

    The memory parameter α can be set in three ways (in priority order):
        1. Explicit ``alpha`` keyword argument to ``__init__``.
        2. ``memory_parameter`` field in the ``MobilityConfig`` dataclass.
        3. Default value 0.8.

    This model provides realistic vehicle movement with:
        - Temporal correlation in velocity
        - Bounded speed variations
        - Smooth trajectory changes
    """

    def __init__(
        self,
        config: Optional[MobilityConfig] = None,
        alpha: Optional[float] = None
    ):
        """
        Args:
            config: Mobility configuration dataclass.
            alpha:  Override the Gauss-Markov memory parameter α.
                    If *None* the value from ``config.memory_parameter``
                    is used (default 0.8).
        """
        super().__init__(config)

        # α — highest priority: explicit argument, then config, then default
        if alpha is not None:
            self.alpha = float(np.clip(alpha, 0.0, 1.0))
        else:
            self.alpha = self.config.memory_parameter

        self.mean_speed = self.config.mean_speed_kmh / 3.6  # m/s
        self.velocity_std = (
            self.config.velocity_std_kmh / 3.6
            if hasattr(self.config, 'velocity_std_kmh')
            else self.config.velocity_std / 3.6
        )

        # Highway dimensions
        self.highway_length = self.config.highway_length_km * 1000  # meters
        self.num_lanes = self.config.num_lanes
        self.lane_width = self.config.lane_width

        # Arrival process
        self.arrival_rate = self.config.arrival_rate

        # Statistics
        self.total_handovers = 0
        self.successful_handovers = 0

    def set_alpha(self, alpha: float):
        """
        Update the Gauss-Markov memory parameter at runtime.

        Args:
            alpha: New value for α ∈ [0, 1].
        """
        self.alpha = float(np.clip(alpha, 0.0, 1.0))

    def update(self, dt: float) -> List[int]:
        """
        Update all vehicle positions using Gauss-Markov model.

        Manuscript Reference: Equation 11

        Args:
            dt: Time step in seconds

        Returns:
            List of vehicle IDs that left the simulation
        """
        departed = []

        for vehicle in self.vehicles:
            # Equation 11: Gauss-Markov velocity update
            # v(t+Δt) = α·v(t) + (1-α)·μ + σ·√(1-α²)·ξ

            current_speed = np.linalg.norm(vehicle.velocity)

            # Generate new speed
            xi = np.random.normal(0, 1)
            new_speed = (
                self.alpha * current_speed
                + (1 - self.alpha) * self.mean_speed
                + self.velocity_std * np.sqrt(1 - self.alpha ** 2) * xi
            )

            # Clamp to valid range
            min_speed = self.config.min_speed_kmh / 3.6
            max_speed = self.config.max_speed_kmh / 3.6
            new_speed = np.clip(new_speed, min_speed, max_speed)

            # Update velocity direction (small random deviation)
            if current_speed > 0:
                direction = vehicle.velocity / current_speed
                # Small angle perturbation for realistic movement
                angle_deviation = np.random.normal(0, 0.01)  # radians
                cos_a, sin_a = np.cos(angle_deviation), np.sin(angle_deviation)
                # Rotate in x-y plane
                new_direction = np.array([
                    direction[0] * cos_a - direction[1] * sin_a,
                    direction[0] * sin_a + direction[1] * cos_a,
                    direction[2] if len(direction) > 2 else 0
                ])
                vehicle.velocity = new_direction * new_speed
            else:
                # Initial velocity along highway
                vehicle.velocity = np.array([new_speed, 0, 0])

            # Update position
            vehicle.position += vehicle.velocity * dt

            # Check if departed
            if vehicle.position[0] > self.highway_length:
                departed.append(vehicle.id)

        # Remove departed vehicles
        for vid in departed:
            self.remove_vehicle(vid)

        return departed

    def add_vehicle(self, lane: int = 0) -> Vehicle:
        """
        Add new vehicle at highway entrance.

        Args:
            lane: Lane number (0-indexed)

        Returns:
            New vehicle instance
        """
        # Random lane if not specified
        if lane < 0 or lane >= self.num_lanes:
            lane = random.randint(0, self.num_lanes - 1)

        # Initial position
        y_offset = (lane - self.num_lanes / 2 + 0.5) * self.lane_width
        position = np.array([0.0, y_offset, 1.5])  # x=0, y=lane center, z=vehicle height

        # Initial velocity (random within range)
        initial_speed = random.uniform(
            self.config.min_speed_kmh / 3.6,
            self.config.max_speed_kmh / 3.6
        )
        velocity = np.array([initial_speed, 0, 0])  # Moving along x-axis

        vehicle = Vehicle(
            vehicle_id=self.vehicle_counter,
            position=position,
            velocity=velocity,
            lane=lane
        )

        self.vehicles.append(vehicle)
        self.vehicle_counter += 1

        return vehicle

    def generate_arrivals(self, dt: float):
        """
        Generate vehicle arrivals based on Poisson process.

        Args:
            dt: Time step in seconds
        """
        # Poisson arrivals per lane
        for lane in range(self.num_lanes):
            expected_arrivals = self.arrival_rate * dt
            num_arrivals = np.random.poisson(expected_arrivals)

            for _ in range(num_arrivals):
                self.add_vehicle(lane)

    def get_vehicle_states(self) -> np.ndarray:
        """Get state matrix for all vehicles."""
        if not self.vehicles:
            return np.array([])

        return np.array([v.state for v in self.vehicles])

    def get_vehicle_positions(self) -> np.ndarray:
        """Get position matrix for all vehicles."""
        if not self.vehicles:
            return np.array([])

        return np.array([v.position for v in self.vehicles])

    def get_vehicle_velocities(self) -> np.ndarray:
        """Get velocity matrix for all vehicles."""
        if not self.vehicles:
            return np.array([])

        return np.array([v.velocity for v in self.vehicles])

    def get_vehicle_speeds(self) -> List[float]:
        """Get list of vehicle speeds in km/h."""
        return [v.speed_kmh for v in self.vehicles]

    def record_handover(self, success: bool):
        """Record handover event."""
        self.total_handovers += 1
        if success:
            self.successful_handovers += 1

    def get_handover_success_rate(self) -> float:
        """Compute handover success rate."""
        if self.total_handovers == 0:
            return 0.0
        return self.successful_handovers / self.total_handovers


# Main execution example
if __name__ == "__main__":
    # Initialize mobility model with default α
    mobility = GaussMarkovMobility()

    print("Gauss-Markov Mobility Model")
    print(f"Speed range: {mobility.config.min_speed_kmh}-{mobility.config.max_speed_kmh} km/h")
    print(f"Memory parameter α = {mobility.alpha}")
    print(f"Highway length: {mobility.highway_length/1000} km")

    # Test configurable α
    mobility_high_alpha = GaussMarkovMobility(alpha=0.95)
    print(f"\nHigh-α instance: α = {mobility_high_alpha.alpha}")

    mobility_low_alpha = GaussMarkovMobility(alpha=0.3)
    print(f"Low-α instance:  α = {mobility_low_alpha.alpha}")

    # Runtime change
    mobility.set_alpha(0.6)
    print(f"After set_alpha(0.6): α = {mobility.alpha}")

    # Add initial vehicles
    for lane in range(mobility.num_lanes):
        mobility.add_vehicle(lane)

    print(f"\nInitial vehicles: {len(mobility.vehicles)}")

    # Simulate for 10 seconds
    dt = 0.1  # 100ms steps

    for t in range(100):
        mobility.update(dt)
        mobility.generate_arrivals(dt)

    print(f"After 10s: {len(mobility.vehicles)} vehicles")
    print(f"Speeds: {mobility.get_vehicle_speeds()}")
