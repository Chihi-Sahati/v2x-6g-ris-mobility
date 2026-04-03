#!/usr/bin/env python3
"""
Training Pipeline for V2X 6G RIS Mobility Management
=====================================================

Authors: AlHussein A. Al-Sahati, Houda Chihi
Version: 2.1
Last Updated: 2026-04-04

Usage:
    python train.py --algorithm qmix --episodes 1000
    python train.py --algorithm mappo --episodes 2000 --lr 3e-4
"""

import sys, os, argparse, time, json, csv
from datetime import datetime
from pathlib import Path
import numpy as np
import torch

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _REPO_ROOT)

from code.simulation.v2x_environment import V2XEnvironment, V2XConfig
from code.algorithms.qmix import QMIXNetwork, QMIXTrainer
from code.algorithms.mappo import MAPPOPolicy, MAPPOTrainer
from code.utils.config import SimulationConfig, RLConfig

NUM_AGENTS = 3
NUM_RIS = 3
NUM_RIS_ELEMENTS = 64
TOTAL_RIS_ELEMENTS = NUM_RIS * NUM_RIS_ELEMENTS  # 192
PHASE_LEVELS = 16
NUM_GNBS = 5
HO_ACTION_SIZE = 6
RB_LEVELS = [2, 5, 10, 20, 50]


def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def preprocess_observation(obs: dict, device: torch.device) -> torch.Tensor:
    """
    Build a (1, 3, 6) tensor from the gym observation dict.
    Agent 0 (RIS):      mean position + mean velocity
    Agent 1 (Handover): gNB loads + mean speed
    Agent 2 (Resource): demand signal
    """
    vs = obs['vehicle_states']
    gs = obs['gnb_states']
    nv = obs['num_vehicles'] if isinstance(obs['num_vehicles'], int) else vs.shape[0]
    active = vs[:max(nv, 1)]

    a0 = np.concatenate([active[:, :3].mean(0), active[:, 3:].mean(0)])
    loads = gs[:, 3]
    spd = float(np.linalg.norm(active[:, 3:], axis=1).mean()) if len(active) else 0.0
    a1 = np.array([loads.mean(), loads.std(), spd, spd, spd, spd], dtype=np.float32)
    a2 = np.array([nv / 150.0, loads.mean(), spd, spd, spd, spd], dtype=np.float32)

    return torch.from_numpy(np.stack([a0, a1, a2])).float().unsqueeze(0).to(device)


def actions_to_env_format(agent_actions, num_vehicles, rng=None):
    """
    Agent 0 (RIS):  phase level → ALL 192 elements with ±2 variation
    Agent 1 (HO):   per-vehicle handover target
    Agent 2 (Res):  per-vehicle RB allocation
    """
    base_phase = agent_actions[0] % PHASE_LEVELS
    if rng is not None:
        ris = np.array([(base_phase + rng.randint(-2, 3)) % PHASE_LEVELS
                         for _ in range(TOTAL_RIS_ELEMENTS)], dtype=np.int64)
    else:
        ris = np.full(TOTAL_RIS_ELEMENTS, base_phase, dtype=np.int64)

    base_ho = agent_actions[1] % HO_ACTION_SIZE
    if rng is not None and num_vehicles > 0:
        ho = np.array([(base_ho if rng.random() >= 0.3 else rng.randint(0, HO_ACTION_SIZE))
                         for _ in range(num_vehicles)], dtype=np.int64)
    else:
        ho = np.full(num_vehicles, base_ho, dtype=np.int64)

    rb_idx = agent_actions[2] % len(RB_LEVELS)
    rb_alloc = np.full(num_vehicles, RB_LEVELS[rb_idx], dtype=np.int64)
    pwr_alloc = np.full(num_vehicles, 1.0 / max(RB_LEVELS[rb_idx], 1), dtype=np.float64)

    return {'ris': ris, 'handover': ho,
            'resource': {'rb_allocation': rb_alloc, 'power_allocation': pwr_alloc}}


def build_qmix_experience(states, actions, reward, next_states, done, device):
    return {
        'states': states, 'actions': torch.tensor([actions], dtype=torch.long, device=device),
        'rewards': torch.tensor([[reward]], dtype=torch.float32, device=device),
        'next_states': next_states, 'dones': torch.tensor([[float(done)]], dtype=torch.float32, device=device),
    }


@torch.no_grad()
def evaluate(env, network_or_policy, algorithm, device, num_eval_episodes=5):
    rewards, steps, hsrs, sinrs, nvs = [], [], [], [], []
    successes = 0
    for _ in range(num_eval_episodes):
        obs, _ = env.reset()
        total_r, step_c, ss, sc = 0.0, 0, 0.0, 0
        while True:
            s = preprocess_observation(obs, device)
            if algorithm == 'qmix':
                a, _ = network_or_policy.select_action(s, hidden_states=None, explore=False)
            else:
                t, _, _ = network_or_policy.get_actions(s, deterministic=True)
                a = t.squeeze(0).cpu().tolist()
            nv = obs['num_vehicles'] if isinstance(obs['num_vehicles'], int) else len(env.mobility.vehicles)
            ea = actions_to_env_format(a, max(nv, 1))
            obs, r, term, trunc, info = env.step(ea)
            total_r += r; step_c += 1
            for v in env.mobility.vehicles: ss += v.sinr; sc += 1
            if term or trunc: successes += 1; break
        rewards.append(total_r); steps.append(step_c)
        hsrs.append(info.get('handover_success_rate', 0.0))
        sinrs.append(ss / max(sc, 1)); nvs.append(info.get('num_vehicles', 0))
    return {k: float(np.mean(v)) for k, v in
            {'avg_reward': rewards, 'avg_steps': steps, 'avg_hsr': hsrs,
             'avg_sinr': sinrs, 'avg_num_vehicles': nvs}.items()}


def train_qmix(env, trainer, args, device):
    save_dir = Path(args.save_dir) / 'qmix'
    save_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log_dir) / 'qmix'
    log_path.mkdir(parents=True, exist_ok=True)
    csv_file = open(log_path / 'training_log.csv', 'w', newline='')
    csv_writer = csv.DictWriter(csv_file, fieldnames=['episode','step','reward','loss','epsilon','hsr','sinr','num_vehicles','elapsed_s'])
    csv_writer.writeheader()
    best = -float('inf'); hidden = None; start = time.time()

    print(f"\n{'='*60}\n  QMIX Training  |  episodes={args.episodes}  batch={args.batch_size}"
          f"  lr={args.lr}  gamma={args.gamma}  seed={args.seed}\n{'='*60}\n")

    for ep in range(1, args.episodes + 1):
        obs, _ = env.reset(seed=args.seed + ep)
        ep_r, ep_loss, ep_steps, ss_r, ss_c = 0.0, 0.0, 0, 0.0, 0
        hidden = None
        while True:
            s = preprocess_observation(obs, device)
            a, hidden = trainer.select_action(s, hidden_states=hidden, explore=True)
            nv = obs['num_vehicles'] if isinstance(obs['num_vehicles'], int) else len(env.mobility.vehicles)
            ea = actions_to_env_format(a, max(nv, 1))
            nobs, r, term, trunc, info = env.step(ea)
            ep_r += r; ep_steps += 1
            for v in env.mobility.vehicles: ss_r += v.sinr; ss_c += 1
            ns = preprocess_observation(nobs, device)
            done = term or trunc
            trainer.buffer.push(build_qmix_experience(s, a, r, ns, done, device))
            ep_loss += trainer.train_step_fn()
            obs = nobs
            if done: break
        avg_sinr = ss_r / max(ss_c, 1); hsr = info.get('handover_success_rate', 0.0)
        elapsed = time.time() - start
        csv_writer.writerow({'episode': ep, 'step': ep_steps, 'reward': f'{ep_r:.4f}',
            'loss': f'{ep_loss/max(ep_steps,1):.6f}', 'epsilon': f'{trainer.epsilon:.4f}',
            'hsr': f'{hsr:.4f}', 'sinr': f'{avg_sinr:.2f}', 'num_vehicles': info.get('num_vehicles',0),
            'elapsed_s': f'{elapsed:.1f}'}); csv_file.flush()
        if ep % 10 == 0 or ep == 1:
            print(f"  [Ep {ep:>5d}/{args.episodes}]  reward={ep_r:>9.2f}  loss={ep_loss/max(ep_steps,1):.6f}"
                  f"  eps={trainer.epsilon:.3f}  hsr={hsr:.2%}  sinr={avg_sinr:>6.1f}dB  ({elapsed:.0f}s)")
        if ep % args.eval_freq == 0 or ep == args.episodes:
            em = evaluate(env, trainer.network, 'qmix', device)
            print(f"\n  >> Eval @ ep {ep}: avg_reward={em['avg_reward']:.2f}  avg_hsr={em['avg_hsr']:.2%}"
                  f"  avg_sinr={em['avg_sinr']:.1f}dB  avg_steps={em['avg_steps']:.0f}\n")
            ckpt = {'episode': ep, 'model_state_dict': trainer.network.state_dict(),
                    'optimizer_state_dict': trainer.optimizer.state_dict(),
                    'epsilon': trainer.epsilon, 'eval_metrics': em, 'args': vars(args)}
            torch.save(ckpt, save_dir / f'checkpoint_ep{ep}.pt')
            if em['avg_reward'] > best:
                best = em['avg_reward']
                torch.save(ckpt, save_dir / 'best_model.pt')
                print(f"  ** New best model saved (reward={best:.2f})")
    csv_file.close()
    print(f"\nQMIX done. Best eval reward: {best:.2f}")


def train_mappo(env, trainer, args, device):
    save_dir = Path(args.save_dir) / 'mappo'
    save_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log_dir) / 'mappo'
    log_path.mkdir(parents=True, exist_ok=True)
    csv_file = open(log_path / 'training_log.csv', 'w', newline='')
    csv_writer = csv.DictWriter(csv_file, fieldnames=['episode','step','reward','loss','policy_loss',
        'value_loss','entropy','hsr','sinr','num_vehicles','elapsed_s'])
    csv_writer.writeheader()
    best = -float('inf'); rollout_len = getattr(args, 'rollout_len', 256); start = time.time()

    print(f"\n{'='*60}\n  MAPPO Training  |  episodes={args.episodes}  batch={args.batch_size}"
          f"  lr={args.lr}  gamma={args.gamma}  rollout={rollout_len}\n{'='*60}\n")

    for ep in range(1, args.episodes + 1):
        obs, _ = env.reset(seed=args.seed + ep)
        ep_r, ep_steps, ep_loss, tc, ss_r, ss_c = 0.0, 0, {'loss':0,'policy_loss':0,'value_loss':0,'entropy':0}, 0, 0.0, 0
        since_update = 0
        while True:
            s = preprocess_observation(obs, device)
            at, lp, vals = trainer.policy.get_actions(s, deterministic=False)
            a = at.squeeze(0).cpu().tolist(); lp = lp.squeeze(0).cpu(); val = vals.item()
            nv = obs['num_vehicles'] if isinstance(obs['num_vehicles'], int) else len(env.mobility.vehicles)
            ea = actions_to_env_format(a, max(nv, 1))
            nobs, r, term, trunc, info = env.step(ea)
            ep_r += r; ep_steps += 1; since_update += 1
            for v in env.mobility.vehicles: ss_r += v.sinr; ss_c += 1
            done = term or trunc
            trainer.collect_experience(state=s.squeeze(0), action=at.squeeze(0), reward=r, value=val, log_prob=lp, done=done)
            if since_update >= rollout_len or done:
                tr = trainer.train()
                if tr.get('loss', 0.0) != 0.0:
                    for k in ep_loss: ep_loss[k] += tr.get(k, 0.0); tc += 1
                since_update = 0
            obs = nobs
            if done: break
        avg_sinr = ss_r / max(ss_c, 1); hsr = info.get('handover_success_rate', 0.0); elapsed = time.time() - start
        csv_writer.writerow({'episode': ep, 'step': ep_steps, 'reward': f'{ep_r:.4f}',
            'loss': f'{ep_loss["loss"]/max(tc,1):.6f}', 'policy_loss': f'{ep_loss["policy_loss"]/max(tc,1):.4f}',
            'value_loss': f'{ep_loss["value_loss"]/max(tc,1):.4f}', 'entropy': f'{ep_loss["entropy"]/max(tc,1):.4f}',
            'hsr': f'{hsr:.4f}', 'sinr': f'{avg_sinr:.2f}', 'num_vehicles': info.get('num_vehicles',0),
            'elapsed_s': f'{elapsed:.1f}'}); csv_file.flush()
        if ep % 10 == 0 or ep == 1:
            print(f"  [Ep {ep:>5d}/{args.episodes}]  reward={ep_r:>9.2f}  loss={ep_loss['loss']/max(tc,1):.6f}"
                  f"  hsr={hsr:.2%}  sinr={avg_sinr:>6.1f}dB  ({elapsed:.0f}s)")
        if ep % args.eval_freq == 0 or ep == args.episodes:
            em = evaluate(env, trainer.policy, 'mappo', device)
            print(f"\n  >> Eval @ ep {ep}: avg_reward={em['avg_reward']:.2f}  avg_hsr={em['avg_hsr']:.2%}"
                  f"  avg_sinr={em['avg_sinr']:.1f}dB  avg_steps={em['avg_steps']:.0f}\n")
            ckpt = {'episode': ep, 'policy_state_dict': trainer.policy.state_dict(),
                    'actor_optimizer': trainer.actor_optimizer.state_dict(),
                    'critic_optimizer': trainer.critic_optimizer.state_dict(),
                    'eval_metrics': em, 'args': vars(args)}
            torch.save(ckpt, save_dir / f'checkpoint_ep{ep}.pt')
            if em['avg_reward'] > best:
                best = em['avg_reward']
                torch.save(ckpt, save_dir / 'best_model.pt')
                print(f"  ** New best model saved (reward={best:.2f})")
    csv_file.close()
    print(f"\nMAPPO done. Best eval reward: {best:.2f}")


def parse_args():
    p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--algorithm', choices=['qmix','mappo'], default='qmix')
    p.add_argument('--episodes', type=int, default=1000)
    p.add_argument('--eval-freq', type=int, default=100)
    p.add_argument('--batch-size', type=int, default=32)
    p.add_argument('--lr', type=float, default=5e-4)
    p.add_argument('--gamma', type=float, default=0.99)
    p.add_argument('--save-dir', default='./saved_models')
    p.add_argument('--log-dir', default='./logs')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--rollout-len', type=int, default=256)
    p.add_argument('--ppo-epochs', type=int, default=5)
    p.add_argument('--clip-epsilon', type=float, default=0.2)
    p.add_argument('--gae-lambda', type=float, default=0.95)
    p.add_argument('--target-update-freq', type=int, default=200)
    return p.parse_args()


def main():
    args = parse_args(); set_seed(args.seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")

    cfg = V2XConfig()
    env = V2XEnvironment(config=cfg)
    print(f"Environment  |  gNBs={cfg.num_gnbs}  RIS={cfg.num_ris}  "
          f"elements/panel={cfg.num_ris_elements}  total={TOTAL_RIS_ELEMENTS}  "
          f"episode_len={cfg.episode_length}  interference={cfg.interference_model}")

    if args.algorithm == 'qmix':
        net = QMIXNetwork(NUM_AGENTS, 6, PHASE_LEVELS, RLConfig().mixing_embed_dim, RLConfig().hypernet_embed_dim).to(device)
        tr = QMIXTrainer(net, lr=args.lr, gamma=args.gamma, batch_size=args.batch_size, target_update_freq=args.target_update_freq)
        print(f"QMIX network  |  params={sum(p.numel() for p in net.parameters()):,}")
    else:
        pol = MAPPOPolicy(NUM_AGENTS, 6, PHASE_LEVELS).to(device)
        tr = MAPPOTrainer(pol, lr=args.lr, gamma=args.gamma, gae_lambda=args.gae_lambda,
                            clip_epsilon=args.clip_epsilon, ppo_epochs=args.ppo_epochs, mini_batch_size=args.batch_size)
        print(f"MAPPO policy  |  params={sum(p.numel() for p in pol.parameters()):,}")

    cdir = Path(args.save_dir) / args.algorithm; cdir.mkdir(parents=True, exist_ok=True)
    with open(cdir / 'training_config.json', 'w') as f:
        json.dump({'algorithm': args.algorithm, 'episodes': args.episodes, 'batch_size': args.batch_size,
            'lr': args.lr, 'gamma': args.gamma, 'seed': args.seed, 'num_agents': NUM_AGENTS,
            'action_dim': PHASE_LEVELS, 'total_ris_elements': TOTAL_RIS_ELEMENTS,
            'timestamp': datetime.now().isoformat()}, f, indent=2)

    if args.algorithm == 'qmix':
        train_qmix(env, tr, args, device)
    else:
        train_mappo(env, tr, args, device)


if __name__ == '__main__':
    main()
