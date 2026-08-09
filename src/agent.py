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

from . import config as cfg

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

def _price_impact_discount(n_units):
    """Cheap heuristic: each extra unit sold in the same batch is worth less."""
    return sum((1 - cfg.PRICE_IMPACT_PCT) ** i for i in range(n_units))


def score_crop(crop, prices):
    info = cfg.CROPS[crop]
    price = prices.get(crop, info["base_price"])
    if not info["ongoing"]:
        gross = price * _price_impact_discount(info["max_yield"]) / max(info["max_yield"], 1)
        gross *= info["max_yield"]
        profit = gross - info["seed_cost"]
        return profit / max(info["max_yield_day"], 1)
    n_harvests = info["max_yield"]
    total_span = info["first_yield_day"] + (n_harvests - 1) * info["interval"]
    gross = price * _price_impact_discount(n_harvests)
    profit = gross - info["seed_cost"]
    return profit / max(total_span, 1)


def score_animal(animal, prices):
    info = cfg.ANIMALS[animal]
    price = prices.get(info["product"], info["base_price"])
    feed_cost_per_cycle = prices.get("WHEAT", cfg.CROPS["WHEAT"]["base_price"])
    production_value = price * cfg.CARE_MULTIPLIER
    profit = production_value - feed_cost_per_cycle
    return profit / max(info["interval"], 1)


def rank_crops(prices):
    return sorted(cfg.CROPS, key=lambda c: score_crop(c, prices), reverse=True)


def rank_animals(prices):
    return sorted(cfg.ANIMALS, key=lambda a: score_animal(a, prices), reverse=True)


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
    return similarity >= cfg.CLONE_SIMILARITY_THRESHOLD and money_ratio >= cfg.CLONE_SIMILARITY_THRESHOLD


def build_sell_orders(shed, prices, phase, clone_like):
    """Sells ordered by current price (best first). Holds premium goods off
    the market when their price has crashed, unless we're liquidating (Cash
    phase) or racing a clone (clone_like)."""
    premium = {"STRAWBERRY", "MELON", "MILK", "WOOL"}
    items = [(item, qty) for item, qty in shed.items() if qty > 0 and item in cfg.PRODUCTS]
    items.sort(key=lambda kv: prices.get(kv[0], 0), reverse=True)
    orders = []
    for item, qty in items:
        base = cfg.CROPS.get(item, {}).get("base_price") or next(
            (a["base_price"] for a in cfg.ANIMALS.values() if a["product"] == item), None
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
        orders.append(["SELL", item, qty])
    return orders


def build_buy_orders(me, shed, seeds, phase, prices, target_crop, target_animal, market_orders_used):
    buys = []
    money = me.get("money", 0)
    budget_left = money

    num_animals = sum(
        1 for row in me.get("tiles", []) for tile in row
        if isinstance(tile, dict) and tile.get("animal")
    )
    if num_animals > 0:
        wheat_price = prices.get("WHEAT", cfg.CROPS["WHEAT"]["base_price"])
        # Keep a feed buffer per animal; top up the shortfall only.
        wheat_buffer_target = num_animals * cfg.WHEAT_BUFFER_DAYS
        wheat_shortfall = max(0, wheat_buffer_target - shed.get("WHEAT", 0))
        cost = wheat_shortfall * wheat_price
        if wheat_shortfall > 0 and cost <= budget_left:
            buys.append(["BUY_PRODUCT", "WHEAT", wheat_shortfall])
            budget_left -= cost

    if phase != "CASH" and target_crop:
        seed_cost = cfg.CROPS[target_crop]["seed_cost"]
        num_quadrants = len(me.get("unlocked_quadrants", ["NW"]))
        seed_buffer = cfg.SEED_BUFFER_PER_QUADRANT * num_quadrants
        shortfall = max(0, seed_buffer - seeds.get(target_crop, 0))
        spendable = max(0, budget_left - cfg.CASH_RESERVE)
        affordable = min(shortfall, int(spendable // seed_cost)) if seed_cost > 0 else 0
        if affordable > 0:
            buys.append(["BUY_SEED", target_crop, affordable])
            budget_left -= affordable * seed_cost

    if phase in ("ROTATE_AND_COMPOUND", "EXPAND") and target_animal:
        # Buy one at a time, but keep buying across the game as each one
        # gets placed -- only skip while one of this type is still sitting
        # unplaced in the shed (don't stack faster than a unit can fetch
        # and place them), and total owned (placed + shed) stays under
        # MAX_ANIMALS so we don't buy more mouths than we can feed.
        unplaced_in_shed = shed.get(target_animal, 0)
        total_owned = sum(shed.get(a, 0) for a in cfg.ANIMALS) + sum(
            1 for row in me.get("tiles", []) for tile in row
            if isinstance(tile, dict) and tile.get("animal")
        )
        animal_cost = cfg.ANIMALS[target_animal]["cost"]
        if (
            unplaced_in_shed == 0
            and total_owned < cfg.MAX_ANIMALS
            and animal_cost <= budget_left
            and money > animal_cost * cfg.ANIMAL_AFFORD_MULTIPLIER
        ):
            buys.append(["BUY_ANIMAL", target_animal, 1])
            budget_left -= animal_cost

    # Land is valuable whenever we can afford it, not just during EXPAND --
    # BOOTSTRAP rarely has the cash, but ROTATE_AND_COMPOUND income was
    # previously never spent on land once EXPAND's day window closed, which
    # stranded the agent on 2 quadrants for the rest of the season.
    if phase in ("EXPAND", "ROTATE_AND_COMPOUND"):
        unlocked = set(me.get("unlocked_quadrants", []))
        for quadrant in cfg.LAND_ORDER:
            if quadrant in unlocked:
                continue
            price = cfg.LAND_PRICES[quadrant]
            if price <= budget_left and money > price * cfg.LAND_AFFORD_MULTIPLIER:
                buys.append(["BUY_LAND"])
                budget_left -= price
            break

    if phase in ("BOOTSTRAP", "EXPAND", "ROTATE_AND_COMPOUND"):
        hires_today = me.get("hires_today", 0)
        # Scale labor with land -- buying more quadrants without more hands
        # to work them just leaves most of the farm empty and neglected.
        num_quadrants = len(me.get("unlocked_quadrants", ["NW"]))
        max_hires = max(1, int(num_quadrants * cfg.HIRE_PER_QUADRANT))
        if hires_today < max_hires:
            fib_cost = _fib_hire_cost(hires_today)
            if fib_cost <= budget_left and money > fib_cost * 4:
                buys.append(["HIRE"])
                budget_left -= fib_cost

    room = cfg.MAX_MARKET_ORDERS_PER_TURN - market_orders_used
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
                info = cfg.CROPS[tile["crop"]]
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


def _decide_unit(pos, inv, claimed, tasks, me, seeds, shed, phase, target_crop, target_animal, day):
    x, y = pos

    # 1) Deliver a carried harvest/product to the shed.
    sellable_in_inv = {k: v for k, v in inv.items() if k in cfg.PRODUCTS and v > 0}
    if sellable_in_inv:
        shed_tile = _nearest_shed_tile(pos)
        if tuple(pos) == shed_tile:
            return ["DROP"]
        return [_step_toward(pos, shed_tile)]

    # 2) Deliver a carried animal to its structure.
    for animal, info in cfg.ANIMALS.items():
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
    for animal, info in cfg.ANIMALS.items():
        claim_key = ("ANIMAL", animal)
        if claim_key in claimed:
            continue
        if shed.get(animal, 0) > 0 and _find_free_structure(me, info["structure"]):
            shed_tile = _nearest_shed_tile(pos)
            if tuple(pos) == shed_tile:
                claimed.add(claim_key)
                return ["PICKUP", animal, 1]
            return [_step_toward(pos, shed_tile)]

    # 7) Clear weeds blocking new planting.
    for t in tasks["weed"]:
        if t in claimed:
            continue
        if pos == t:
            claimed.add(t)
            return ["DIG"]
    nearest = _nearest_unclaimed(pos, tasks["weed"], claimed)
    if nearest:
        return [_step_toward(pos, nearest)]

    # 8) Plant on an empty tile with seeds on hand.
    if phase != "CASH" and target_crop and seeds.get(target_crop, 0) > 0:
        for t in tasks["empty"]:
            if t in claimed:
                continue
            if pos == t:
                claimed.add(t)
                return ["PLANT", target_crop]
        nearest = _nearest_unclaimed(pos, tasks["empty"], claimed)
        if nearest:
            return [_step_toward(pos, nearest)]

    # 9) Build a structure for the target animal if none is free.
    if phase in ("ROTATE_AND_COMPOUND", "EXPAND") and target_animal:
        structure_kind = cfg.ANIMALS[target_animal]["structure"]
        if not _find_free_structure(me, structure_kind):
            for t in tasks["empty"]:
                if t in claimed:
                    continue
                if pos == t:
                    claimed.add(t)
                    return ["BUILD_COOP" if structure_kind == "COOP" else "BUILD_PASTURE"]
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
    seeds = private.get("seeds", {})
    shed = private.get("shed", {})
    inventories = private.get("inventories", [{}])

    phase = cfg.get_phase(day)
    clone_like = is_clone_like(me, opp)

    crop_ranking = rank_crops(prices)
    animal_ranking = rank_animals(prices)
    target_crop = crop_ranking[0] if crop_ranking else None
    target_animal = animal_ranking[0] if animal_ranking else None

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
        farmer_pos, farmer_inv, claimed, tasks, me, seeds, shed, phase, target_crop, target_animal, day
    )

    hands_actions = []
    for i, hand_pos in enumerate(me.get("hands", [])):
        hand_inv = inventories[i + 1] if i + 1 < len(inventories) else {}
        hands_actions.append(
            _decide_unit(
                tuple(hand_pos), hand_inv, claimed, tasks, me, seeds, shed, phase, target_crop, target_animal, day
            )
        )

    sells = build_sell_orders(shed, prices, phase, clone_like)
    buys = build_buy_orders(me, shed, seeds, phase, prices, target_crop, target_animal, len(sells))
    market_orders = (sells + buys)[: cfg.MAX_MARKET_ORDERS_PER_TURN]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}
