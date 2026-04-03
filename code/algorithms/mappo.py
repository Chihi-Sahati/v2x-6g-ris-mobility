"""
MAPPO: Multi-Agent Proximal Policy Optimization
================================================

Implementation of MAPPO algorithm for V2X mobility management.

Manuscript References:
- Section V-B: MAPPO Policy Optimization
- Equation 22: PPO clip objective
- Equation 23: Value function loss
- Equation 24: Entropy bonus
- Equation 25: Combined objective

Original Paper: Yu et al., "The surprising effectiveness of PPO in 
cooperative multi-agent games", NeurIPS 2022 [4]

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


class ActorNetwork(nn.Module):
    """
    Actor (policy) network for MAPPO.
    
    Manuscript Reference: Section V-B
    
    π_θ(a|s) parameterized policy for each agent.
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
        
        # Policy network
        self.fc1 = nn.Linear(state_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, action_dim)
        
        # Action distribution
        self.softmax = nn.Softmax(dim=-1)
    
    def forward(
        self,
        state: torch.Tensor
    ) -> torch.Tensor:
        """Get action probabilities."""
        x = F.relu(self.fc1(state))
        x = F.relu(self.fc2(x))
        logits = self.fc3(x)
        return self.softmax(logits)
    
    def get_action(
        self,
        state: torch.Tensor,
        deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Sample action from policy."""
        probs = self.forward(state)
        
        if deterministic:
            action = probs.argmax(dim=-1)
        else:
            dist = torch.distributions.Categorical(probs)
            action = dist.sample()
        
        log_prob = torch.log(probs.gather(-1, action.unsqueeze(-1)) + 1e-8).squeeze(-1)
        
        return action, log_prob


class CriticNetwork(nn.Module):
    """
    Centralized critic network for MAPPO.
    
    Manuscript Reference: Section V-B
    
    V_φ(s) centralized value function using global state.
    CTDE: Centralized Training, Decentralized Execution
    """
    
    def __init__(
        self,
        state_dim: int,  # Global state dimension
        hidden_dim: int = 64
    ):
        super().__init__()
        
        self.fc1 = nn.Linear(state_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, 1)
    
    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Get state value estimate."""
        x = F.relu(self.fc1(state))
        x = F.relu(self.fc2(x))
        value = self.fc3(x)
        return value


class MAPPOPolicy:
    """
    Complete MAPPO policy combining actor and critic.
    
    Manuscript Reference: Section V-B (Figure 4)
    """
    
    def __init__(
        self,
        num_agents: int,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 64
    ):
        self.num_agents = num_agents
        self.action_dim = action_dim
        
        # Decentralized actors
        self.actors = nn.ModuleList([
            ActorNetwork(state_dim, action_dim, hidden_dim)
            for _ in range(num_agents)
        ])
        
        # Centralized critic
        self.critic = CriticNetwork(state_dim * num_agents, hidden_dim)
    
    def get_actions(
        self,
        states: torch.Tensor,
        deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Get actions from all agents."""
        batch_size = states.shape[0]
        
        actions = []
        log_probs = []
        
        for i, actor in enumerate(self.actors):
            action, log_prob = actor.get_action(states[:, i, :], deterministic)
            actions.append(action)
            log_probs.append(log_prob)
        
        actions = torch.stack(actions, dim=1)  # (batch, num_agents)
        log_probs = torch.stack(log_probs, dim=1)
        
        # Global state value
        global_state = states.view(batch_size, -1)
        values = self.critic(global_state)
        
        return actions, log_probs, values
    
    def evaluate_actions(
        self,
        states: torch.Tensor,
        actions: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Evaluate actions for training."""
        batch_size = states.shape[0]
        
        log_probs = []
        entropies = []
        
        for i, actor in enumerate(self.actors):
            probs = actor(states[:, i, :])
            dist = torch.distributions.Categorical(probs)
            
            log_prob = dist.log_prob(actions[:, i])
            entropy = dist.entropy()
            
            log_probs.append(log_prob)
            entropies.append(entropy)
        
        log_probs = torch.stack(log_probs, dim=1)
        entropies = torch.stack(entropies, dim=1)
        
        # Global state value
        global_state = states.view(batch_size, -1)
        values = self.critic(global_state)
        
        return log_probs, values, entropies


class RolloutBuffer:
    """Buffer for storing rollout data."""
    
    def __init__(self, capacity: int = 2048):
        self.capacity = capacity
        self.states: List[torch.Tensor] = []
        self.actions: List[torch.Tensor] = []
        self.rewards: List[float] = []
        self.values: List[float] = []
        self.log_probs: List[torch.Tensor] = []
        self.dones: List[bool] = []
    
    def push(
        self,
        state: torch.Tensor,
        action: torch.Tensor,
        reward: float,
        value: float,
        log_prob: torch.Tensor,
        done: bool
    ):
        self.states.append(state)
        self.actions.append(action)
        self.rewards.append(reward)
        self.values.append(value)
        self.log_probs.append(log_prob)
        self.dones.append(done)
    
    def clear(self):
        self.states.clear()
        self.actions.clear()
        self.rewards.clear()
        self.values.clear()
        self.log_probs.clear()
        self.dones.clear()
    
    def __len__(self):
        return len(self.states)


class MAPPOTrainer:
    """
    MAPPO training algorithm.
    
    Manuscript Reference: Section V-B (Algorithm 3)
    
    Training objective (Equations 22-25):
        L^CLIP(θ) = E[min(r(θ)·A, clip(r(θ), 1-ε, 1+ε)·A)]
        L^VF(φ) = E[(V_φ(s) - R)^2]
        L^ENT(θ) = E[H(π_θ)]
        
        Total: L(θ, φ) = -L^CLIP + c_1·L^VF - c_2·L^ENT
    """
    
    def __init__(
        self,
        policy: MAPPOPolicy,
        lr: float = 5e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.2,
        entropy_coef: float = 0.01,
        value_loss_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        ppo_epochs: int = 5,
        mini_batch_size: int = 32
    ):
        self.policy = policy
        self.gamma = gamma  # From config.py
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon  # ε in Equation 22
        self.entropy_coef = entropy_coef  # c_2 in Equation 25
        self.value_loss_coef = value_loss_coef  # c_1 in Equation 25
        self.max_grad_norm = max_grad_norm
        self.ppo_epochs = ppo_epochs
        self.mini_batch_size = mini_batch_size
        
        # Optimizers
        self.actor_optimizer = optim.Adam(policy.actors.parameters(), lr=lr)
        self.critic_optimizer = optim.Adam(policy.critic.parameters(), lr=lr)
        
        # Rollout buffer
        self.buffer = RolloutBuffer()
    
    def compute_gae(
        self,
        rewards: List[float],
        values: List[float],
        dones: List[bool],
        next_value: float
    ) -> Tuple[List[float], List[float]]:
        """
        Compute Generalized Advantage Estimation.
        
        Manuscript Reference: Equation 22 (Advantage)
        
        A_t = Σ_{l=0}^{∞} (γλ)^l · δ_{t+l}
        where δ_t = r_t + γV(s_{t+1}) - V(s_t)
        """
        advantages = []
        returns = []
        gae = 0.0
        
        # Work backwards
        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_val = next_value
            else:
                next_val = values[t + 1]
            
            # TD error
            delta = rewards[t] + self.gamma * next_val * (1 - dones[t]) - values[t]
            
            # GAE
            gae = delta + self.gamma * self.gae_lambda * (1 - dones[t]) * gae
            
            advantages.insert(0, gae)
            returns.insert(0, gae + values[t])
        
        return advantages, returns
    
    def train(self) -> Dict[str, float]:
        """
        Execute PPO training update.
        
        Manuscript Reference: Equations 22-25
        """
        if len(self.buffer) < self.mini_batch_size:
            return {'loss': 0.0}
        
        # Get data from buffer
        states = torch.stack(self.buffer.states)
        actions = torch.stack(self.buffer.actions)
        old_log_probs = torch.stack(self.buffer.log_probs)
        rewards = self.buffer.rewards
        values = self.buffer.values
        dones = self.buffer.dones
        
        # Compute next value for GAE
        with torch.no_grad():
            next_state = states[-1].unsqueeze(0)
            _, _, next_value = self.policy.get_actions(next_state, deterministic=True)
            next_value = next_value.item()
        
        # Compute advantages and returns
        advantages, returns = self.compute_gae(rewards, values, dones, next_value)
        
        advantages = torch.tensor(advantages, dtype=torch.float32)
        returns = torch.tensor(returns, dtype=torch.float32)
        
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        total_loss = 0.0
        
        # PPO epochs
        for _ in range(self.ppo_epochs):
            # Mini-batch updates
            indices = np.random.permutation(len(self.buffer))
            
            for start in range(0, len(self.buffer), self.mini_batch_size):
                end = start + self.mini_batch_size
                mb_indices = indices[start:end]
                
                mb_states = states[mb_indices]
                mb_actions = actions[mb_indices]
                mb_old_log_probs = old_log_probs[mb_indices]
                mb_advantages = advantages[mb_indices]
                mb_returns = returns[mb_indices]
                
                # Evaluate current policy
                new_log_probs, new_values, entropies = self.policy.evaluate_actions(
                    mb_states, mb_actions
                )
                
                # Policy loss (Equation 22)
                ratio = torch.exp(new_log_probs.sum(dim=1) - mb_old_log_probs.sum(dim=1))
                surr1 = ratio * mb_advantages
                surr2 = torch.clamp(
                    ratio,
                    1 - self.clip_epsilon,
                    1 + self.clip_epsilon
                ) * mb_advantages
                policy_loss = -torch.min(surr1, surr2).mean()
                
                # Value loss (Equation 23)
                value_loss = F.mse_loss(new_values.squeeze(), mb_returns)
                
                # Entropy bonus (Equation 24)
                entropy_loss = -entropies.mean()
                
                # Combined loss (Equation 25)
                loss = (
                    policy_loss
                    + self.value_loss_coef * value_loss
                    + self.entropy_coef * entropy_loss
                )
                
                # Optimize
                self.actor_optimizer.zero_grad()
                self.critic_optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    self.policy.parameters(), 
                    self.max_grad_norm
                )
                self.actor_optimizer.step()
                self.critic_optimizer.step()
                
                total_loss += loss.item()
        
        # Clear buffer
        self.buffer.clear()
        
        return {
            'loss': total_loss / (self.ppo_epochs * (len(self.buffer) // self.mini_batch_size + 1)),
            'policy_loss': policy_loss.item(),
            'value_loss': value_loss.item(),
            'entropy': -entropy_loss.item()
        }
    
    def collect_experience(
        self,
        state: torch.Tensor,
        action: torch.Tensor,
        reward: float,
        value: float,
        log_prob: torch.Tensor,
        done: bool
    ):
        """Store experience in buffer."""
        self.buffer.push(state, action, reward, value, log_prob, done)


# Main execution example
if __name__ == "__main__":
    # Initialize MAPPO policy (matching config.py parameters)
    num_agents = 3  # RIS, Handover, Resource agents
    state_dim = 6  # Position + velocity
    action_dim = 16  # RIS phases + handover decisions
    
    policy = MAPPOPolicy(
        num_agents=num_agents,
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_dim=64
    )
    
    trainer = MAPPOTrainer(
        policy=policy,
        lr=5e-4,
        gamma=0.99,
        gae_lambda=0.95,
        clip_epsilon=0.2,
        entropy_coef=0.01,
        value_loss_coef=0.5
    )
    
    print(f"MAPPO Policy initialized with {num_agents} agents")
    print(f"Parameters: γ=0.99, ε=0.2, c_1=0.5, c_2=0.01")
