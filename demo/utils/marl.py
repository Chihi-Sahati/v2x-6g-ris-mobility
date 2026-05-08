import numpy as np

# =========================================================================
# Eq(19): Q_tot = f_mix(Q_1, ..., Q_n)   QMIX Value Decomposition
# Eq(20): dQ_tot/dQ_i >= 0                Monotonicity Constraint
# Eq(21): L = E[(y - Q_tot)^2]            QMIX Loss
# =========================================================================

class QMIXAgent:
    def __init__(self, agent_id, obs_dim=4, act_dim=3, hidden=32):
        self.agent_id = agent_id
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        self.hidden = hidden
        self.W1 = np.random.randn(obs_dim, hidden) * 0.1
        self.b1 = np.zeros(hidden)
        self.W2 = np.random.randn(hidden, act_dim) * 0.1
        self.b2 = np.zeros(act_dim)
        self.target_W1 = self.W1.copy()
        self.target_b1 = self.b1.copy()
        self.target_W2 = self.W2.copy()
        self.target_b2 = self.b2.copy()

    def q_values(self, obs, use_target=False):
        if use_target:
            h = np.tanh(obs @ self.target_W1 + self.target_b1)
            return h @ self.target_W2 + self.target_b2
        h = np.tanh(obs @ self.W1 + self.b1)
        return h @ self.W2 + self.b2

    def select_action(self, obs, epsilon=0.1):
        if np.random.random() < epsilon:
            return np.random.randint(self.act_dim)
        q = self.q_values(obs)
        return np.argmax(q)

    def update_target(self):
        self.target_W1 = self.W1.copy()
        self.target_b1 = self.b1.copy()
        self.target_W2 = self.W2.copy()
        self.target_b2 = self.b2.copy()


class QMIXMixer:
    def __init__(self, n_agents, state_dim=10, hidden=32):
        self.n_agents = n_agents
        self.state_dim = state_dim
        self.hidden = hidden
        self.hyper_W1 = np.random.randn(state_dim, hidden * n_agents) * 0.1
        self.hyper_b1 = np.zeros(hidden * n_agents)
        self.hyper_W2 = np.random.randn(state_dim, hidden) * 0.1
        self.hyper_b2 = np.zeros(hidden)
        self.W_out = np.random.randn(hidden, 1) * 0.1

    def mix(self, agent_qs, state):
        batch = agent_qs.shape[0] if len(agent_qs.shape) > 1 else 1
        if len(agent_qs.shape) == 1:
            agent_qs = agent_qs.reshape(1, -1)
        if len(state.shape) == 1:
            state = state.reshape(1, -1)
        w1 = np.abs(state @ self.hyper_W1 + self.hyper_b1)
        w1 = w1.reshape(batch, self.n_agents, self.hidden)
        h = np.zeros((batch, self.hidden))
        for i in range(self.n_agents):
            h += agent_qs[:, i:i+1] * w1[:, i, :]
        h = np.tanh(h)
        w2 = np.abs(state @ self.hyper_W2 + self.hyper_b2)
        w2 = np.tanh(w2)
        q_tot = h * w2 @ self.W_out
        return q_tot.flatten()

    def loss(self, agent_qs, state, target, gamma=0.99):
        q_tot = self.mix(agent_qs, state)
        td_error = target - q_tot
        return np.mean(td_error ** 2), td_error

# =========================================================================
# Eq(22): L^CLIP = E[min(r*A, clip(r,1-e,1+e)*A)]   MAPPO Policy
# Eq(23): L^VF = E[(V - R)^2]                         Value Loss
# Eq(24): L = -L^CLIP + c1*L^VF - c2*H(pi)            Total Loss
# =========================================================================

class MAPPOAgent:
    def __init__(self, agent_id, obs_dim=4, act_dim=3, hidden=32, clip_eps=0.2, c1=0.5, c2=0.01):
        self.agent_id = agent_id
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        self.hidden = hidden
        self.clip_eps = clip_eps
        self.c1 = c1
        self.c2 = c2
        self.pi_W1 = np.random.randn(obs_dim, hidden) * 0.1
        self.pi_b1 = np.zeros(hidden)
        self.pi_W2 = np.random.randn(hidden, act_dim) * 0.1
        self.pi_b2 = np.zeros(act_dim)
        self.old_pi_W1 = self.pi_W1.copy()
        self.old_pi_b1 = self.pi_b1.copy()
        self.value_W1 = np.random.randn(obs_dim, hidden) * 0.1
        self.value_b1 = np.zeros(hidden)
        self.value_W2 = np.random.randn(hidden, 1) * 0.1
        self.value_b2 = np.zeros(0)

    def policy(self, obs):
        h = np.tanh(obs @ self.pi_W1 + self.pi_b1)
        logits = h @ self.pi_W2 + self.pi_b2
        exp_l = np.exp(logits - np.max(logits))
        return exp_l / np.sum(exp_l)

    def old_policy(self, obs):
        h = np.tanh(obs @ self.old_pi_W1 + self.old_pi_b1)
        logits = h @ self.old_pi_W2 + self.old_pi_b2
        exp_l = np.exp(logits - np.max(logits))
        return exp_l / np.sum(exp_l)

    def value(self, obs):
        h = np.tanh(obs @ self.value_W1 + self.value_b1)
        return (h @ self.value_W2 + self.value_b2).flatten()

    def select_action(self, obs):
        probs = self.policy(obs)
        return np.random.choice(self.act_dim, p=probs)

    def compute_advantage(self, rewards, values, gamma=0.99, lam=0.95):
        T = len(rewards)
        advantages = np.zeros(T)
        gae = 0
        for t in reversed(range(T)):
            delta = rewards[t] + gamma * (values[t+1] if t+1 < T else values[-1]) - values[t]
            gae = delta + gamma * lam * gae
            advantages[t] = gae
        return advantages

    def clip_loss(self, obs, actions, advantages):
        probs = self.policy(obs)
        old_probs = self.old_policy(obs)
        ratios = np.zeros(len(actions))
        for i, a in enumerate(actions):
            ratios[i] = probs[a] / (old_probs[a] + 1e-8)
        clipped = np.clip(ratios, 1-self.clip_eps, 1+self.clip_eps)
        return np.mean(np.minimum(ratios * advantages, clipped * advantages))

    def entropy(self, obs):
        probs = self.policy(obs)
        return -np.sum(probs * np.log(probs + 1e-8))

    def total_loss(self, obs, actions, advantages, rewards):
        l_clip = self.clip_loss(obs, actions, advantages)
        v = self.value(obs)
        l_vf = np.mean((v - rewards) ** 2)
        h = self.entropy(obs)
        return -l_clip + self.c1 * l_vf - self.c2 * h

    def update_old_policy(self):
        self.old_pi_W1 = self.pi_W1.copy()
        self.old_pi_b1 = self.pi_b1.copy()

# =========================================================================
# Eq(12): max E[Sigma gamma^t * Sigma w * R(t)]    CMDP Objective
# Eq(13): P(T_E2E > tau_max) <= epsilon             URLLC Constraint
# Eq(14): HSR(t) >= HSR_min                         HO Constraint
# =========================================================================

class CMDP:
    def __init__(self, n_agents=3, gamma=0.99, tau_max=1.0, epsilon=1e-5, hsr_min=95.0):
        self.n_agents = n_agents
        self.gamma = gamma
        self.tau_max = tau_max
        self.epsilon = epsilon
        self.hsr_min = hsr_min
        self.lambda_urlcc = 0.1
        self.lambda_hsr = 0.1
        self.lr_lambda = 0.01

    def reward(self, throughput, latency, hsr, ris_gain):
        w_tp = 0.4
        w_lat = 0.3
        w_hsr = 0.2
        w_ris = 0.1
        r_tp = throughput / 2000.0
        r_lat = max(0, 1.0 - latency / 2.0)
        r_hsr = hsr / 100.0
        r_ris = ris_gain / 10.0
        return w_tp * r_tp + w_lat * r_lat + w_hsr * r_hsr + w_ris * r_ris

    def constraint_urlcc(self, latency_samples):
        exceed = sum(1 for l in latency_samples if l > self.tau_max)
        violation_rate = exceed / max(len(latency_samples), 1)
        return violation_rate <= self.epsilon, violation_rate

    def constraint_hsr(self, current_hsr):
        return current_hsr >= self.hsr_min, current_hsr

    def lagrangian_reward(self, base_reward, urlcc_violation, hsr_value):
        urlcc_ok, urlcc_rate = True, 0
        if isinstance(urlcc_violation, tuple):
            urlcc_ok, urlcc_rate = urlcc_violation
        penalty_urlcc = self.lambda_urlcc * urlcc_rate if not urlcc_ok else 0
        hsr_ok, hsr_val = True, hsr_value
        if isinstance(hsr_value, tuple):
            hsr_ok, hsr_val = hsr_value
        penalty_hsr = self.lambda_hsr * max(0, self.hsr_min - hsr_val) / 100.0 if not hsr_ok else 0
        return base_reward - penalty_urlcc - penalty_hsr

    def update_lambdas(self, urlcc_violation, hsr_value):
        if isinstance(urlcc_violation, tuple):
            _, urlcc_rate = urlcc_violation
            self.lambda_urlcc = max(0, self.lambda_urlcc + self.lr_lambda * (urlcc_rate - self.epsilon))
        if isinstance(hsr_value, tuple):
            _, hsr_val = hsr_value
            self.lambda_hsr = max(0, self.lambda_hsr + self.lr_lambda * (self.hsr_min - hsr_val) / 100.0)

# =========================================================================
# Eq(25): V(s) = E[Sigma gamma^t * ||grad J||^2]    Lyapunov Function
# Eq(26): ||Q_k - Q*|| <= rho^k * ||Q_0 - Q*||      QMIX Convergence
# Eq(27): O(1/eps^3) episodes for eps-optimal         MAPPO Complexity
# Eq(28): E[V(t+1) - V(t)] <= -c * ||grad J||^2      Stability
# =========================================================================

class LyapunovAnalyzer:
    def __init__(self, gamma=0.99):
        self.gamma = gamma
        self.gradient_history = []
        self.lyapunov_history = []
        self.convergence_rate = 0.95
        self.q_error_history = []

    def compute_lyapunov(self, gradients):
        grad_norm_sq = np.sum(np.array(gradients) ** 2)
        self.gradient_history.append(grad_norm_sq)
        V = sum(self.gamma ** i * g for i, g in enumerate(self.gradient_history[-100:]))
        self.lyapunov_history.append(V)
        return V

    def check_stability(self, window=10):
        if len(self.lyapunov_history) < window:
            return True, 1.0
        recent = self.lyapunov_history[-window:]
        is_decreasing = all(recent[i] >= recent[i+1] for i in range(len(recent)-1))
        if len(recent) > 1:
            rate = recent[-1] / (recent[0] + 1e-8)
        else:
            rate = 1.0
        return is_decreasing, rate

    def qmix_convergence_bound(self, q_error_initial, episode):
        bound = (self.convergence_rate ** episode) * q_error_initial
        self.q_error_history.append(bound)
        return bound

    def mappo_sample_complexity(self, epsilon):
        return int(np.ceil(1.0 / (epsilon ** 3)))

    def lyapunov_condition(self, V_current, V_next, grad_norm_sq, c=0.01):
        delta = V_next - V_current
        satisfies = delta <= -c * grad_norm_sq
        return satisfies, delta