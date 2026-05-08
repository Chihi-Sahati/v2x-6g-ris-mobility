#!/usr/bin/env python3
"""
V2X 6G RIS Mobility Management — Evaluation Runner
====================================================
Version: 2.1 — No patches needed (env is fixed)

Usage:
    python run_evaluation.py                           # defaults
    python run_evaluation.py --steps 500 --seed 123
"""

import sys, os, argparse, csv, numpy as np
from typing import List, Tuple, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))
from code.simulation.v2x_environment import V2XEnvironment, V2XConfig
from code.simulation.channel import ChannelModel

SPEED_RANGES = [80, 120, 160, 200, 250, 300, 350, 400, 450, 500]
DEFAULT_STEPS = 200
DEFAULT_SEED = 42
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'simulations', 'results')


def _make_env(target_speed_kmh, seed=42):
    cfg = V2XConfig()
    env = V2XEnvironment(config=cfg)
    env.mobility.config.min_speed_kmh = target_speed_kmh
    env.mobility.config.max_speed_kmh = target_speed_kmh
    env.mobility.config.mean_speed_kmh = target_speed_kmh
    env.reset(seed=seed)
    _spread_vehicles(env, seed)
    return env


def _spread_vehicles(env, seed):
    rng = np.random.RandomState(seed)
    for v in env.mobility.vehicles:
        v.position[0] = rng.uniform(0, env.mobility.highway_length)
        lane = rng.randint(0, env.mobility.num_lanes)
        v.lane = lane
        v.position[1] = (lane - env.mobility.num_lanes / 2 + 0.5) * env.mobility.lane_width
        speed_ms = env.mobility.config.mean_speed_kmh / 3.6
        v.velocity = np.array([speed_ms, 0.0, 0.0])


def _run_episode(env, num_steps, *, apply_ris_gain=False, ris_seed_offset=0, seed=DEFAULT_SEED):
    rng = np.random.RandomState(seed + ris_seed_offset)
    sinr_samples, latency_samples = [], []
    steps_run = 0
    cum_ho_a, cum_ho_s = 0, 0

    if apply_ris_gain:
        for r in range(env.config.num_ris):
            base = rng.uniform(0, 2 * np.pi)
            env.ris_phases[r] = base + rng.normal(0, 0.3, env.config.num_ris_elements)

    for step_i in range(num_steps):
        ho_before, hs_before = env.handover_attempts, env.handover_successes
        n_veh = len(env.mobility.vehicles)
        action = {'ris': env.ris_action_space.sample()}
        if n_veh > 0:
            action['handover'] = np.random.randint(0, env.config.num_gnbs + 1, n_veh)
            action['resource'] = {
                'rb_allocation': np.ones(n_veh, dtype=int),
                'power_allocation': np.ones(n_veh),
            }
        obs, reward, terminated, truncated, info = env.step(action)
        steps_run += 1
        da = env.handover_attempts - ho_before
        ds = env.handover_successes - hs_before
        if da < 0: da, ds = max(da, 0), max(ds, 0)
        cum_ho_a += da; cum_ho_s += ds
        for v in env.mobility.vehicles:
            sinr_samples.append(v.sinr)
            latency_samples.append(env._compute_estimated_latency_ms(v))
        if terminated or truncated:
            env.reset(seed=seed + step_i + ris_seed_offset + 1)
            _spread_vehicles(env, seed=seed + step_i + ris_seed_offset + 1)
            if apply_ris_gain:
                for r in range(env.config.num_ris):
                    base = rng.uniform(0, 2 * np.pi)
                    env.ris_phases[r] = base + rng.normal(0, 0.3, env.config.num_ris_elements)

    hsr = cum_ho_s / cum_ho_a if cum_ho_a > 0 else 1.0
    return {'sinr_samples': sinr_samples, 'latency_samples': latency_samples,
            'hsr': hsr, 'ho_attempts': cum_ho_a, 'ho_successes': cum_ho_s, 'steps_run': steps_run}


def _compute_avg_throughput(env, data):
    if not data['sinr_samples']: return 0.0
    return float(np.mean([env._sinr_to_rate_mbps(s) for s in data['sinr_samples']]))


def evaluate_sinr_vs_speed(speeds, num_steps, seed):
    print("\n" + "=" * 60 + "\n  Evaluating SINR vs Speed\n" + "=" * 60)
    results = []
    for idx, speed in enumerate(speeds):
        env_no = _make_env(speed, seed)
        r_no = _run_episode(env_no, num_steps, apply_ris_gain=False, seed=seed)
        avg_no = float(np.mean(r_no['sinr_samples'])) if r_no['sinr_samples'] else 0.0
        env_ris = _make_env(speed, seed)
        r_ris = _run_episode(env_ris, num_steps, apply_ris_gain=True, ris_seed_offset=idx, seed=seed)
        avg_ris = float(np.mean(r_ris['sinr_samples'])) if r_ris['sinr_samples'] else 0.0
        print(f"  Speed {speed:>4d} km/h | No RIS: {avg_no:7.2f} dB | RIS: {avg_ris:7.2f} dB | Δ = {avg_ris-avg_no:+.2f} dB")
        results.append((speed, avg_no, avg_ris))
    return results


def evaluate_throughput_vs_speed(speeds, num_steps, seed):
    print("\n" + "=" * 60 + "\n  Evaluating Throughput vs Speed\n" + "=" * 60)
    results = []
    for idx, speed in enumerate(speeds):
        env_no = _make_env(speed, seed)
        r_no = _run_episode(env_no, num_steps, apply_ris_gain=False, seed=seed)
        tp_no = _compute_avg_throughput(env_no, r_no)
        env_ris = _make_env(speed, seed)
        r_ris = _run_episode(env_ris, num_steps, apply_ris_gain=True, ris_seed_offset=idx, seed=seed)
        tp_ris = _compute_avg_throughput(env_ris, r_ris)
        gain = ((tp_ris - tp_no) / tp_no * 100.0) if tp_no > 0 else 0.0
        print(f"  Speed {speed:>4d} km/h | No RIS: {tp_no:8.1f} Mbps | RIS: {tp_ris:8.1f} Mbps | gain={gain:+.1f}%")
        results.append((speed, tp_no, tp_ris))
    return results


def evaluate_latency_cdf(num_steps=1000, seed=42):
    print("\n" + "=" * 60 + f"\n  Evaluating Latency CDF ({num_steps} steps)\n" + "=" * 60)
    env = _make_env(120, seed)
    env.reset(seed=seed)
    all_lat = []
    for si in range(num_steps):
        n_veh = len(env.mobility.vehicles)
        action = {'ris': env.ris_action_space.sample()}
        if n_veh > 0:
            action['handover'] = np.random.randint(0, env.config.num_gnbs + 1, n_veh)
        _, _, term, trunc, _ = env.step(action)
        for v in env.mobility.vehicles:
            all_lat.append(env._compute_estimated_latency_ms(v))
        if term or trunc:
            env.reset(seed=seed + si)
    lats = np.array(all_lat); lats.sort()
    n = len(lats); cdf = np.arange(1, n + 1) / n
    print(f"  Samples: {n}  Mean: {np.mean(lats):.4f} ms  P99: {np.percentile(lats,99):.4f} ms")
    return lats, cdf


def evaluate_hsr_vs_speed(speeds, num_steps, seed):
    print("\n" + "=" * 60 + "\n  Evaluating Handover Success Rate vs Speed\n" + "=" * 60)
    results = []
    for idx, speed in enumerate(speeds):
        env_no = _make_env(speed, seed)
        r_no = _run_episode(env_no, num_steps, apply_ris_gain=False, seed=seed)
        env_ris = _make_env(speed, seed)
        r_ris = _run_episode(env_ris, num_steps, apply_ris_gain=True, ris_seed_offset=idx, seed=seed)
        print(f"  Speed {speed:>4d} km/h | No RIS: {r_no['hsr']:.4f} ({r_no['ho_successes']}/{r_no['ho_attempts']})"
              f"  | RIS: {r_ris['hsr']:.4f} ({r_ris['ho_successes']}/{r_ris['ho_attempts']})")
        results.append((speed, r_no['hsr'], r_ris['hsr']))
    return results


def compare_with_without_ris(num_steps, seed):
    print("\n" + "=" * 70 + "\n  RIS Impact Comparison (120 km/h)\n" + "=" * 70)
    env_no = _make_env(120, seed)
    r_no = _run_episode(env_no, num_steps, apply_ris_gain=False, seed=seed)
    env_ris = _make_env(120, seed)
    r_ris = _run_episode(env_ris, num_steps, apply_ris_gain=True, seed=seed)
    for name, v_no, v_ris, unit, lower in [
        ("Avg SINR", np.mean(r_no['sinr_samples']), np.mean(r_ris['sinr_samples']), "dB", False),
        ("Avg Throughput", _compute_avg_throughput(env_no, r_no), _compute_avg_throughput(env_ris, r_ris), "Mbps", False),
        ("Handover Success Rate", r_no['hsr']*100, r_ris['hsr']*100, "%", False),
        ("Avg Latency", np.mean(r_no['latency_samples']), np.mean(r_ris['latency_samples']), "ms", True)]:
        print(f"  {name:<25} {v_no:>13.2f}{unit:<2} {v_ris:>13.2f}{unit:<2} {'↓' if (v_ris-v_no)<0 == lower else '↑'}{abs(v_ris-v_no):.2f}{unit}")
    print()


def save_sinr_csv(results, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['speed_kmh','sinr_db','with_ris_sinr_db'])
        for s, sn, sr in results: w.writerow([s, round(sn,2), round(sr,2)])
    print(f"\n  ✓ Saved {path}  ({len(results)} rows)")


def save_throughput_csv(results, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['speed_kmh','throughput_mbps','with_ris_throughput_mbps'])
        for s, tn, tr in results: w.writerow([s, round(tn,2), round(tr,2)])
    print(f"  ✓ Saved {path}  ({len(results)} rows)")


def save_latency_csv(lats, cdf, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = len(lats)
    if n > 500:
        idx = np.linspace(0, n-1, 500, dtype=int); lats = lats[idx]; cdf = cdf[idx]
    with open(path, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['latency_ms','cdf_probability'])
        for la, pr in zip(lats, cdf): w.writerow([round(la,6), round(pr,6)])
    print(f"  ✓ Saved {path}  ({len(lats)} rows)")


def save_hsr_csv(results, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['speed_kmh','hsr','with_ris_hsr'])
        for s, hn, hr in results: w.writerow([s, round(hn,4), round(hr,4)])
    print(f"  ✓ Saved {path}  ({len(results)} rows)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR)
    p.add_argument('--steps', type=int, default=DEFAULT_STEPS)
    p.add_argument('--seed', type=int, default=DEFAULT_SEED)
    args = p.parse_args()

    print("=" * 60 + f"\n  V2X 6G RIS — Evaluation  (v2.1, env is fixed, no patches)\n"
          f"  steps={args.steps}  seed={args.seed}  speeds={SPEED_RANGES}\n" + "=" * 60)

    sinr = evaluate_sinr_vs_speed(SPEED_RANGES, args.steps, args.seed)
    tp = evaluate_throughput_vs_speed(SPEED_RANGES, args.steps, args.seed)
    lats, cdf = evaluate_latency_cdf(min(args.steps * 5, 1000), args.seed)
    hsr = evaluate_hsr_vs_speed(SPEED_RANGES, args.steps, args.seed)
    compare_with_without_ris(args.steps, args.seed)

    print("\n" + "=" * 60 + "\n  Saving results\n" + "=" * 60)
    od = args.output_dir
    save_sinr_csv(sinr, os.path.join(od, 'sinr_results.csv'))
    save_throughput_csv(tp, os.path.join(od, 'throughput_results.csv'))
    save_latency_csv(lats, cdf, os.path.join(od, 'latency_results.csv'))
    save_hsr_csv(hsr, os.path.join(od, 'hsr_results.csv'))

    print(f"\n  All results saved to: {od}/\n" + "=" * 60)


if __name__ == '__main__':
    main()
