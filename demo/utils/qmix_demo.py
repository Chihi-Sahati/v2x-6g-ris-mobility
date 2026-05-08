import numpy as np

class QMIXSkeleton:
    def __init__(self, n_agents: int = 3, obs_dim: int = 4, act_dim: int = 3):
        self.n_agents = n_agents
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        # simple weights for a toy policy
        self._w = np.random.randn(n_agents, obs_dim) * 0.1
        self._b = np.zeros(n_agents)

    def predict(self, obs):
        # obs can be a 1D vector or a 2D batch
        arr = np.atleast_2d(np.asarray(obs))
        # compute simple Q for each agent
        q = arr @ self._w.T + self._b
        # choose action with max Q for each agent, clip to act_dim
        actions = np.argmax(q, axis=-1)
        if actions.ndim == 0:
            return int(actions)
        return [int(a) for a in actions]

    def update(self, *args, **kwargs):
        # placeholder for training step
        pass

class QMIXMixer:
    def __init__(self, n_agents: int = 3, state_dim: int = 4):
        self.n_agents = n_agents
        self.state_dim = state_dim
        # simple linear mixing parameters (toy)
        self.W1 = np.ones((self.state_dim, 1)) * 0.1
        self.b1 = 0.0

    def mix(self, agent_qs, state=None):
        a = np.asarray(agent_qs)
        if a.ndim == 1:
            a = a.reshape(1, -1)
        if a.shape[1] != self.n_agents:
            # align size
            a = np.resize(a, (a.shape[0], self.n_agents))
        if state is None:
            state = np.zeros(self.state_dim)
        if state.ndim == 0:
            state = np.array([state])
        # simple joint value: sum of agent Qs plus a small portion of state
        joint = a.sum(axis=1) * 0.5 + np.sum(state) * 0.2
        return joint if joint.size > 1 else float(joint)
