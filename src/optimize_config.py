"""Offline hyperparameter search for the tunable constants in src/config.py.

Runs entirely at development time -- no ~1s/turn budget applies here, only
to the agent's actual per-turn decision, which stays exactly the same cheap
heuristic logic; only the config constants it reads change. Uses
src/simulate.py-style matches against a mix of weak (random, starter) and
strong (tetsutani, boatlee -- see reference_agents/, gitignored) opponents
as the fitness signal: random search to find a promising region, then
coordinate-wise hill-climbing to refine it. Not sophisticated by design --
good enough to beat hand-picked constants, not a real optimizer.

Reuses the existing agent/reactive layers untouched: this only searches
over the config *values* those layers already read (cfg.SEED_BUFFER_PER_QUADRANT,
cfg.CASH_RESERVE, ..., cfg.PHASE_BOUNDARIES), by mutating the shared
`src.config` module object in place before each match. `agent()` re-reads
`cfg.X` fresh every call, so no code changes to agent.py were needed beyond
the round-1 refactor that named these constants.
"""

import importlib.util
import random

from kaggle_environments import make

from . import config as cfg
from .agent import agent as agent_fn

PARAM_SPACE = {
    "SEED_BUFFER_PER_QUADRANT": ("int", 2, 16),
    "CASH_RESERVE": ("int", 0, 500),
    "MAX_ANIMALS": ("int", 1, 8),
    "CARE_MULTIPLIER": ("float", 1.0, 6.0),
    "MAX_SELL_PRICE_IMPACT_FRAC": ("float", 0.05, 0.6),
    "CLONE_SIMILARITY_THRESHOLD": ("float", 0.5, 0.99),
    "HIRE_PER_QUADRANT": ("float", 1.0, 4.0),
    "LAND_AFFORD_MULTIPLIER": ("float", 1.2, 4.0),
    "ANIMAL_AFFORD_MULTIPLIER": ("float", 1.5, 5.0),
    "WHEAT_BUFFER_DAYS": ("int", 1, 6),
    "PHASE_EXPAND_START": ("int", 1, 8),
    "PHASE_ROTATE_START": ("int", 6, 18),
    "PHASE_PROTECT_START": ("int", 16, 27),
    "PHASE_CASH_START": ("int", 25, 29),
}

DEFAULT_PARAMS = {
    "SEED_BUFFER_PER_QUADRANT": 6,
    "CASH_RESERVE": 150,
    "MAX_ANIMALS": 3,
    "CARE_MULTIPLIER": 4.0,
    "MAX_SELL_PRICE_IMPACT_FRAC": 0.15,
    "CLONE_SIMILARITY_THRESHOLD": 0.85,
    "HIRE_PER_QUADRANT": 2.0,
    "LAND_AFFORD_MULTIPLIER": 2.0,
    "ANIMAL_AFFORD_MULTIPLIER": 3.0,
    "WHEAT_BUFFER_DAYS": 3,
    "PHASE_EXPAND_START": 3,
    "PHASE_ROTATE_START": 12,
    "PHASE_PROTECT_START": 24,
    "PHASE_CASH_START": 28,
}

# Weighted toward the strong references -- that's the actual goal; random/
# starter stay in the mix only as a regression guard (see REGRESSION_PENALTY).
FITNESS_WEIGHTS = {
    "random": 0.15,
    "starter": 0.15,
    "tetsutani": 0.35,
    "boatlee": 0.35,
}
REGRESSION_PENALTY = 1_000_000

REFERENCE_AGENT_PATHS = {
    "tetsutani": "reference_agents/tetsutani/main.py",
    "boatlee": "reference_agents/boatlee/main.py",
}


def load_reference_agent(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def apply_params(params):
    cfg.SEED_BUFFER_PER_QUADRANT = params["SEED_BUFFER_PER_QUADRANT"]
    cfg.CASH_RESERVE = params["CASH_RESERVE"]
    cfg.MAX_ANIMALS = params["MAX_ANIMALS"]
    cfg.CARE_MULTIPLIER = params["CARE_MULTIPLIER"]
    cfg.MAX_SELL_PRICE_IMPACT_FRAC = params["MAX_SELL_PRICE_IMPACT_FRAC"]
    cfg.CLONE_SIMILARITY_THRESHOLD = params["CLONE_SIMILARITY_THRESHOLD"]
    cfg.HIRE_PER_QUADRANT = params["HIRE_PER_QUADRANT"]
    cfg.LAND_AFFORD_MULTIPLIER = params["LAND_AFFORD_MULTIPLIER"]
    cfg.ANIMAL_AFFORD_MULTIPLIER = params["ANIMAL_AFFORD_MULTIPLIER"]
    cfg.WHEAT_BUFFER_DAYS = params["WHEAT_BUFFER_DAYS"]

    days = sorted([
        params["PHASE_EXPAND_START"],
        params["PHASE_ROTATE_START"],
        params["PHASE_PROTECT_START"],
        params["PHASE_CASH_START"],
    ])
    days = [max(1, min(29, d)) for d in days]
    for i in range(1, len(days)):
        if days[i] <= days[i - 1]:
            days[i] = min(29, days[i - 1] + 1)
    cfg.PHASE_BOUNDARIES = [
        ("BOOTSTRAP", 0),
        ("EXPAND", days[0]),
        ("ROTATE_AND_COMPOUND", days[1]),
        ("PROTECT_VALUE", days[2]),
        ("CASH", days[3]),
    ]


def sample_random(rng):
    params = {}
    for name, (kind, lo, hi) in PARAM_SPACE.items():
        params[name] = rng.randint(lo, hi) if kind == "int" else rng.uniform(lo, hi)
    return params


def run_match(opponent, seed):
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed})
    env.run([agent_fn, opponent])
    final = env.steps[-1]
    return final[0].reward, final[1].reward


def evaluate(params, seeds, reference_agents):
    apply_params(params)
    deltas = {name: [] for name in FITNESS_WEIGHTS}
    regression = False
    for seed in seeds:
        for name in ("random", "starter"):
            self_r, opp_r = run_match(name, seed)
            deltas[name].append(self_r - opp_r)
            if self_r <= opp_r:
                regression = True
        for name, fn in reference_agents.items():
            self_r, opp_r = run_match(fn, seed)
            deltas[name].append(self_r - opp_r)
    avg = {name: sum(v) / len(v) for name, v in deltas.items()}
    score = sum(FITNESS_WEIGHTS[name] * avg[name] for name in FITNESS_WEIGHTS)
    if regression:
        score -= REGRESSION_PENALTY
    return score, avg


def random_search(n_candidates, seeds, reference_agents, rng):
    results = []
    for i in range(n_candidates):
        params = sample_random(rng)
        score, avg = evaluate(params, seeds, reference_agents)
        results.append((score, params, avg))
        rounded = {k: round(v) for k, v in avg.items()}
        print(f"[random {i + 1}/{n_candidates}] score={score:,.0f} avg={rounded}")
    results.sort(key=lambda r: -r[0])
    return results


def hill_climb(start_params, seeds, reference_agents, rng, steps):
    current_params = dict(start_params)
    current_score, current_avg = evaluate(current_params, seeds, reference_agents)
    names = list(PARAM_SPACE)
    for step in range(steps):
        name = rng.choice(names)
        kind, lo, hi = PARAM_SPACE[name]
        candidate = dict(current_params)
        if kind == "int":
            span = max(1, (hi - lo) // 6)
            candidate[name] = max(lo, min(hi, candidate[name] + rng.randint(-span, span)))
        else:
            span = (hi - lo) / 6
            candidate[name] = max(lo, min(hi, candidate[name] + rng.uniform(-span, span)))
        score, avg = evaluate(candidate, seeds, reference_agents)
        if score > current_score:
            current_params, current_score, current_avg = candidate, score, avg
            print(f"  step {step + 1}: improved ({name} -> {candidate[name]:.3g}), score={score:,.0f}")
    return current_params, current_score, current_avg


def main():
    rng = random.Random(42)
    reference_agents = {
        name: load_reference_agent(path, f"opt_{name}")
        for name, path in REFERENCE_AGENT_PATHS.items()
    }
    # A full match (720 turns, both sides) runs ~4.5s wall-clock -- much
    # slower than our own agent's think-time alone (the reference agents'
    # decode/replay-lookup and engine overhead dominate). Budget sized
    # accordingly: ~96 + ~128 + ~16 = 240 matches, ~18 minutes total.
    search_seeds = [1, 2]

    print("=== baseline (current config.py defaults) ===")
    baseline_score, baseline_avg = evaluate(DEFAULT_PARAMS, search_seeds, reference_agents)
    print(f"score={baseline_score:,.0f} avg={ {k: round(v) for k, v in baseline_avg.items()} }\n")

    print("=== random search (12 candidates, 2 seeds) ===")
    results = random_search(12, search_seeds, reference_agents, rng)

    print("\n=== hill-climbing top 2 candidates (8 steps each) ===")
    refined = []
    for rank, (score, params, avg) in enumerate(results[:2], start=1):
        print(f"-- refining candidate #{rank} (start score={score:,.0f}) --")
        best_params, best_score, best_avg = hill_climb(params, search_seeds, reference_agents, rng, steps=8)
        refined.append((best_score, best_params, best_avg))
    refined.sort(key=lambda r: -r[0])
    best_score, best_params, best_avg = refined[0]

    print("\n=== final validation (4 seeds) ===")
    final_seeds = [1, 2, 3, 4]
    final_score, final_avg = evaluate(best_params, final_seeds, reference_agents)
    print(f"score={final_score:,.0f}")
    print("avg deltas:", {k: round(v) for k, v in final_avg.items()})
    print("\nwinning params:")
    for k, v in best_params.items():
        print(f"  {k} = {v!r}")

    print(f"\nbaseline avg deltas: { {k: round(v) for k, v in baseline_avg.items()} }")
    print(f"winning avg deltas:  { {k: round(v) for k, v in final_avg.items()} }")


if __name__ == "__main__":
    main()
