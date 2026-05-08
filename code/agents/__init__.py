"""
AI Agents for V2X 6G RIS Mobility Management
============================================

This module implements the multi-agent architecture for V2X mobility management
with RIS optimization, based on the Agent Loop Pattern from NetOps-Guardian-AI.

Manuscript Reference: Section IV - AI Agent Framework Architecture
Repository Version: v2.0

Authors: AlHussein A. Al-Sahati, Houda Chihi
"""

from .agent_loop import (
    BaseV2XAgent,
    RISOptimizationAgent,
    HandoverManagementAgent,
    ResourceAllocationAgent,
    AIAnalysisEngine,
    AgentCoordinator,
    AgentState,
    AgentAction,
    AgentMessage,
)

__all__ = [
    "BaseV2XAgent",
    "RISOptimizationAgent",
    "HandoverManagementAgent",
    "ResourceAllocationAgent",
    "AIAnalysisEngine",
    "AgentCoordinator",
    "AgentState",
    "AgentAction",
    "AgentMessage",
]

__version__ = "2.0.0"
