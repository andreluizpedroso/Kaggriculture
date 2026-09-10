"""One-off diagnostic: run our agent vs. a strong reference (using the
same env.run() pattern as simulate.py/benchmark_references.py, which is
known to produce correct results) and log day-by-day money/hands/land/
animals for both sides from env.steps, to see WHERE the value gap
actually opens up instead of guessing at levers.

Not part of the tuned pipeline -- a throwaway instrumentation script.
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kaggle_environments import make

from src.agent import agent as our_agent


def load_reference_agent(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def snapshot(farm):
    n_hands = len(farm.get("hands", []))
    n_animals = sum(
        1 for row in farm.get("tiles", []) for tile in row
        if isinstance(tile, dict) and tile.get("animal")
    )
    n_planted = sum(
        1 for row in farm.get("tiles", []) for tile in row
        if isinstance(tile, dict) and tile.get("kind") == "PLANT"
    )
    n_quadrants = len(farm.get("unlocked_quadrants", ["NW"]))
    return n_hands, n_animals, n_planted, n_quadrants


def main():
    opponent = load_reference_agent("reference_agents/tetsutani/main.py", "diag_tetsutani")
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": 1})
    env.run([our_agent, opponent])

    print(f"{'day':>4} {'me$':>8} {'opp$':>9} {'me_hnd':>6} {'opp_hnd':>7} {'me_an':>5} {'opp_an':>6} {'me_pl':>5} {'opp_pl':>6} {'me_qd':>5} {'opp_qd':>5}")
    last_day = -1
    for step in env.steps:
        obs = step[0].observation
        day = obs.get("day", 0)
        hour = obs.get("hour", 0)
        if day != last_day and hour == 12:
            last_day = day
            farms = obs["farms"]
            me_money = step[0].reward
            opp_money = step[1].reward
            me_h, me_a, me_p, me_q = snapshot(farms[0])
            opp_h, opp_a, opp_p, opp_q = snapshot(farms[1])
            print(f"{day:>4} {me_money:>8} {opp_money:>9} {me_h:>6} {opp_h:>7} {me_a:>5} {opp_a:>6} {me_p:>5} {opp_p:>6} {me_q:>5} {opp_q:>5}")

    final = env.steps[-1]
    print(f"\nFINAL reward: me={final[0].reward} opp={final[1].reward}")


if __name__ == "__main__":
    main()
