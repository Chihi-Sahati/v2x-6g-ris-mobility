import numpy as np

class RISAgent:
    def __init__(self, panel_id=0, n_elem=64):
        self.panel_id = panel_id
        self.n_elem = n_elem
        self.last_action = np.zeros(n_elem)

    def act(self, sinr_db):
        # Simple policy: if SINR is low, randomize phases; if high, keep stable
        if sinr_db < 5:
            action = np.random.uniform(0, 2*np.pi, self.n_elem)
        else:
            action = self.last_action + np.random.normal(0, 0.1, self.n_elem)
        self.last_action = action
        return action

class HOAgent:
    def __init__(self):
        self.last_gnb = -1

    def act(self, current_gnb, sinr_db, target_sinr_db):
        # Simple policy: handover if target is significantly better
        if target_sinr_db > sinr_db + 3.0:
            return True
        return False

class RAAgent:
    def __init__(self):
        pass

    def act(self, sinr_db):
        # Simple policy: allocate more resources if SINR is low
        if sinr_db < 10:
            return 1.5  # Boost factor
        return 1.0

class MARLCoordinator:
    def __init__(self, n_panels=3, n_elements=64):
        self.ris_agents = [RISAgent(i, n_elements) for i in range(n_panels)]
        self.ho_agent = HOAgent()
        self.ra_agent = RAAgent()

    def step(self, vehicle, nearest_ris_idx, target_gnb_sinr, all_gnbs):
        # 1. RIS Action
        if nearest_ris_idx is not None:
            phases = self.ris_agents[nearest_ris_idx].act(vehicle.sinr_db)
            # Apply phases to the panel (simulated in simulator)
            return {'type': 'RIS', 'idx': nearest_ris_idx, 'phases': phases}
        
        # 2. HO Action
        if self.ho_agent.act(vehicle.connected_gnb, vehicle.sinr_db, target_gnb_sinr):
            return {'type': 'HO', 'target': 'best'}
            
        # 3. RA Action
        boost = self.ra_agent.act(vehicle.sinr_db)
        return {'type': 'RA', 'boost': boost}
