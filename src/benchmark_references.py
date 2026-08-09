"""Benchmark our agent against strong public reference agents pulled from
Kaggle (see reference_agents/, gitignored -- local sparring only, never
redistributed). Reuses the run/report plumbing from src/simulate.py, just
swapping the opponent from a built-in name string to a locally-loaded
Python callable.

Note: tetsutani/adaptive-farming-strategy-for-kaggriculture and
romanrozen/strong-barnyard-economist ship byte-identical agent code (same
underlying strategy, different notebook write-up) -- they count as one
distinct opponent, not two, when interpreting results.
"""

import importlib.util
import time

from kaggle_environments import make

from .agent import agent

SEEDS = list(range(1, 16))  # 15 seeds per matchup
TURN_BUDGET_S = 1.0
CUMULATIVE_BUDGET_S = 60.0

REFERENCE_AGENTS = {
    "tetsutani": "reference_agents/tetsutani/main.py",
    "romanrozen": "reference_agents/romanrozen/main.py",
    "boatlee": "reference_agents/boatlee/main.py",
}

_timings = []


def _timed_agent(obs):
    t0 = time.perf_counter()
    result = agent(obs)
    _timings.append(time.perf_counter() - t0)
    return result


def load_reference_agent(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def run_match(opponent_fn, opponent_name, seed):
    global _timings
    _timings = []
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed})
    env.run([_timed_agent, opponent_fn])
    final = env.steps[-1]
    bank_self = final[0].reward
    bank_opp = final[1].reward
    if bank_self > bank_opp:
        winner = "self"
    elif bank_opp > bank_self:
        winner = "opp"
    else:
        winner = "tie"
    max_turn_ms = max(_timings) * 1000 if _timings else 0.0
    cum_ms = sum(_timings) * 1000
    turns_over_budget = sum(1 for t in _timings if t > TURN_BUDGET_S)
    return {
        "opponent": opponent_name,
        "seed": seed,
        "bank_self": bank_self,
        "bank_opp": bank_opp,
        "winner": winner,
        "max_turn_ms": max_turn_ms,
        "turns_over_budget": turns_over_budget,
        "cum_ms": cum_ms,
    }


def print_report(results, opponents):
    header = f"{'opponent':<12} {'seed':<5} {'bank_self':>10} {'bank_opp':>9} {'winner':<6} {'max_ms':>8} {'over_1s':>8} {'cum_ms':>9}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['opponent']:<12} {r['seed']:<5} {r['bank_self']:>10.0f} {r['bank_opp']:>9.0f} "
            f"{r['winner']:<6} {r['max_turn_ms']:>8.1f} {r['turns_over_budget']:>8} {r['cum_ms']:>9.0f}"
        )

    print("\n--- summary ---")
    for opp in opponents:
        opp_results = [r for r in results if r["opponent"] == opp]
        if not opp_results:
            continue
        wins = sum(1 for r in opp_results if r["winner"] == "self")
        ties = sum(1 for r in opp_results if r["winner"] == "tie")
        avg_delta = sum(r["bank_self"] - r["bank_opp"] for r in opp_results) / len(opp_results)
        print(f"vs {opp}: win_rate={wins}/{len(opp_results)} ties={ties} avg_bank_delta={avg_delta:+.0f}")

    worst_turn = max((r["max_turn_ms"] for r in results), default=0.0)
    worst_cum = max((r["cum_ms"] for r in results), default=0.0)
    print(f"\nworst single-turn time (our agent): {worst_turn:.1f} ms (budget: {TURN_BUDGET_S * 1000:.0f} ms)")
    print(f"worst cumulative time (our agent): {worst_cum:.0f} ms (slack budget: {CUMULATIVE_BUDGET_S * 1000:.0f} ms)")


def main():
    loaded = {name: load_reference_agent(path, f"ref_{name}") for name, path in REFERENCE_AGENTS.items()}
    results = []
    for name, fn in loaded.items():
        for seed in SEEDS:
            results.append(run_match(fn, name, seed))
    print_report(results, list(REFERENCE_AGENTS))


if __name__ == "__main__":
    main()
