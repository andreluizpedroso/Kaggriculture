"""Kaggriculture submission -- GENERATED FILE, do not hand-edit.

Built by scripts/build_submission.py from src/config.py + src/agent.py
(merged into one flat file because Kaggle's submission validator
expects a single root-level main.py -- see PROGRESS.md). Edit the
source files in src/ and rerun the build script instead.
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


"""Kaggriculture agent: a 5-phase season route with reactive layers on top.

Backbone: the season is split into phases (Bootstrap -> Expand -> Rotate &
Compound -> Protect Value -> Cash, see config.PHASE_BOUNDARIES) that bias
*what* the agent invests in (hiring pace, land buying, reinvestment vs.
cash-out) without needing a literal pre-baked list of 720 actions -- the
engine already exposes enough per-tile/per-animal state
(`consecutive_unwatered`, `fed_today`, `yield_units`, ...) that a cheap,
stateless-per-turn decision (recomputed fresh from `obs` every call) can
reconstruct "the plan" each turn instead of persisting a plan and repairing
it. This sidesteps a whole class of plan/reality-drift bugs at the cost of
being a policy rather than a literal itinerary; see PROGRESS.md.

On top of the phase-biased policy:
- hard prevention (water/feed) always runs first, every turn, regardless of
  phase -- losing a plant/animal is irreversible and never worth deferring.
- CARE is applied whenever available (the ~4x community multiplier is
  treated as a core mechanic, not optional).
- market orders: SELL is always ordered before BUY in the same turn's list.
- demand-sensitive sell ordering: sells are ordered by current price
  (most profitable now first) rather than shed insertion order.
- clone preemption (best-effort): if the opponent's public farm looks like
  it's running the same recipe as ours, skip any "hold for a better price"
  logic and sell immediately instead of waiting.
"""

_STATE = {"hold": {}}


def _reset_if_new_episode(obs):
    if obs.get("day", 0) == 0 and obs.get("hour", 0) == 0:
        _STATE.clear()
        _STATE["hold"] = {}


def _shed_access_tiles(board_size=10):
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def _is_shed_adjacent(pos, board_size=10):
    return tuple(pos) in set(_shed_access_tiles(board_size))


def _step_toward(pos, target, board_size=10):
    """One greedy Manhattan step from pos toward target. Returns a move op or None if already there."""
    x, y = pos
    tx, ty = target
    dx, dy = tx - x, ty - y
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy):
        return "EAST" if dx > 0 else "WEST"
    return "SOUTH" if dy > 0 else "NORTH"


def _nearest_shed_tile(pos, board_size=10):
    tiles = _shed_access_tiles(board_size)
    x, y = pos
    return min(tiles, key=lambda t: abs(t[0] - x) + abs(t[1] - y))


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
# Batch revenue is projected with the engine's real price formula
# (market_price, copied verbatim from the installed source) instead of
# a flat guessed decay -- the engine processes a multi-unit SELL order one
# unit at a time, each unit nudging inventory (and therefore price) before
# the next is quoted, so simulating that sequence gives an exact answer
# instead of an approximation.

def _projected_batch_revenue(item, market_inventory, n_units):
    """Revenue for selling `n_units` of `item` in one batch, starting from
    `market_inventory`, simulated unit-by-unit exactly like the engine.
    SELL *adds* to market inventory (you're supplying the market), which is
    what pushes the price down as a batch grows -- confirmed against the
    engine's `_commit_unit`. A sale at the $1 floor doesn't add supply
    (matches the engine's `if price > 1: market["inventory"][item] += 1`),
    so the price stays pinned at the floor instead of self-correcting."""
    total = 0
    inv = market_inventory
    for _ in range(max(0, int(n_units))):
        price = market_price(item, inv)
        total += price
        if price > PRICE_FLOOR:
            inv += 1
    return total


def score_crop(crop, prices, inventory=None):
    info = CROPS[crop]
    market_inv = (inventory or {}).get(crop, MARKET_I0)
    if not info["ongoing"]:
        gross = _projected_batch_revenue(crop, market_inv, info["max_yield"])
        profit = gross - info["seed_cost"]
        return profit / max(info["max_yield_day"], 1)
    n_harvests = info["max_yield"]
    total_span = info["first_yield_day"] + (n_harvests - 1) * info["interval"]
    gross = _projected_batch_revenue(crop, market_inv, n_harvests)
    profit = gross - info["seed_cost"]
    return profit / max(total_span, 1)


def score_animal(animal, prices, inventory=None):
    info = ANIMALS[animal]
    market_inv = (inventory or {}).get(info["product"], MARKET_I0)
    price = market_price(info["product"], market_inv) if inventory else prices.get(info["product"], info["base_price"])
    feed_cost_per_cycle = prices.get("WHEAT", CROPS["WHEAT"]["base_price"])
    production_value = price * CARE_MULTIPLIER
    profit = production_value - feed_cost_per_cycle
    return profit / max(info["interval"], 1)


def rank_crops(prices, inventory=None):
    return sorted(CROPS, key=lambda c: score_crop(c, prices, inventory), reverse=True)


def rank_animals(prices, inventory=None):
    return sorted(ANIMALS, key=lambda a: score_animal(a, prices, inventory), reverse=True)


# --------------------------------------------------------------------------
# Market orders: sell-before-buy, demand-sensitive ordering, clone preemption
# --------------------------------------------------------------------------

def is_clone_like(me, opp):
    """Best-effort similarity check between our public farm state and the opponent's."""
    if opp is None:
        return False

    def crop_counts(farm):
        counts = {}
        for row in farm.get("tiles", []):
            for tile in row:
                if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                    counts[tile["crop"]] = counts.get(tile["crop"], 0) + 1
        return counts

    def animal_counts(farm):
        counts = {}
        for row in farm.get("tiles", []):
            for tile in row:
                if isinstance(tile, dict) and tile.get("animal"):
                    counts[tile["animal"]] = counts.get(tile["animal"], 0) + 1
        return counts

    my_crops, opp_crops = crop_counts(me), crop_counts(opp)
    my_animals, opp_animals = animal_counts(me), animal_counts(opp)
    keys = set(my_crops) | set(opp_crops) | set(my_animals) | set(opp_animals)
    if not keys:
        return False
    diffs = 0
    total = 0
    for k in set(my_crops) | set(opp_crops):
        diffs += abs(my_crops.get(k, 0) - opp_crops.get(k, 0))
        total += max(my_crops.get(k, 0), opp_crops.get(k, 0))
    for k in set(my_animals) | set(opp_animals):
        diffs += abs(my_animals.get(k, 0) - opp_animals.get(k, 0))
        total += max(my_animals.get(k, 0), opp_animals.get(k, 0))
    if total == 0:
        return False
    similarity = 1 - (diffs / (2 * total))
    money_ratio = min(me.get("money", 1), opp.get("money", 1)) / max(me.get("money", 1), opp.get("money", 1), 1)
    return similarity >= CLONE_SIMILARITY_THRESHOLD and money_ratio >= CLONE_SIMILARITY_THRESHOLD


def _max_batch_within_impact(item, market_inventory, available_qty):
    """How many units of `item` can be sold in one order, starting from
    `market_inventory`, before the price would drop below
    MAX_SELL_PRICE_IMPACT_FRAC of the pre-sale spot price -- simulated
    unit-by-unit with the real formula, same idea as
    _projected_batch_revenue above."""
    if available_qty <= 0:
        return 0
    spot = market_price(item, market_inventory)
    floor_price = spot * (1 - MAX_SELL_PRICE_IMPACT_FRAC)
    inv = market_inventory
    n = 0
    while n < available_qty:
        price = market_price(item, inv)
        if n > 0 and price < floor_price:
            break
        n += 1
        if price > PRICE_FLOOR:
            inv += 1
    return n


def build_sell_orders(shed, prices, phase, clone_like, inventory=None):
    """Sells ordered by current price (best first). Holds premium goods off
    the market entirely when their price has already crashed hard, unless
    we're liquidating (Cash phase) or racing a clone (clone_like).
    Otherwise caps each item's batch size (via the real price formula, see
    _max_batch_within_impact) so a single turn's sale doesn't crash its own
    price more than MAX_SELL_PRICE_IMPACT_FRAC -- the held-back remainder
    just carries over to a later turn's SELL order."""
    premium = {"STRAWBERRY", "MELON", "MILK", "WOOL"}
    items = [(item, qty) for item, qty in shed.items() if qty > 0 and item in PRODUCTS]
    items.sort(key=lambda kv: prices.get(kv[0], 0), reverse=True)
    orders = []
    for item, qty in items:
        base = CROPS.get(item, {}).get("base_price") or next(
            (a["base_price"] for a in ANIMALS.values() if a["product"] == item), None
        )
        price = prices.get(item, base or 1)
        should_hold = (
            phase in ("PROTECT_VALUE",)
            and item in premium
            and base
            and price < 0.35 * base
            and not clone_like
        )
        if should_hold:
            continue

        if phase == "CASH" or clone_like or not inventory:
            sell_qty = qty
        else:
            sell_qty = _max_batch_within_impact(item, inventory.get(item, MARKET_I0), qty)
        if sell_qty > 0:
            orders.append(["SELL", item, sell_qty])
    return orders


def _owned_count(animal, me, shed):
    """Total owned of one animal type: placed on the farm + sitting unplaced
    in the shed."""
    placed = sum(
        1 for row in me.get("tiles", []) for tile in row
        if isinstance(tile, dict) and tile.get("animal") == animal
    )
    return placed + shed.get(animal, 0)


def build_buy_orders(me, shed, seeds, phase, prices, target_crops, target_animals, market_orders_used):
    buys = []
    money = me.get("money", 0)
    budget_left = money

    num_animals = sum(
        1 for row in me.get("tiles", []) for tile in row
        if isinstance(tile, dict) and tile.get("animal")
    )
    if num_animals > 0:
        wheat_price = prices.get("WHEAT", CROPS["WHEAT"]["base_price"])
        # Keep a feed buffer per animal; top up the shortfall only.
        wheat_buffer_target = num_animals * WHEAT_BUFFER_DAYS
        wheat_shortfall = max(0, wheat_buffer_target - shed.get("WHEAT", 0))
        cost = wheat_shortfall * wheat_price
        if wheat_shortfall > 0 and cost <= budget_left:
            buys.append(["BUY_PRODUCT", "WHEAT", wheat_shortfall])
            budget_left -= cost

    # Seeds: top up every crop in the portfolio (not just the single best
    # scorer) so planting can rotate across several crops instead of
    # monoculture -- see CROP_PORTFOLIO_SIZE. Spends in score order, each
    # crop respecting the shared CASH_RESERVE floor.
    if phase != "CASH":
        for crop in target_crops:
            seed_cost = CROPS[crop]["seed_cost"]
            num_quadrants = len(me.get("unlocked_quadrants", ["NW"]))
            seed_buffer = SEED_BUFFER_PER_QUADRANT * num_quadrants
            shortfall = max(0, seed_buffer - seeds.get(crop, 0))
            spendable = max(0, budget_left - CASH_RESERVE)
            affordable = min(shortfall, int(spendable // seed_cost)) if seed_cost > 0 else 0
            if affordable > 0:
                buys.append(["BUY_SEED", crop, affordable])
                budget_left -= affordable * seed_cost

    if phase in ("ROTATE_AND_COMPOUND", "EXPAND") and target_animals:
        # Buy one animal per turn, but rotate across the portfolio: fill the
        # best-scored type up to MAX_ANIMALS_PER_TYPE first, then move to
        # the next-best type, instead of capping the whole farm at a single
        # small total (see MAX_ANIMALS_PER_TYPE for why the old shared cap
        # of 3 was the single biggest ceiling on late-game income).
        for animal in target_animals:
            unplaced_in_shed = shed.get(animal, 0)
            total_owned = _owned_count(animal, me, shed)
            animal_cost = ANIMALS[animal]["cost"]
            if (
                unplaced_in_shed == 0
                and total_owned < MAX_ANIMALS_PER_TYPE
                and animal_cost <= budget_left
                and money > animal_cost * ANIMAL_AFFORD_MULTIPLIER
            ):
                buys.append(["BUY_ANIMAL", animal, 1])
                budget_left -= animal_cost
                break

    # Land is valuable whenever we can afford it, not just during EXPAND --
    # BOOTSTRAP rarely has the cash, but ROTATE_AND_COMPOUND income was
    # previously never spent on land once EXPAND's day window closed, which
    # stranded the agent on 2 quadrants for the rest of the season.
    if phase in ("EXPAND", "ROTATE_AND_COMPOUND"):
        unlocked = set(me.get("unlocked_quadrants", []))
        bought_quadrants = len(unlocked - {"NW"})
        if bought_quadrants < MAX_LAND_QUADRANTS:
            for quadrant in LAND_ORDER:
                if quadrant in unlocked:
                    continue
                price = LAND_PRICES[quadrant]
                if price <= budget_left and money > price * LAND_AFFORD_MULTIPLIER:
                    buys.append(["BUY_LAND"])
                    budget_left -= price
                break

    if phase in ("BOOTSTRAP", "EXPAND", "ROTATE_AND_COMPOUND"):
        hires_today = me.get("hires_today", 0)
        # Scale labor with land -- buying more quadrants without more hands
        # to work them just leaves most of the farm empty and neglected.
        num_quadrants = len(me.get("unlocked_quadrants", ["NW"]))
        max_hires = max(1, int(num_quadrants * HIRE_PER_QUADRANT))
        if hires_today < max_hires:
            fib_cost = _fib_hire_cost(hires_today)
            if fib_cost <= budget_left and money > fib_cost * 4:
                buys.append(["HIRE"])
                budget_left -= fib_cost

    room = MAX_MARKET_ORDERS_PER_TURN - market_orders_used
    return buys[:max(room, 0)]


def _fib_hire_cost(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


# --------------------------------------------------------------------------
# Per-turn unit decisions
# --------------------------------------------------------------------------

def _find_watering_targets(me):
    out = []
    for y, row in enumerate(me["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today"):
                out.append((x, y))
    return out


def _find_feeding_targets(me):
    out = []
    for y, row in enumerate(me["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("animal") and not tile.get("fed_today"):
                out.append((x, y))
    return out


def _find_care_targets(me):
    out = []
    for y, row in enumerate(me["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("animal") and not tile.get("cared_today"):
                out.append((x, y))
    return out


def _find_harvest_targets(me, day):
    out = []
    for y, row in enumerate(me["tiles"]):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict):
                continue
            if tile.get("yield_units", 0) <= 0:
                continue
            if tile.get("kind") == "PLANT":
                info = CROPS[tile["crop"]]
                if day - tile["planted_day"] < info["first_yield_day"]:
                    continue
            out.append((x, y))
    return out


def _find_fertilizer_targets(me):
    out = []
    for y, row in enumerate(me["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("animal") and tile.get("fertilizer_available"):
                out.append((x, y))
    return out


def _find_weed_targets(me):
    out = []
    for y, row in enumerate(me["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("kind") == "WEED":
                out.append((x, y))
    return out


def _find_empty_tiles(me):
    out = []
    for y, row in enumerate(me["tiles"]):
        for x, tile in enumerate(row):
            if tile is None:
                out.append((x, y))
    return out


def _resolve_at(pos, target, op_at_target):
    if tuple(pos) == tuple(target):
        return op_at_target
    return [_step_toward(pos, target)]


def _decide_unit(pos, inv, claimed, tasks, me, seeds, shed, phase, target_crops, target_animals, day):
    x, y = pos

    # 1) Deliver a carried harvest/product to the shed.
    sellable_in_inv = {k: v for k, v in inv.items() if k in PRODUCTS and v > 0}
    if sellable_in_inv:
        shed_tile = _nearest_shed_tile(pos)
        if tuple(pos) == shed_tile:
            return ["DROP"]
        return [_step_toward(pos, shed_tile)]

    # 2) Deliver a carried animal to its structure.
    for animal, info in ANIMALS.items():
        if inv.get(animal, 0) > 0:
            structure = _find_free_structure(me, info["structure"])
            if structure:
                if tuple(pos) == structure and pos not in claimed:
                    claimed.add(pos)
                    return ["PLACE", animal]
                return [_step_toward(pos, structure)]

    # 3a) Hard prevention: water (no inventory item consumed, just standing
    # on the tile).
    for t in tasks["water"]:
        if t in claimed:
            continue
        if pos == t:
            claimed.add(t)
            return ["WATER"]
    nearest = _nearest_unclaimed(pos, tasks["water"], claimed)
    if nearest:
        return [_step_toward(pos, nearest)]

    # 3b) Hard prevention: feed. Unlike WATER, FEED consumes WHEAT from the
    # *unit's own inventory* (not the shed) -- a unit with no wheat on hand
    # must fetch some from the shed first, or every FEED silently no-ops
    # and animals starve after 2 missed days regardless of how much wheat
    # sits in storage. (Confirmed against the engine source: BUY_PRODUCT
    # deposits into the shed, and FEED calls `_inv_take(inv, "WHEAT", 1)`
    # on the acting unit's own inventory.)
    if tasks["feed"]:
        if inv.get("WHEAT", 0) > 0:
            for t in tasks["feed"]:
                if t in claimed:
                    continue
                if pos == t:
                    claimed.add(t)
                    return ["FEED"]
            nearest = _nearest_unclaimed(pos, tasks["feed"], claimed)
            if nearest:
                return [_step_toward(pos, nearest)]
        else:
            shed_tile = _nearest_shed_tile(pos)
            if tuple(pos) == shed_tile:
                return ["PICKUP", "WHEAT", len(tasks["feed"])]
            return [_step_toward(pos, shed_tile)]

    # 4) CARE.
    for t in tasks["care"]:
        if t in claimed:
            continue
        if pos == t:
            claimed.add(t)
            return ["CARE"]
    nearest = _nearest_unclaimed(pos, tasks["care"], claimed)
    if nearest:
        return [_step_toward(pos, nearest)]

    # 5) Harvest.
    for t in tasks["harvest"]:
        if t in claimed:
            continue
        if pos == t:
            claimed.add(t)
            return ["HARVEST"]
    nearest = _nearest_unclaimed(pos, tasks["harvest"], claimed)
    if nearest:
        return [_step_toward(pos, nearest)]

    # 6) Collect fertilizer.
    for t in tasks["fertilizer"]:
        if t in claimed:
            continue
        if pos == t:
            claimed.add(t)
            return ["COLLECT_FERTILIZER"]
    nearest = _nearest_unclaimed(pos, tasks["fertilizer"], claimed)
    if nearest:
        return [_step_toward(pos, nearest)]

    # 6b) A purchased animal is waiting in the shed with a free matching
    # structure -- fetch it now. Below survival tasks and harvest/fertilizer
    # (those are irreversible-loss-prevention or produce income right away),
    # but above weeding/planting: money is already spent on it and it earns
    # nothing until placed. `("ANIMAL", name)` keys never collide with the
    # (x, y) tile keys also stored in `claimed`.
    for animal, info in ANIMALS.items():
        claim_key = ("ANIMAL", animal)
        if claim_key in claimed:
            continue
        if shed.get(animal, 0) > 0 and _find_free_structure(me, info["structure"]):
            shed_tile = _nearest_shed_tile(pos)
            if tuple(pos) == shed_tile:
                claimed.add(claim_key)
                return ["PICKUP", animal, 1]
            return [_step_toward(pos, shed_tile)]

    # 7) Build a structure, but *only* when an animal we already paid for is
    # actually sitting unplaced in the shed waiting on one -- money already
    # spent, earning nothing until placed, same rationale as 6b. **Must
    # outrank weeding/planting** (steps 8/9 below) precisely because those
    # always have *some* empty tile to claim as long as any land is
    # unlocked: confirmed via `scripts/diagnose_gap.py` on 2026-09-10 that
    # ranking structure-building after planting means bought animals never
    # get placed (0 COOP/PASTURE built in 30 real turns, every dollar spent
    # on animals wasted) -- longstanding bug, predates today's portfolio
    # rewrite. But the fix must NOT go further and prioritize building
    # structures *speculatively* for animals not yet bought (tried that
    # first: with `MAX_ANIMALS_PER_TYPE` now 13 per type across up to 3
    # portfolio types, "keep building ahead of target" consumes every tile
    # building structures and crop planting starves completely instead --
    # confirmed regression, reverted to this narrower, unplaced-only gate).
    if target_animals:
        needed_kind = None
        for animal in target_animals:
            if shed.get(animal, 0) <= 0:
                continue
            structure_kind = ANIMALS[animal]["structure"]
            if not _find_free_structure(me, structure_kind):
                needed_kind = structure_kind
                break
        if needed_kind:
            for t in tasks["empty"]:
                if t in claimed:
                    continue
                if pos == t:
                    claimed.add(t)
                    return ["BUILD_COOP" if needed_kind == "COOP" else "BUILD_PASTURE"]
            nearest = _nearest_unclaimed(pos, tasks["empty"], claimed)
            if nearest:
                return [_step_toward(pos, nearest)]

    # 8) Clear weeds blocking new planting.
    for t in tasks["weed"]:
        if t in claimed:
            continue
        if pos == t:
            claimed.add(t)
            return ["DIG"]
    nearest = _nearest_unclaimed(pos, tasks["weed"], claimed)
    if nearest:
        return [_step_toward(pos, nearest)]

    # 9) Plant on an empty tile with seeds on hand. Rotates across the crop
    # portfolio by tile position (deterministic, no extra state needed) so
    # the farm doesn't converge to monoculture on a single top-scored crop
    # -- see CROP_PORTFOLIO_SIZE. Falls back to any portfolio crop that
    # still has seeds if the rotated pick has run out.
    if phase != "CASH" and target_crops:
        for t in tasks["empty"]:
            if t in claimed:
                continue
            if pos == t:
                tx, ty = t
                rotated = target_crops[(tx + ty) % len(target_crops)]
                crop = rotated if seeds.get(rotated, 0) > 0 else next(
                    (c for c in target_crops if seeds.get(c, 0) > 0), None
                )
                if crop:
                    claimed.add(t)
                    return ["PLANT", crop]
        nearest = _nearest_unclaimed(pos, tasks["empty"], claimed)
        if nearest:
            return [_step_toward(pos, nearest)]

    return ["PASS"]


def _nearest_unclaimed(pos, candidates, claimed):
    options = [c for c in candidates if c not in claimed]
    if not options:
        return None
    x, y = pos
    return min(options, key=lambda t: abs(t[0] - x) + abs(t[1] - y))


def _find_free_structure(me, kind):
    for y, row in enumerate(me["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("kind") == kind and not tile.get("animal"):
                return (x, y)
    return None


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def agent(obs):
    _reset_if_new_episode(obs)

    player = obs["player"]
    day = obs.get("day", 0)
    farms = obs["farms"]
    me = farms[player]
    opp = farms[1 - player] if len(farms) > 1 else None
    private = obs["private"]
    market = obs["market"]
    prices = market.get("prices", {})
    inventory = market.get("inventory", {})
    seeds = private.get("seeds", {})
    shed = private.get("shed", {})
    inventories = private.get("inventories", [{}])

    phase = get_phase(day)
    clone_like = is_clone_like(me, opp)

    crop_ranking = rank_crops(prices, inventory)
    animal_ranking = rank_animals(prices, inventory)
    # Portfolios, not single picks: rotating across the top-N scored crops
    #/animals avoids dumping the whole farm's production of one item on the
    # market at once (see CROP_PORTFOLIO_SIZE / ANIMAL_PORTFOLIO_SIZE).
    target_crops = crop_ranking[: CROP_PORTFOLIO_SIZE]
    target_animals = animal_ranking[: ANIMAL_PORTFOLIO_SIZE]

    tasks = {
        "water": _find_watering_targets(me),
        "feed": _find_feeding_targets(me),
        "care": _find_care_targets(me),
        "harvest": _find_harvest_targets(me, day),
        "fertilizer": _find_fertilizer_targets(me),
        "weed": _find_weed_targets(me),
        "empty": _find_empty_tiles(me),
    }

    claimed = set()
    farmer_pos = tuple(me["farmer"])
    farmer_inv = inventories[0] if inventories else {}
    farmer_action = _decide_unit(
        farmer_pos, farmer_inv, claimed, tasks, me, seeds, shed, phase, target_crops, target_animals, day
    )

    hands_actions = []
    for i, hand_pos in enumerate(me.get("hands", [])):
        hand_inv = inventories[i + 1] if i + 1 < len(inventories) else {}
        hands_actions.append(
            _decide_unit(
                tuple(hand_pos), hand_inv, claimed, tasks, me, seeds, shed, phase, target_crops, target_animals, day
            )
        )

    sells = build_sell_orders(shed, prices, phase, clone_like, inventory)
    buys = build_buy_orders(me, shed, seeds, phase, prices, target_crops, target_animals, len(sells))
    market_orders = (sells + buys)[: MAX_MARKET_ORDERS_PER_TURN]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}
