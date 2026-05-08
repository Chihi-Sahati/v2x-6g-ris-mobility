"""
Reinforcement Learning Algorithms for V2X 6G RIS Mobility Management
=====================================================================

This module implements MARL algorithms:
- QMIX: Value-decomposition for cooperative multi-agent RL
- MAPPO: Multi-Agent Proximal Policy Optimization

Manuscript Reference: Section V (Multi-Agent Reinforcement Learning)
Repository Version: v2.0

Authors: AlHussein A. Al-Sahati, Houda Chihi
"""

from .qmix import QMIXNetwork, QMIXTrainer
from .mappo import MAPPOPolicy, MAPPOTrainer

__all__ = [
    "QMIXNetwork",
    "QMIXTrainer",
    "MAPPOPolicy",
    "MAPPOTrainer",
]

__version__ = "2.0.0"
