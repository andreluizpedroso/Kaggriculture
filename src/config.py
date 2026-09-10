"""Central economy table and tunable constants for the Kaggriculture agent.

Numbers here are copied from the installed kaggle_environments engine
(`kaggle_environments/envs/kaggriculture/kaggriculture.py` and its README),
not guessed — see PROGRESS.md for the spike that confirmed them. Anything
marked "estimate" below is genuinely a guess (community analysis, not
verified against the engine) and is expected to be retuned from
`simulate.py` results.
"""

import math

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

# --- Real market price function -----------------------------------------
# Copied verbatim from the installed engine
# (kaggle_environments/envs/kaggriculture/kaggriculture.py::MARKET_PARAMS
# and market_price()), not re-derived from the docs page -- the source is
# the ground truth and was already confirmed to disagree with the public
# competition-download docs.zip on other points (see the ⚠️ note in
# CLAUDE.md). Used by score_crop/score_animal/build_sell_orders to project
# exactly how many units of a product can be sold in a batch before the
# price crashes, instead of a flat guessed decay heuristic.
MARKET_I0 = 10000
PRICE_FLOOR = 1
MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "I0": MARKET_I0, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "I0": MARKET_I0, "T": 450, "below_func": "log",    "below_target": 0.20, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "I0": MARKET_I0, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}


def _shape(func, x):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return x ** 0.5
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    return x


def market_price(item, inventory):
    """Same formula as the engine's market_price(): price(inv) = base +/-
    amp * f(|inv - I0|), floored at PRICE_FLOOR and rounded to the nearest
    dollar."""
    p = MARKET_PARAMS[item]
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        f = p["below_func"]
        amp = p["below_target"] * base / _shape(f, T)
        price = base + amp * _shape(f, I0 - inventory)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / _shape(f, T)
        price = base - amp * _shape(f, inventory - I0)
    return max(PRICE_FLOOR, int(round(price)))

# --- Land ---------------------------------------------------------------
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = {"NE": 1000, "SW": 2000, "SE": 4000}

# Cap on *additional* quadrants bought beyond the free starting NW.
# Verified community meta report (PROGRESS.md, "Pesquisa de meta real")
# found 54% of the 3100+-Elo band deliberately stops at NE+NW+SW and never
# buys SE -- tried capping this at 2 (skip SE) on 2026-09-10 as an
# untested guess (not run through optimize_config.py's search) and it
# measured WORSE against the 3 strong references (-123,627 vs -121,961
# without the cap) -- reverted. Left at len(LAND_ORDER) (no effective
# cap, matches pre-2026-09-10 behavior) until this is actually run through
# the search instead of guessed.
MAX_LAND_QUADRANTS = 3

# --- Season / phase route -------------------------------------------------
# `obs["day"]` is 0-indexed (0..29). Boundaries are the first day of each
# phase. Tuned against the user's 1-indexed "Bootstrap dias 1-3" etc.
TURNS_PER_DAY = 24
SEASON_DAYS = 30
# Tuned by src/optimize_config.py (random search + hill-climbing against
# random/starter/tetsutani/boatlee) -- see PROGRESS.md for the search run
# and the before/after boundary values.
PHASE_BOUNDARIES = [
    ("BOOTSTRAP", 0),
    ("EXPAND", 1),
    ("ROTATE_AND_COMPOUND", 9),
    ("PROTECT_VALUE", 25),
    ("CASH", 25),
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


# --- Tunable constants -------------------------------------------------
# Values below are the winner of the src/optimize_config.py search (random
# search + hill-climbing, fitness = avg bank delta vs random/starter/
# tetsutani/boatlee, weighted toward the strong opponents) -- see
# PROGRESS.md for the search run, the pre-search values, and the
# before/after benchmark numbers. Each constant's original rationale
# (why it exists, what it protects against) is kept below; only the
# numbers changed.

# Community analysis claims CARE can multiply animal yield by ~4x; still
# unverified against the current (post-balance-change) engine, but the
# search independently converged close to that same value. CARE is always
# applied when available regardless of this constant (it only affects
# which animal to buy), so a wrong value here is low-risk to correct later.
CARE_MULTIPLIER = 3.994722922301145

# Max fraction the price of a single item is allowed to drop, within one
# turn's SELL order, before the rest of that item's shed stock is held
# back for a later turn -- computed exactly via market_price() (see
# _max_batch_within_impact in agent.py), not a guessed flat decay anymore.
MAX_SELL_PRICE_IMPACT_FRAC = 0.3187331394159213

# Clone-preemption: how similar (0..1) self vs. opponent public farm state
# has to be before we treat the opponent as running the same "recipe" and
# preempt a planned sale (skip the PROTECT_VALUE hold-for-a-better-price
# logic in build_sell_orders) instead of waiting.
CLONE_SIMILARITY_THRESHOLD = 0.5098490837890597

MAX_MARKET_ORDERS_PER_TURN = 10

# Cap animals owned PER TYPE (placed + sitting in shed) so the agent
# doesn't buy more mouths to feed than its current labor/cash can sustain --
# an unfed animal that flees after 2 days is a pure loss of its purchase
# cost. This used to be a single cap of 3 shared across all animal types
# (i.e. 3 animals total, ever) -- confirmed via benchmark_references.py to
# be the single biggest ceiling on late-game income: animals are the only
# indefinite-duration product in the game, and strong public agents run
# compositions like 8 cow + 6 sheep (14+ animals), not 3. Raised and
# reinterpreted as a per-type cap so the agent can build a real animal
# portfolio instead of stopping at 3 lifetime purchases.
MAX_ANIMALS_PER_TYPE = 13

# How many distinct animal types to actively target/buy at once (ranked by
# score_animal, best first) -- diversifying avoids dumping all production
# of a single product on the market at once and crashing its own price
# (see MAX_SELL_PRICE_IMPACT_FRAC), and mirrors the multi-animal
# compositions strong public agents run.
# TEMPORARILY 0 (animals disabled) as of 2026-09-10 -- see PROGRESS.md
# "Bug de prioridade de estrutura corrigido, mas expõe problema de
# economia animal" for the full story. Short version: fixing the
# structure-building priority bug (animals used to never get placed at
# all, see below) made things WORSE, not better, once animals actually
# started working -- isolated testing confirmed animals are net-NEGATIVE
# value at the current MAX_ANIMALS_PER_TYPE/CARE_MULTIPLIER/etc tuning
# (-137,604 with a conservative cap of 3, vs -125,693 with animals fully
# disabled, vs -128,303 the pre-fix/pre-portfolio baseline). Needs real
# economic re-validation (feed cost vs. CARE_MULTIPLIER vs. opportunity
# cost of hand-turns spent on animal upkeep vs. crops) before turning
# animals back on -- not safe to just re-enable with a guessed cap.
ANIMAL_PORTFOLIO_SIZE = 0

# Same idea for crops: rotate planting across the top-N scored crops
# instead of monoculture on a single top pick, for the same
# market-saturation reason. optimize_config.py's search (2026-09-10,
# post-portfolio-rewrite) converged back to 1 (monoculture) here --
# unlike animals, diversifying crops did NOT help once other constants
# were retuned. Kept at 1 on evidence, not reverted back to the
# hardcoded single-crop design by assumption.
CROP_PORTFOLIO_SIZE = 1

# Keep this many seeds of the current target crop in stock at once, per
# unlocked quadrant. Buying only 1 at a time throttled planting to roughly
# one new plant per purchase-notice-walk-plant cycle, which couldn't keep
# up once land grew to 100 tiles -- most of the farm sat empty for lack of
# seed backlog. CASH_RESERVE below still stops this from starving
# hiring/wheat/land.
SEED_BUFFER_PER_QUADRANT = 8

# Never let an opportunistic purchase (seed top-up, land, a new animal --
# anything that isn't survival-critical wheat) drop the bank below this,
# so a run of bad luck doesn't leave the agent unable to react.
CASH_RESERVE = 463

# How many farm hands to keep hired per unlocked quadrant -- land without
# labor to work it just sits empty and neglected.
HIRE_PER_QUADRANT = 2.088942301542801

# Affordability safety margins: only spend on a non-essential purchase
# (land, an animal) if the bank has at least this many multiples of the
# cost left over afterward, so one purchase doesn't strand the agent.
LAND_AFFORD_MULTIPLIER = 3.864626007706941
ANIMAL_AFFORD_MULTIPLIER = 4.323711816789951

# Feed buffer target, in days of wheat, kept in the shed per animal owned.
WHEAT_BUFFER_DAYS = 2
