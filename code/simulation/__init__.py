"""
Simulation Environment for V2X 6G RIS Mobility Management
=========================================================

This module provides simulation components:
- Channel models (3GPP TR 38.901)
- Mobility models (Gauss-Markov)
- V2X environment (OpenAI Gym compatible)

Manuscript Reference: Section III (System Model)
Repository Version: v2.0

Authors: AlHussein A. Al-Sahati, Houda Chihi
"""

from .channel import ChannelModel, compute_path_loss, compute_snr
from .mobility import MobilityModel, GaussMarkovMobility
from .v2x_environment import V2XEnvironment, V2XObservation

__all__ = [
    "ChannelModel",
    "compute_path_loss",
    "compute_snr",
    "MobilityModel",
    "GaussMarkovMobility",
    "V2XEnvironment",
    "V2XObservation",
]

__version__ = "2.0.0"
