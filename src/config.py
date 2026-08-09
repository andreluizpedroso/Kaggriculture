"""Central economy table and tunable constants for the Kaggriculture agent.

Numbers here are copied from the installed kaggle_environments engine
(`kaggle_environments/envs/kaggriculture/kaggriculture.py` and its README),
not guessed — see PROGRESS.md for the spike that confirmed them. Anything
marked "estimate" below is genuinely a guess (community analysis, not
verified against the engine) and is expected to be retuned from
`simulate.py` results.
"""

# --- Crops -------------------------------------------------------------
# first_yield_day / max_yield_day / interval are in days-since-planted.
# interval == 0 means one-time harvest; interval > 0 means "ongoing" crop
# that produces every `interval` days after first_yield_day, up to
# `max_yield` total scheduled productions.
CROPS = {
    "WHEAT":      {"seed_cost": 10,  "base_price": 25,  "first_yield_day": 2,  "max_yield_day": 4,  "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed_cost": 20,  "base_price": 35,  "first_yield_day": 2,  "max_yield_day": 3,  "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed_cost": 50,  "base_price": 60,  "first_yield_day": 8,  "max_yield_day": 8,  "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed_cost": 100, "base_price": 120, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed_cost": 80,  "base_price": 250, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

# --- Animals -------------------------------------------------------------
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "product": "EGG",  "base_price": 50,  "first_yield_day": 4, "interval": 1, "max_held": 4},
    "COW":   {"cost": 400, "structure": "PASTURE", "product": "MILK", "base_price": 160, "first_yield_day": 8, "interval": 2, "max_held": 6},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "product": "WOOL", "base_price": 200, "first_yield_day": 6, "interval": 3, "max_held": 6},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

# --- Land ---------------------------------------------------------------
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = {"NE": 1000, "SW": 2000, "SE": 4000}

# --- Season / phase route -------------------------------------------------
# `obs["day"]` is 0-indexed (0..29). Boundaries are the first day of each
# phase. Tuned against the user's 1-indexed "Bootstrap dias 1-3" etc.
TURNS_PER_DAY = 24
SEASON_DAYS = 30
PHASE_BOUNDARIES = [
    ("BOOTSTRAP", 0),          # days 0-2   (1-3 in-game)
    ("EXPAND", 3),             # days 3-11  (4-12)
    ("ROTATE_AND_COMPOUND", 12),  # days 12-23 (13-24)
    ("PROTECT_VALUE", 24),     # days 24-27 (25-28)
    ("CASH", 28),              # days 28-29 (29-30)
]


def get_phase(day: int) -> str:
    """Return the season-route phase name for a given 0-indexed `obs["day"]`."""
    phase = PHASE_BOUNDARIES[0][0]
    for name, start_day in PHASE_BOUNDARIES:
        if day >= start_day:
            phase = name
        else:
            break
    return phase


# --- Tunable constants (estimates — revisit via simulate.py) -------------
# Community analysis claims CARE can multiply animal yield by ~4x; unverified
# against the current (post-balance-change) engine. CARE is always applied
# when available regardless of this constant (it only affects which animal
# to buy), so a wrong value here is low-risk to correct later.
CARE_MULTIPLIER = 4.0

# Assumed per-unit price decay when selling several units of the same
# product in a short window, used only for score projections (not a real
# market simulation — the real price function lives in the engine and is
# read live from obs["market"]["prices"] every phase-planning cycle).
PRICE_IMPACT_PCT = 0.06

# No single crop should claim more than this share of currently-empty
# tiles when planning a phase's planting targets, so the agent doesn't
# crash its own price late-game (more likely post-balance-change).
MAX_SINGLE_CROP_SHARE = 0.6

# Clone-preemption: how similar (0..1) self vs. opponent public farm state
# has to be before we treat the opponent as running the same "recipe" and
# preempt a planned sale by a few turns.
CLONE_SIMILARITY_THRESHOLD = 0.85
CLONE_PREEMPT_TURNS = 2

MAX_MARKET_ORDERS_PER_TURN = 10

# Cap total animals owned (placed + sitting in shed) so the agent doesn't
# buy more mouths to feed than its current labor/cash can sustain -- an
# unfed animal that flees after 2 days is a pure loss of its purchase cost.
MAX_ANIMALS = 3

# Keep this many seeds of the current target crop in stock at once. Buying
# only 1 at a time throttled planting to roughly one new plant per
# purchase-notice-walk-plant cycle, which couldn't keep up once land grew
# to 100 tiles -- most of the farm sat empty for lack of seed backlog.
# Scales with how many quadrants are unlocked (more land -> more units
# working it -> need a bigger backlog so nobody stalls waiting on seed).
# CASH_RESERVE below still stops this from starving hiring/wheat/land.
SEED_BUFFER_PER_QUADRANT = 6

# Never let an opportunistic purchase (seed top-up, land, a new animal --
# anything that isn't survival-critical wheat) drop the bank below this,
# so a run of bad luck doesn't leave the agent unable to react.
CASH_RESERVE = 150
