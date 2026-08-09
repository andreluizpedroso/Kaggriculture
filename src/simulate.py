"""Local test harness: run the agent against the built-in random/starter
bots across several seeds and report bank balances, win/loss, and whether
any turn exceeded the ~1s per-turn budget (with ~60s cumulative slack)."""

import time

from kaggle_environments import make

from .agent import agent

OPPONENTS = ["random", "starter"]
SEEDS = [1, 2, 3, 4, 5]
TURN_BUDGET_S = 1.0
CUMULATIVE_BUDGET_S = 60.0

_timings = []


def _timed_agent(obs):
    t0 = time.perf_counter()
    result = agent(obs)
    _timings.append(time.perf_counter() - t0)
    return result


def run_match(opponent, seed):
    global _timings
    _timings = []
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed})
    env.run([_timed_agent, opponent])
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
        "opponent": opponent,
        "seed": seed,
        "bank_self": bank_self,
        "bank_opp": bank_opp,
        "winner": winner,
        "max_turn_ms": max_turn_ms,
        "turns_over_budget": turns_over_budget,
        "cum_ms": cum_ms,
    }


def print_report(results):
    header = f"{'opponent':<8} {'seed':<5} {'bank_self':>10} {'bank_opp':>9} {'winner':<6} {'max_ms':>8} {'over_1s':>8} {'cum_ms':>9}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['opponent']:<8} {r['seed']:<5} {r['bank_self']:>10.0f} {r['bank_opp']:>9.0f} "
            f"{r['winner']:<6} {r['max_turn_ms']:>8.1f} {r['turns_over_budget']:>8} {r['cum_ms']:>9.0f}"
        )

    print("\n--- summary ---")
    for opp in OPPONENTS:
        opp_results = [r for r in results if r["opponent"] == opp]
        if not opp_results:
            continue
        wins = sum(1 for r in opp_results if r["winner"] == "self")
        avg_delta = sum(r["bank_self"] - r["bank_opp"] for r in opp_results) / len(opp_results)
        print(f"vs {opp}: win_rate={wins}/{len(opp_results)} avg_bank_delta={avg_delta:+.0f}")

    worst_turn = max((r["max_turn_ms"] for r in results), default=0.0)
    worst_cum = max((r["cum_ms"] for r in results), default=0.0)
    print(f"\nworst single-turn time: {worst_turn:.1f} ms (budget: {TURN_BUDGET_S * 1000:.0f} ms)")
    print(f"worst cumulative time: {worst_cum:.0f} ms (slack budget: {CUMULATIVE_BUDGET_S * 1000:.0f} ms)")


def main():
    results = [run_match(opp, seed) for opp in OPPONENTS for seed in SEEDS]
    print_report(results)


if __name__ == "__main__":
    main()
