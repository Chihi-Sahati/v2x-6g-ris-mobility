"""
QMIX: Monotonic Value Function Factorisation for Deep Multi-Agent RL
=====================================================================

Implementation of QMIX algorithm for V2X mobility management.

Manuscript References:
- Section V-A: QMIX Value Decomposition
- Equation 18: Q_total = f_mix(Q_1, ..., Q_n)
- Equation 19: Monotonicity constraint ∂Q_total/∂Q_i ≥ 0
- Equation 20: Mixing network architecture

Original Paper: Rashid et al., "QMIX: Monotonic value function factorisation 
for deep multi-agent reinforcement learning", ICML 2018 [3]

Authors: AlHussein A. Al-Sahati, Houda Chihi
Version: 2.0
Last Updated: 2026-03-24
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque
import random


class QNetwork(nn.Module):
    """
    Individual agent Q-network.
    
    Manuscript Reference: Section V-A
    
    Approximates Q_i(s_i, a_i) for each agent.
    """
    
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 64
    ):
        super().__init__()
        
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # DRQN architecture
        self.fc1 = nn.Linear(state_dim, hidden_dim)
        self.rnn = nn.GRUCell(hidden_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, action_dim)
    
    def forward(
        self,
        state: torch.Tensor,
        hidden: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass through Q-network."""
        x = F.relu(self.fc1(state))
        
        if hidden is not None:
            h = self.rnn(x, hidden)
        else:
            h = self.rnn(x, torch.zeros_like(x))
        
        q_values = self.fc2(h)
        return q_values, h


class MixingNetwork(nn.Module):
    """
    Mixing network for value decomposition.
    
    Manuscript Reference: Equation 18, 19, 20
    
    Computes Q_total = f_mix(Q_1, ..., Q_n) with monotonicity constraint:
        ∂Q_total/∂Q_i ≥ 0 for all i
    
    Uses hypernetworks to generate weights conditioned on global state.
    """
    
    def __init__(
        self,
        num_agents: int,
        state_dim: int,
        mixing_embed_dim: int = 32,
        hypernet_embed_dim: int = 64
    ):
        super().__init__()
        
        self.num_agents = num_agents
        self.state_dim = state_dim
        
        # Hypernetworks for generating mixing weights (Equation 20)
        # W_1: (state_dim, num_agents * mixing_embed_dim)
        self.hyper_w1 = nn.Sequential(
            nn.Linear(state_dim, hypernet_embed_dim),
            nn.ReLU(),
            nn.Linear(hypernet_embed_dim, num_agents * mixing_embed_dim)
        )
        
        # W_2: (state_dim, mixing_embed_dim)
        self.hyper_w2 = nn.Sequential(
            nn.Linear(state_dim, hypernet_embed_dim),
            nn.ReLU(),
            nn.Linear(hypernet_embed_dim, mixing_embed_dim)
        )
        
        # Bias hypernetworks
        self.hyper_b1 = nn.Linear(state_dim, mixing_embed_dim)
        self.hyper_b2 = nn.Sequential(
            nn.Linear(state_dim, mixing_embed_dim),
            nn.ReLU(),
            nn.Linear(mixing_embed_dim, 1)
        )
        
        self.mixing_embed_dim = mixing_embed_dim
    
    def forward(
        self,
        agent_qs: torch.Tensor,
        states: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute Q_total from individual Q-values.
        
        Manuscript Reference: Equation 18
        
        Args:
            agent_qs: (batch, num_agents) individual Q-values
            states: (batch, state_dim) global state
            
        Returns:
            Q_total: (batch, 1) joint Q-value
        """
        batch_size = agent_qs.shape[0]
        
        # Generate weights from hypernetworks (Equation 20)
        w1 = torch.abs(self.hyper_w1(states))  # Ensure positive (monotonicity)
        w1 = w1.view(batch_size, self.num_agents, self.mixing_embed_dim)
        
        w2 = torch.abs(self.hyper_w2(states))
        w2 = w2.view(batch_size, self.mixing_embed_dim, 1)
        
        # Bias
        b1 = self.hyper_b1(states).view(batch_size, 1, self.mixing_embed_dim)
        b2 = self.hyper_b2(states).view(batch_size, 1, 1)
        
        # First layer (Equation 18)
        hidden = F.elu(
            torch.bmm(agent_qs.unsqueeze(1), w1) + b1
        )
        
        # Second layer
        q_total = torch.bmm(hidden, w2) + b2
        
        return q_total


class QMIXNetwork(nn.Module):
    """
    Complete QMIX network combining agent networks and mixing network.
    
    Manuscript Reference: Section V-A (Figure 3)
    """
    
    def __init__(
        self,
        num_agents: int,
        state_dim: int,
        action_dim: int,
        mixing_embed_dim: int = 32,
        hypernet_embed_dim: int = 64,
        hidden_dim: int = 64
    ):
        super().__init__()
        
        self.num_agents = num_agents
        self.action_dim = action_dim
        
        # Agent Q-networks
        self.agent_q_networks = nn.ModuleList([
            QNetwork(state_dim, action_dim, hidden_dim)
            for _ in range(num_agents)
        ])
        
        # Target networks
        self.target_agent_q_networks = nn.ModuleList([
            QNetwork(state_dim, action_dim, hidden_dim)
            for _ in range(num_agents)
        ])
        
        # Mixing network
        self.mixing_network = MixingNetwork(
            num_agents, state_dim * num_agents,
            mixing_embed_dim, hypernet_embed_dim
        )
        self.target_mixing_network = MixingNetwork(
            num_agents, state_dim * num_agents,
            mixing_embed_dim, hypernet_embed_dim
        )
        
        # Copy to target networks
        self._update_target_networks()
    
    def forward(
        self,
        states: torch.Tensor,
        actions: Optional[torch.Tensor] = None,
        hidden_states: Optional[List[torch.Tensor]] = None
    ) -> Tuple[torch.Tensor, List[torch.Tensor]]:
        """
        Compute joint Q-value.
        
        Manuscript Reference: Equation 18
        """
        batch_size = states.shape[0]
        
        # Compute individual Q-values
        agent_qs = []
        new_hidden_states = []
        
        for i, q_net in enumerate(self.agent_q_networks):
            hidden = hidden_states[i] if hidden_states else None
            q_values, new_hidden = q_net(states[:, i, :], hidden)
            
            if actions is not None:
                q_i = q_values.gather(1, actions[:, i].unsqueeze(1))
            else:
                q_i = q_values.max(dim=1, keepdim=True)[0]
            
            agent_qs.append(q_i)
            new_hidden_states.append(new_hidden)
        
        # Stack Q-values
        agent_qs = torch.cat(agent_qs, dim=1)  # (batch, num_agents)
        
        # Global state (concatenated)
        global_state = states.view(batch_size, -1)
        
        # Mix Q-values (Equation 18)
        q_total = self.mixing_network(agent_qs, global_state)
        
        return q_total, new_hidden_states
    
    def _update_target_networks(self):
        """Copy weights to target networks."""
        for i in range(self.num_agents):
            self.target_agent_q_networks[i].load_state_dict(
                self.agent_q_networks[i].state_dict()
            )
        self.target_mixing_network.load_state_dict(
            self.mixing_network.state_dict()
        )


class ReplayBuffer:
    """Experience replay buffer for QMIX."""
    
    def __init__(self, capacity: int = 100000):
        self.buffer = deque(maxlen=capacity)
    
    def push(self, experience: Dict):
        self.buffer.append(experience)
    
    def sample(self, batch_size: int) -> Dict:
        batch = random.sample(self.buffer, batch_size)
        return {
            key: torch.stack([b[key] for b in batch])
            for key in batch[0].keys()
        }
    
    def __len__(self):
        return len(self.buffer)


class QMIXTrainer:
    """
    QMIX training algorithm.
    
    Manuscript Reference: Section V-A (Algorithm 2)
    Equation 21: Loss = (y - Q_total(s, a))²
    
    Training procedure:
        1. Collect experiences (s, a, r, s')
        2. Compute target: y = r + γ·max_a' Q_total(s', a')
        3. Minimize TD loss
    """
    
    def __init__(
        self,
        network: QMIXNetwork,
        lr: float = 5e-4,
        gamma: float = 0.99,
        batch_size: int = 32,
        target_update_freq: int = 200,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.05,
        epsilon_decay: int = 50000
    ):
        self.network = network
        self.gamma = gamma  # From config.py
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        
        # Optimizer
        self.optimizer = optim.Adam(network.parameters(), lr=lr)
        
        # Replay buffer
        self.buffer = ReplayBuffer()
        
        # Epsilon-greedy exploration
        self.epsilon = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        
        # Training counter
        self.train_step = 0
    
    def select_action(
        self,
        states: torch.Tensor,
        hidden_states: Optional[List[torch.Tensor]] = None,
        explore: bool = True
    ) -> Tuple[List[int], List[torch.Tensor]]:
        """
        Select actions using epsilon-greedy.
        
        Manuscript Reference: Equation 17 (Joint Action)
        """
        actions = []
        new_hidden_states = []
        
        for i, q_net in enumerate(self.network.agent_q_networks):
            hidden = hidden_states[i] if hidden_states else None
            q_values, new_hidden = q_net(states[:, i, :], hidden)
            
            if explore and random.random() < self.epsilon:
                action = random.randint(0, self.network.action_dim - 1)
            else:
                action = q_values.argmax(dim=1).item()
            
            actions.append(action)
            new_hidden_states.append(new_hidden)
        
        return actions, new_hidden_states
    
    def train_step_fn(self) -> float:
        """
        Execute one training step.
        
        Manuscript Reference: Equation 21
        
        Loss = E[(r + γ·max_a' Q_target(s', a') - Q(s, a))²]
        """
        if len(self.buffer) < self.batch_size:
            return 0.0
        
        # Sample batch
        batch = self.buffer.sample(self.batch_size)
        
        states = batch['states']
        actions = batch['actions']
        rewards = batch['rewards']
        next_states = batch['next_states']
        dones = batch['dones']
        
        # Compute current Q_total
        q_total, _ = self.network(states, actions)
        
        # Compute target Q_total
        with torch.no_grad():
            # Get best actions for next state
            next_agent_qs = []
            for i, q_net in enumerate(self.network.agent_q_networks):
                q_values, _ = q_net(next_states[:, i, :])
                next_agent_qs.append(q_values.max(dim=1, keepdim=True)[0])
            
            next_agent_qs = torch.cat(next_agent_qs, dim=1)
            global_state = next_states.view(self.batch_size, -1)
            
            target_q_total = self.network.target_mixing_network(
                next_agent_qs, global_state
            )
            
            # Target value (Equation 21)
            target = rewards + self.gamma * (1 - dones) * target_q_total
        
        # TD loss
        loss = F.mse_loss(q_total, target)
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.network.parameters(), 10)
        self.optimizer.step()
        
        # Update target networks
        self.train_step += 1
        if self.train_step % self.target_update_freq == 0:
            self.network._update_target_networks()
        
        # Decay epsilon
        self.epsilon = max(
            self.epsilon_end,
            self.epsilon - (1 - self.epsilon_end) / self.epsilon_decay
        )
        
        return loss.item()


# Main execution example
if __name__ == "__main__":
    # Initialize QMIX network (matching config.py parameters)
    num_agents = 3  # RIS, Handover, Resource agents
    state_dim = 6  # Position + velocity
    action_dim = 16  # RIS phases + handover decisions
    
    network = QMIXNetwork(
        num_agents=num_agents,
        state_dim=state_dim,
        action_dim=action_dim,
        mixing_embed_dim=32,
        hypernet_embed_dim=64
    )
    
    trainer = QMIXTrainer(
        network=network,
        lr=5e-4,
        gamma=0.99,
        batch_size=32
    )
    
    print(f"QMIX Network initialized with {num_agents} agents")
    print(f"Parameters: γ=0.99, lr=5e-4, batch=32")
