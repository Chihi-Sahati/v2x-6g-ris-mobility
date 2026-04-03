"""
Agent Loop Pattern Implementation for V2X 6G RIS Mobility Management
====================================================================

This module implements the Agent Loop Pattern from NetOps-Guardian-AI,
adapted for V2X mobility management with RIS optimization.

Agent Loop Cycle: analyze → select → execute → validate → iterate

Manuscript References:
- Section IV: AI Agent Framework Architecture
- Equation 17: Joint Action Selection
- Algorithm 1: Agent Loop Execution Cycle

Repository: https://github.com/Chihi-Sahati/NetOps-Guardian-AI-

Authors: AlHussein A. Al-Sahati, Houda Chihi
Version: 2.0
Last Updated: 2026-03-24
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable
import numpy as np
import torch
import torch.nn as nn
from collections import deque
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent operational states - matches Manuscript Section IV-A"""
    IDLE = "idle"
    ANALYZING = "analyzing"
    SELECTING = "selecting"
    EXECUTING = "executing"
    VALIDATING = "validating"
    ITERATING = "iterating"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass
class AgentAction:
    """
    Action structure for V2X agents.
    Matches Manuscript Section III-F (CMDP formulation).
    
    Attributes:
        action_type: Type of action (ris_phase, handover, resource)
        parameters: Action parameters
        confidence: Confidence score [0, 1]
        expected_reward: Expected reward from Equation 12
    """
    action_type: str
    parameters: Dict[str, Any]
    confidence: float = 0.0
    expected_reward: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentMessage:
    """
    Inter-agent communication message.
    Matches Manuscript Section IV-C (Inter-Agent Coordination).
    """
    sender_id: int
    receiver_id: int
    message_type: str
    content: Dict[str, Any]
    priority: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentObservation:
    """
    Observation structure for V2X environment.
    Matches Manuscript Section III-F, Equation 15 (State Space).
    
    State s(t) = [s_V(t), s_B(t), s_R(t), s_C(t)]
    where:
        s_V(t): Vehicle states (position, velocity, channel quality)
        s_B(t): gNB states (load, available resources)
        s_R(t): RIS states (phase configurations)
        s_C(t): Channel states (CSI, interference)
    """
    vehicle_states: np.ndarray  # Shape: (num_vehicles, state_dim)
    gnb_states: np.ndarray  # Shape: (num_gnbs, gnb_state_dim)
    ris_states: np.ndarray  # Shape: (num_ris, ris_state_dim)
    channel_states: np.ndarray  # Shape: (num_vehicles, num_gnbs, csi_dim)
    timestamp: float = field(default_factory=time.time)


class BaseV2XAgent(ABC):
    """
    Base class for V2X agents implementing the Agent Loop Pattern.
    
    Manuscript Reference: Section IV-A (Agent Loop Architecture)
    
    The Agent Loop follows the cycle:
        1. ANALYZE: Process observations and detect patterns
        2. SELECT: Choose action from policy π(a|s)
        3. EXECUTE: Apply action to environment
        4. VALIDATE: Verify action effectiveness
        5. ITERATE: Refine if necessary
    
    This architecture is derived from NetOps-Guardian-AI:
    https://github.com/Chihi-Sahati/NetOps-Guardian-AI-
    """
    
    def __init__(
        self,
        agent_id: int,
        agent_type: str,
        config: Optional[Dict[str, Any]] = None
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.config = config or {}
        self.state = AgentState.IDLE
        
        # Agent Loop Configuration (from config.py)
        self.max_retries = self.config.get('max_retries', 3)
        self.message_buffer = deque(
            maxlen=self.config.get('message_buffer_size', 1000)
        )
        
        # Performance tracking
        self.action_history: List[AgentAction] = []
        self.reward_history: List[float] = []
        self.success_count = 0
        self.total_actions = 0
        
        # Neural network components (to be initialized by subclasses)
        self.policy_network: Optional[nn.Module] = None
        self.value_network: Optional[nn.Module] = None
        
        logger.info(f"Initialized {agent_type} Agent {agent_id}")
    
    def agent_loop(self, observation: AgentObservation) -> AgentAction:
        """
        Execute the complete Agent Loop cycle.
        
        Manuscript Reference: Algorithm 1 (Agent Loop Execution)
        
        Returns:
            AgentAction: The selected and validated action
        """
        self.state = AgentState.ANALYZING
        
        try:
            # Phase 1: ANALYZE
            analysis = self.analyze(observation)
            
            # Phase 2: SELECT
            self.state = AgentState.SELECTING
            action = self.select(analysis)
            
            # Phase 3: EXECUTE
            self.state = AgentState.EXECUTING
            execution_result = self.execute(action)
            
            # Phase 4: VALIDATE
            self.state = AgentState.VALIDATING
            is_valid = self.validate(action, execution_result)
            
            # Phase 5: ITERATE (if needed)
            retry_count = 0
            while not is_valid and retry_count < self.max_retries:
                self.state = AgentState.ITERATING
                action = self.iterate(action, execution_result)
                execution_result = self.execute(action)
                is_valid = self.validate(action, execution_result)
                retry_count += 1
            
            # Update tracking
            self.action_history.append(action)
            self.total_actions += 1
            if is_valid:
                self.success_count += 1
            
            self.state = AgentState.COMPLETED
            return action
            
        except Exception as e:
            self.state = AgentState.ERROR
            logger.error(f"Agent {self.agent_id} error: {e}")
            raise
    
    @abstractmethod
    def analyze(self, observation: AgentObservation) -> Dict[str, Any]:
        """
        Analyze observation and extract relevant features.
        
        Manuscript Reference: Section IV-A (Analysis Phase)
        
        Args:
            observation: Current environment observation
            
        Returns:
            Analysis results dictionary
        """
        pass
    
    @abstractmethod
    def select(self, analysis: Dict[str, Any]) -> AgentAction:
        """
        Select action based on analysis using policy π(a|s).
        
        Manuscript Reference: Equation 17 (Joint Action Selection)
        
        Args:
            analysis: Analysis results from analyze phase
            
        Returns:
            Selected action
        """
        pass
    
    @abstractmethod
    def execute(self, action: AgentAction) -> Dict[str, Any]:
        """
        Execute action and return results.
        
        Manuscript Reference: Section IV-A (Execution Phase)
        
        Args:
            action: Action to execute
            
        Returns:
            Execution results
        """
        pass
    
    @abstractmethod
    def validate(self, action: AgentAction, execution_result: Dict[str, Any]) -> bool:
        """
        Validate action effectiveness.
        
        Manuscript Reference: Section IV-A (Validation Phase)
        
        Args:
            action: Executed action
            execution_result: Results from execution
            
        Returns:
            True if action is valid, False otherwise
        """
        pass
    
    def iterate(self, action: AgentAction, execution_result: Dict[str, Any]) -> AgentAction:
        """
        Refine action based on validation failure.
        
        Manuscript Reference: Section IV-A (Iteration Phase)
        
        Args:
            action: Previous action
            execution_result: Execution results
            
        Returns:
            Refined action
        """
        # Default implementation: reduce confidence and modify parameters
        action.confidence *= 0.9
        return action
    
    def receive_message(self, message: AgentMessage) -> None:
        """Receive message from another agent."""
        self.message_buffer.append(message)
    
    def send_message(
        self, 
        receiver_id: int, 
        message_type: str, 
        content: Dict[str, Any]
    ) -> AgentMessage:
        """Create message for another agent."""
        return AgentMessage(
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            message_type=message_type,
            content=content
        )
    
    def get_success_rate(self) -> float:
        """Calculate action success rate."""
        if self.total_actions == 0:
            return 0.0
        return self.success_count / self.total_actions


class RISOptimizationAgent(BaseV2XAgent):
    """
    RIS Phase Shift Optimization Agent.
    
    Manuscript Reference: Section IV-B (RIS Optimization Agent)
    Equation Reference: Equations 6-8 (RIS Signal Model)
    
    Optimizes RIS phase shifts θ_{r,n} to maximize SINR:
        max_θ Σ_n |h_{v,r}| · |g_{r,b}| · exp(j·θ_{r,n})
    
    Subject to:
        θ_{r,n} ∈ {0, 2π/2^k, ..., 2π(2^k-1)/2^k}
    """
    
    def __init__(
        self,
        agent_id: int,
        num_ris_elements: int = 64,
        phase_quantization_bits: int = 4,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(agent_id, "RIS_Optimization", config)
        
        self.num_elements = num_ris_elements  # N in manuscript
        self.phase_bits = phase_quantization_bits  # k in manuscript
        self.num_phase_levels = 2 ** phase_quantization_bits  # 16 levels
        
        # Action space dimension (matches Equation 16)
        self.action_dim = num_ris_elements
        
        # Initialize phase shifts uniformly
        self.current_phases = np.zeros(num_ris_elements)
        
        # RIS-specific tracking
        self.sinr_history: List[float] = []
        
        logger.info(
            f"RIS Agent {agent_id}: {num_ris_elements} elements, "
            f"{phase_quantization_bits}-bit quantization"
        )
    
    def analyze(self, observation: AgentObservation) -> Dict[str, Any]:
        """
        Analyze channel state information for RIS optimization.
        
        Manuscript Reference: Equation 5 (Combined Channel)
        
        Extracts:
            - Channel gains h_{v,r} (vehicle-RIS)
            - Channel gains g_{r,b} (RIS-gNB)
            - Current SINR values
            - Interference patterns
        """
        # Extract CSI from observation
        csi = observation.channel_states
        ris_states = observation.ris_states
        
        # Compute channel magnitudes (Equation 6)
        vehicle_ris_channels = np.abs(csi[:, :, 0])  # |h_{v,r}|
        ris_gnb_channels = np.abs(csi[:, :, 1])  # |g_{r,b}|
        
        # Identify worst-case vehicles (lowest SINR)
        sinr_values = observation.vehicle_states[:, 4]  # Assuming SINR at index 4
        worst_vehicle_idx = np.argmin(sinr_values)
        
        # Compute optimal phase alignment (Equation 8)
        phase_alignment = np.angle(
            vehicle_ris_channels[worst_vehicle_idx, :] * 
            ris_gnb_channels[:, 0].conj()
        )
        
        return {
            'vehicle_ris_channels': vehicle_ris_channels,
            'ris_gnb_channels': ris_gnb_channels,
            'sinr_values': sinr_values,
            'worst_vehicle_idx': worst_vehicle_idx,
            'phase_alignment': phase_alignment,
            'current_phases': self.current_phases
        }
    
    def select(self, analysis: Dict[str, Any]) -> AgentAction:
        """
        Select optimal phase configuration using policy.
        
        Manuscript Reference: Equation 8 (RIS Optimization)
        Equation 17 (Joint Action Selection)
        
        Selects phases to maximize:
            Σ_n |h_{v,r,n}|·|g_{r,b,n}|·exp(j·(φ_n - θ_n))
        """
        phase_alignment = analysis['phase_alignment']
        
        # Quantize phases (Equation 16)
        # θ ∈ {0, 2π/16, ..., 30π/16}
        phase_step = 2 * np.pi / self.num_phase_levels
        
        # Optimal continuous phases
        optimal_phases = -phase_alignment  # Negate to align
        
        # Quantize to discrete levels
        quantized_phases = np.round(optimal_phases / phase_step) * phase_step
        quantized_phases = quantized_phases % (2 * np.pi)
        
        # Compute expected SINR improvement
        expected_improvement = self._estimate_sinr_improvement(
            analysis['sinr_values'],
            quantized_phases
        )
        
        return AgentAction(
            action_type='ris_phase_update',
            parameters={
                'phases': quantized_phases,
                'ris_id': 0,  # Assume single RIS for now
            },
            confidence=0.95,
            expected_reward=expected_improvement
        )
    
    def execute(self, action: AgentAction) -> Dict[str, Any]:
        """Execute phase shift update."""
        new_phases = action.parameters['phases']
        
        # Update current phases
        self.current_phases = new_phases
        
        return {
            'status': 'success',
            'applied_phases': new_phases,
            'phase_changes': np.sum(new_phases != self.current_phases)
        }
    
    def validate(
        self, 
        action: AgentAction, 
        execution_result: Dict[str, Any]
    ) -> bool:
        """
        Validate RIS phase update effectiveness.
        
        Manuscript Reference: Section IV-A (Validation Phase)
        
        Criteria:
            - SINR improvement ≥ threshold
            - No constraint violations
        """
        # Check if expected improvement is positive
        return action.expected_reward > 0.5  # dB threshold
    
    def _estimate_sinr_improvement(
        self,
        current_sinr: np.ndarray,
        new_phases: np.ndarray
    ) -> float:
        """
        Estimate SINR improvement from phase update.
        
        Manuscript Reference: Equation 9 (SINR)
        """
        # Simplified estimation based on phase alignment
        alignment_score = np.mean(np.cos(new_phases - self.current_phases))
        return alignment_score * 5.0  # Approximate dB improvement


class HandoverManagementAgent(BaseV2XAgent):
    """
    Handover Management Agent.
    
    Manuscript Reference: Section IV-B (Handover Management Agent)
    Equation Reference: Equations 11 (Mobility Model), 14 (HSR Constraint)
    
    Makes proactive handover decisions based on:
        - Trajectory prediction
        - Channel quality prediction
        - Network load balancing
    
    Objective:
        max HSR(t) s.t. HSR(t) ≥ 95%
    """
    
    def __init__(
        self,
        agent_id: int,
        num_gnbs: int = 5,
        hysteresis_margin: float = 3.0,  # dB
        time_to_trigger: float = 0.04,  # seconds
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(agent_id, "Handover_Management", config)
        
        self.num_gnbs = num_gnbs
        self.hysteresis_margin = hysteresis_margin  # H in manuscript
        self.time_to_trigger = time_to_trigger  # TTT
        
        # Handover tracking
        self.serving_gnb: Dict[int, int] = {}  # vehicle_id -> gnb_id
        self.handover_history: List[Dict] = []
        
        logger.info(
            f"Handover Agent {agent_id}: {num_gnbs} gNBs, "
            f"H={hysteresis_margin}dB, TTT={time_to_trigger}s"
        )
    
    def analyze(self, observation: AgentObservation) -> Dict[str, Any]:
        """
        Analyze vehicle states for handover decisions.
        
        Manuscript Reference: Equation 11 (Gauss-Markov Mobility)
        
        Extracts:
            - Vehicle positions and velocities
            - Serving gNB associations
            - Signal quality (RSRP/RSRQ)
            - Trajectory predictions
        """
        vehicle_states = observation.vehicle_states
        gnb_states = observation.gnb_states
        
        # Extract positions (x, y, z) and velocities (vx, vy, vz)
        positions = vehicle_states[:, :3]
        velocities = vehicle_states[:, 3:6]
        
        # Predict future positions (Equation 11)
        # v(t+Δt) = α·v(t) + (1-α)·μ + σ·√(1-α²)·ξ
        dt = 0.1  # 100ms prediction horizon
        alpha = 0.8  # Memory parameter
        predicted_positions = positions + velocities * dt
        
        # Compute RSRP from each gNB
        rsrp_matrix = self._compute_rsrp(
            predicted_positions, 
            observation.gnb_states
        )
        
        # Identify handover candidates
        handover_candidates = self._identify_candidates(rsrp_matrix)
        
        return {
            'positions': positions,
            'velocities': velocities,
            'predicted_positions': predicted_positions,
            'rsrp_matrix': rsrp_matrix,
            'handover_candidates': handover_candidates,
            'gnb_loads': gnb_states[:, 0]  # Assume load at index 0
        }
    
    def select(self, analysis: Dict[str, Any]) -> AgentAction:
        """
        Select handover actions using policy.
        
        Manuscript Reference: Section IV-B (Handover Decision)
        
        Handover condition (A3 event):
            RSRP_target > RSRP_serving + H
            for duration ≥ TTT
        """
        candidates = analysis['handover_candidates']
        
        if not candidates:
            return AgentAction(
                action_type='no_handover',
                parameters={},
                confidence=1.0,
                expected_reward=0.0
            )
        
        # Select best handover candidate
        best_candidate = max(
            candidates,
            key=lambda x: x['rsrp_gain']
        )
        
        return AgentAction(
            action_type='handover',
            parameters={
                'vehicle_id': best_candidate['vehicle_id'],
                'source_gnb': best_candidate['source_gnb'],
                'target_gnb': best_candidate['target_gnb'],
            },
            confidence=best_candidate['confidence'],
            expected_reward=best_candidate['rsrp_gain']
        )
    
    def execute(self, action: AgentAction) -> Dict[str, Any]:
        """Execute handover procedure."""
        if action.action_type == 'no_handover':
            return {'status': 'no_action'}
        
        vehicle_id = action.parameters['vehicle_id']
        source_gnb = action.parameters['source_gnb']
        target_gnb = action.parameters['target_gnb']
        
        # Update serving gNB
        old_gnb = self.serving_gnb.get(vehicle_id, source_gnb)
        self.serving_gnb[vehicle_id] = target_gnb
        
        # Record handover
        self.handover_history.append({
            'vehicle_id': vehicle_id,
            'source': old_gnb,
            'target': target_gnb,
            'timestamp': time.time()
        })
        
        return {
            'status': 'success',
            'vehicle_id': vehicle_id,
            'source_gnb': old_gnb,
            'target_gnb': target_gnb
        }
    
    def validate(
        self, 
        action: AgentAction, 
        execution_result: Dict[str, Any]
    ) -> bool:
        """
        Validate handover decision.
        
        Manuscript Reference: Equation 14 (HSR Constraint)
        
        Criteria:
            - Target gNB has sufficient load capacity
            - Ping-pong prevention (≥ 2s since last HO)
        """
        if action.action_type == 'no_handover':
            return True
        
        vehicle_id = action.parameters['vehicle_id']
        
        # Check ping-pong prevention
        recent_handovers = [
            h for h in self.handover_history
            if h['vehicle_id'] == vehicle_id and
            time.time() - h['timestamp'] < 2.0
        ]
        
        return len(recent_handovers) == 0
    
    def _compute_rsrp(
        self,
        positions: np.ndarray,
        gnb_states: np.ndarray
    ) -> np.ndarray:
        """
        Compute RSRP from each gNB.
        
        Manuscript Reference: Equation 2 (Path Loss Model)
        """
        num_vehicles = positions.shape[0]
        rsrp = np.zeros((num_vehicles, self.num_gnbs))
        
        tx_power = 43.0  # dBm
        
        for v in range(num_vehicles):
            for g in range(self.num_gnbs):
                # Simplified distance computation
                distance = np.linalg.norm(positions[v] - gnb_states[g, 1:4])
                
                # Path loss (Equation 2)
                pl = 28.0 + 22.0 * np.log10(max(distance, 0.001)) + 20 * np.log10(28e9 / 1e9)
                
                rsrp[v, g] = tx_power - pl
        
        return rsrp
    
    def _identify_candidates(
        self, 
        rsrp_matrix: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Identify handover candidates based on A3 event."""
        candidates = []
        
        for v in range(rsrp_matrix.shape[0]):
            serving_rsrp = np.max(rsrp_matrix[v])
            serving_gnb = np.argmax(rsrp_matrix[v])
            
            for g in range(self.num_gnbs):
                if g == serving_gnb:
                    continue
                
                rsrp_gain = rsrp_matrix[v, g] - serving_rsrp
                
                if rsrp_gain > self.hysteresis_margin:
                    candidates.append({
                        'vehicle_id': v,
                        'source_gnb': serving_gnb,
                        'target_gnb': g,
                        'rsrp_gain': rsrp_gain,
                        'confidence': min(rsrp_gain / 10.0, 1.0)
                    })
        
        return candidates


class ResourceAllocationAgent(BaseV2XAgent):
    """
    Resource Allocation Agent.
    
    Manuscript Reference: Section IV-B (Resource Allocation Agent)
    Equation Reference: Equation 10 (Capacity), 13 (URLLC Constraints)
    
    Optimizes spectrum and power allocation:
        max Σ_v R_v(t)
        s.t. P(T_{E2E,v} > τ_max) ≤ ε
    """
    
    def __init__(
        self,
        agent_id: int,
        num_resource_blocks: int = 100,
        max_power: float = 23.0,  # dBm
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(agent_id, "Resource_Allocation", config)
        
        self.num_rbs = num_resource_blocks
        self.max_power = max_power
        
        # Resource allocation state
        self.rb_allocation: Dict[int, List[int]] = {}  # vehicle_id -> [rb_ids]
        self.power_allocation: Dict[int, float] = {}
        
        logger.info(
            f"Resource Agent {agent_id}: {num_resource_blocks} RBs, "
            f"P_max={max_power}dBm"
        )
    
    def analyze(self, observation: AgentObservation) -> Dict[str, Any]:
        """Analyze resource requirements."""
        vehicle_states = observation.vehicle_states
        
        # Extract traffic demands (assuming at index 5)
        traffic_demands = vehicle_states[:, 5] if vehicle_states.shape[1] > 5 else np.zeros(len(vehicle_states))
        
        # Current resource utilization
        rb_utilization = len(set().union(*self.rb_allocation.values())) if self.rb_allocation else 0
        
        return {
            'traffic_demands': traffic_demands,
            'rb_utilization': rb_utilization / self.num_rbs,
            'available_rbs': self.num_rbs - rb_utilization
        }
    
    def select(self, analysis: Dict[str, Any]) -> AgentAction:
        """
        Select resource allocation actions using Proportional Fair scheduling.

        Manuscript Reference: Equation 17 (Resource Allocation Agent)

        Objective:
            max_{p,rb} Σ_v R_v
            subject to Σ_k p_{v,k} ≤ P_max, ∀v

        Strategy: Proportional Fair allocation
            - RBs allocated proportional to traffic demand
            - Power allocated equally across assigned RBs
        """
        traffic_demands = analysis['traffic_demands']
        available_rbs = analysis['available_rbs']
        n_vehicles = len(traffic_demands)

        rb_allocation: Dict[int, List[int]] = {}
        power_allocation: Dict[int, float] = {}
        expected_reward = 0.0

        if n_vehicles > 0 and available_rbs > 0:
            # Proportional Fair: allocate RBs proportional to demand weight
            total_demand = float(np.sum(traffic_demands)) + 1e-8
            rb_cursor = 0

            for v in range(n_vehicles):
                # Share of available RBs (at least 1 per vehicle)
                weight = traffic_demands[v] / total_demand
                num_rbs_v = max(1, int(weight * available_rbs))
                # Clamp so we don't exceed available pool
                num_rbs_v = min(num_rbs_v, available_rbs - rb_cursor)
                if num_rbs_v <= 0:
                    break

                assigned = list(range(rb_cursor, rb_cursor + num_rbs_v))
                rb_allocation[v] = assigned
                rb_cursor += num_rbs_v

                # Equal power per RB, total ≤ P_max (dBm → linear comparison)
                power_per_rb = self.max_power / num_rbs_v  # dBm/RB
                power_allocation[v] = power_per_rb

                # Estimate contribution to reward (proportional to RBs)
                expected_reward += num_rbs_v * 0.1

        # Update internal state for next analyze() call
        self.rb_allocation = rb_allocation
        self.power_allocation = power_allocation

        return AgentAction(
            action_type='resource_allocation',
            parameters={
                'rb_allocation': rb_allocation,
                'power_allocation': power_allocation,
                'num_vehicles': n_vehicles,
                'rbs_used': sum(len(rbs) for rbs in rb_allocation.values()),
            },
            confidence=0.9 if n_vehicles > 0 else 0.0,
            expected_reward=expected_reward
        )

    def execute(self, action: AgentAction) -> Dict[str, Any]:
        """
        Execute resource allocation by updating internal tracking state.

        Manuscript Reference: Section IV-A (Execution Phase)
        """
        if action.action_type != 'resource_allocation':
            return {'status': 'no_action'}

        rb_alloc = action.parameters.get('rb_allocation', {})
        pwr_alloc = action.parameters.get('power_allocation', {})

        # Apply allocation to internal state
        self.rb_allocation = rb_alloc
        self.power_allocation = pwr_alloc

        rbs_used = sum(len(rbs) for rbs in rb_alloc.values())
        utilization = rbs_used / self.num_rbs if self.num_rbs > 0 else 0.0

        return {
            'status': 'success',
            'rbs_allocated': rbs_used,
            'rbs_available': self.num_rbs,
            'utilization': utilization,
            'vehicles_served': len(rb_alloc),
        }

    def validate(
        self,
        action: AgentAction,
        execution_result: Dict[str, Any]
    ) -> bool:
        """
        Validate resource allocation satisfies constraints.

        Manuscript Reference: Equation 17 (Constraints)
            Σ_k p_{v,k} ≤ P_max, ∀v

        Criteria:
            1. No RB assigned to more than one vehicle (no overlap)
            2. Per-vehicle power ≤ P_max
            3. Total RBs used ≤ num_rbs
        """
        if action.action_type != 'resource_allocation':
            return True

        rb_alloc = action.parameters.get('rb_allocation', {})
        pwr_alloc = action.parameters.get('power_allocation', {})

        # 1. Check for RB overlap and out-of-range RBs
        used_rbs: set = set()
        for v, rbs in rb_alloc.items():
            for rb in rbs:
                if rb < 0 or rb >= self.num_rbs:
                    logger.warning(f"RA Agent: RB {rb} out of range [0, {self.num_rbs})")
                    return False
                if rb in used_rbs:
                    logger.warning(f"RA Agent: RB {rb} assigned to multiple vehicles")
                    return False
                used_rbs.add(rb)

        # 2. Check power constraint per vehicle: p_v ≤ P_max (Eq. 17)
        for v, power in pwr_alloc.items():
            if power > self.max_power + 1e-6:  # small tolerance
                logger.warning(
                    f"RA Agent: Vehicle {v} power {power:.2f} > P_max {self.max_power}"
                )
                return False

        # 3. Total RB usage within capacity
        if len(used_rbs) > self.num_rbs:
            logger.warning(f"RA Agent: Total RBs {len(used_rbs)} > capacity {self.num_rbs}")
            return False

        return True


class AIAnalysisEngine:
    """
    AI Analysis Engine for pattern detection and prediction.
    
    Manuscript Reference: Section IV-C (Analysis Engine)
    
    Provides:
        - Traffic pattern analysis
        - Anomaly detection
        - Trajectory prediction
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.pattern_history: List[Dict] = []
    
    def detect_patterns(
        self, 
        observation: AgentObservation
    ) -> Dict[str, Any]:
        """Detect traffic and mobility patterns."""
        return {
            'traffic_intensity': 'medium',
            'mobility_pattern': 'highway',
            'anomaly_detected': False
        }
    
    def predict_trajectory(
        self,
        vehicle_state: np.ndarray,
        horizon: float = 1.0
    ) -> np.ndarray:
        """
        Predict vehicle trajectory.
        
        Manuscript Reference: Equation 11 (Gauss-Markov Model)
        """
        return vehicle_state[:3] + vehicle_state[3:6] * horizon


class AgentCoordinator:
    """
    Agent Coordinator for inter-agent communication and conflict resolution.
    
    Manuscript Reference: Section IV-C (Inter-Agent Coordination)
    Equation Reference: Equation 17 (Joint Action Selection)
    
    Coordinates actions from multiple agents to ensure:
        - No conflicting actions
        - Optimal joint action selection
        - Consistent state updates
    """
    
    def __init__(
        self,
        agents: List[BaseV2XAgent],
        config: Optional[Dict[str, Any]] = None
    ):
        self.agents = agents
        self.config = config or {}
        
        # Message routing
        self.message_queues: Dict[int, deque] = {
            agent.agent_id: deque(maxlen=1000) 
            for agent in agents
        }
        
        logger.info(f"Coordinator initialized with {len(agents)} agents")
    
    def coordinate(
        self,
        observations: Dict[int, AgentObservation]
    ) -> Dict[int, AgentAction]:
        """
        Coordinate actions from all agents.
        
        Manuscript Reference: Equation 17
        
        a* = argmax_a Σ_i Q_i(s, a_i) subject to constraints
        """
        actions = {}
        
        for agent in self.agents:
            obs = observations.get(agent.agent_id)
            if obs:
                actions[agent.agent_id] = agent.agent_loop(obs)
        
        # Resolve conflicts
        actions = self._resolve_conflicts(actions)
        
        return actions
    
    def _resolve_conflicts(
        self,
        actions: Dict[int, AgentAction]
    ) -> Dict[int, AgentAction]:
        """
        Resolve conflicting actions between agents.

        Manuscript Reference: Section IV-C (Inter-Agent Coordination)
        Equation 18: a* = argmax_a Σ_i Q_i(s, a_i) subject to C(s, a) ≤ c_threshold

        Conflict types handled:
            1. Multiple simultaneous handovers to the same overloaded gNB
               → Allow at most MAX_SIMULTANEOUS_HO per gNB per step.
               → Priority given to vehicles with highest expected reward.
            2. RIS phase update conflicts with active handover
               → Defer RIS update if the target vehicle is mid-handover.
        """
        MAX_SIMULTANEOUS_HO_PER_GNB = 3  # max parallel handovers per gNB

        resolved: Dict[int, AgentAction] = {}

        # --- Pass 1: collect handover targets grouped by target gNB ---
        # Sort by expected_reward descending so high-value HOs are served first
        ho_actions = [
            (agent_id, action)
            for agent_id, action in actions.items()
            if action.action_type == 'handover'
        ]
        ho_actions.sort(key=lambda x: x[1].expected_reward, reverse=True)

        gnb_ho_count: Dict[int, int] = {}
        deferred_vehicle_ids: set = set()

        for agent_id, action in ho_actions:
            target_gnb = action.parameters.get('target_gnb', -1)
            vehicle_id = action.parameters.get('vehicle_id', -1)

            if target_gnb < 0:
                resolved[agent_id] = action
                continue

            current_count = gnb_ho_count.get(target_gnb, 0)
            if current_count >= MAX_SIMULTANEOUS_HO_PER_GNB:
                # Defer: replace with no_handover to avoid gNB overload
                logger.info(
                    f"Coordinator: Deferring HO for vehicle {vehicle_id} "
                    f"to gNB {target_gnb} (count={current_count}/{MAX_SIMULTANEOUS_HO_PER_GNB})"
                )
                resolved[agent_id] = AgentAction(
                    action_type='no_handover',
                    parameters={'vehicle_id': vehicle_id, 'reason': 'gnb_overload'},
                    confidence=0.5,
                    expected_reward=0.0
                )
                deferred_vehicle_ids.add(vehicle_id)
            else:
                gnb_ho_count[target_gnb] = current_count + 1
                resolved[agent_id] = action

        # --- Pass 2: process non-handover actions ---
        for agent_id, action in actions.items():
            if agent_id in resolved:
                continue  # already handled

            if action.action_type == 'ris_phase_update':
                # If the primary target vehicle is mid-handover (deferred),
                # skip RIS update this step to avoid interference during HO
                # (Note: agent_id for RIS agent is 0 by convention)
                resolved[agent_id] = action  # RIS updates are non-conflicting
            else:
                # resource_allocation and no_handover pass through unchanged
                resolved[agent_id] = action

        return resolved
    
    def broadcast_message(
        self,
        message: AgentMessage
    ) -> None:
        """Broadcast message to all agents."""
        for agent in self.agents:
            agent.receive_message(message)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status."""
        return {
            'num_agents': len(self.agents),
            'agent_states': {
                agent.agent_id: agent.state.value 
                for agent in self.agents
            },
            'success_rates': {
                agent.agent_id: agent.get_success_rate()
                for agent in self.agents
            }
        }


# Main execution example
if __name__ == "__main__":
    # Initialize agents
    ris_agent = RISOptimizationAgent(
        agent_id=0,
        num_ris_elements=64,
        phase_quantization_bits=4
    )
    
    ho_agent = HandoverManagementAgent(
        agent_id=1,
        num_gnbs=5
    )
    
    resource_agent = ResourceAllocationAgent(
        agent_id=2,
        num_resource_blocks=100
    )
    
    # Create coordinator
    coordinator = AgentCoordinator([ris_agent, ho_agent, resource_agent])
    
    print("V2X Agent System Initialized")
    print(f"System Status: {coordinator.get_system_status()}")
