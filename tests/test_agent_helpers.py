"""Narrow tests for src.agent's pure, deterministic helper functions.

Full-game correctness (does the agent actually win) is covered by
src/simulate.py against the real engine, not here -- these tests only
guard the small pieces of logic that are easy to get subtly wrong and
cheap to check without spinning up kaggle_environments.
"""

from src import config as cfg
from src.agent import (
    _max_batch_within_impact,
    _projected_batch_revenue,
    build_buy_orders,
    build_sell_orders,
    is_clone_like,
    score_animal,
    score_crop,
)


def test_market_price_matches_reference_table():
    # Spot-check against the README's Price Function reference table
    # (P(I0-T), P(I0+T), P(I0+2T)) -- confirms our copy of the formula in
    # config.py matches the installed engine's, not just "looks similar".
    assert cfg.market_price("MELON", cfg.MARKET_I0) == 250
    assert cfg.market_price("MELON", cfg.MARKET_I0 - 300) == 300
    assert cfg.market_price("MELON", cfg.MARKET_I0 + 300) == 1
    assert cfg.market_price("WHEAT", cfg.MARKET_I0 - 400) == 45
    assert cfg.market_price("WHEAT", cfg.MARKET_I0 + 400) == 20
    assert cfg.market_price("WHEAT", cfg.MARKET_I0 + 800) == 19


def test_projected_batch_revenue_reflects_falling_price_as_batch_grows():
    # SELL adds to market inventory (confirmed against the engine's
    # _commit_unit), which is what drags the price down as a batch grows.
    # Melon's price curve is quadratic and steep, but flat enough near I0
    # that a tiny batch (a few units) doesn't move the rounded price at
    # all -- use a batch large enough to show real decay.
    single = _projected_batch_revenue("MELON", cfg.MARKET_I0, 1)
    fifty = _projected_batch_revenue("MELON", cfg.MARKET_I0, 50)
    assert fifty < single * 50
    assert fifty > 0


def test_max_batch_within_impact_caps_large_batches():
    # A small batch shouldn't move melon's steep quadratic price curve
    # enough to trip the cap; a large one should.
    assert _max_batch_within_impact("MELON", cfg.MARKET_I0, 5) == 5
    capped = _max_batch_within_impact("MELON", cfg.MARKET_I0, 500)
    assert 0 < capped < 500


def test_score_crop_prefers_higher_price():
    # score_crop projects revenue from real market inventory (via
    # cfg.market_price), not the `prices` spot value directly -- inventory
    # below I0 means scarcity (price above base), above I0 means glut
    # (price below base).
    scarce = {"WHEAT": cfg.MARKET_I0 - 300}
    glutted = {"WHEAT": cfg.MARKET_I0 + 300}
    assert score_crop("WHEAT", {}, scarce) > score_crop("WHEAT", {}, glutted)


def test_score_crop_ranking_shifts_with_price():
    # At I0 (base price) for both, melon (seed 80, base 250) should
    # out-score wheat (seed 10, base 25) on a profit-per-day basis.
    at_i0 = {"WHEAT": cfg.MARKET_I0, "MELON": cfg.MARKET_I0}
    assert score_crop("MELON", {}, at_i0) > score_crop("WHEAT", {}, at_i0)

    # If wheat is scarce (price up) while melon is heavily glutted (price
    # crashed near the floor), wheat should overtake melon -- the score
    # must actually react to real market inventory, not just the static
    # base table.
    skewed = {"WHEAT": cfg.MARKET_I0 - 400, "MELON": cfg.MARKET_I0 + 3000}
    assert score_crop("WHEAT", {}, skewed) > score_crop("MELON", {}, skewed)


def test_score_animal_reacts_to_product_price():
    prices_low = {"EGG": 10, "WHEAT": 25}
    prices_high = {"EGG": 200, "WHEAT": 25}
    assert score_animal("GOOSE", prices_high) > score_animal("GOOSE", prices_low)


def test_build_sell_orders_only_sells_positive_stock():
    shed = {"WHEAT": 5, "CARROT": 0, "EGG": 3}
    prices = {c: info["base_price"] for c, info in cfg.CROPS.items()}
    prices.update({"EGG": 50, "MILK": 160, "WOOL": 200})
    orders = build_sell_orders(shed, prices, phase="ROTATE_AND_COMPOUND", clone_like=False)
    items_sold = {o[1] for o in orders}
    assert "WHEAT" in items_sold
    assert "EGG" in items_sold
    assert "CARROT" not in items_sold
    assert all(o[0] == "SELL" for o in orders)


def test_build_sell_orders_caps_batch_using_real_price_formula():
    shed = {"MELON": 500}
    prices = {"MELON": cfg.CROPS["MELON"]["base_price"]}
    inventory = {"MELON": cfg.MARKET_I0}

    # No inventory given -- falls back to selling everything (old behavior,
    # e.g. for callers/tests that don't track market inventory).
    uncapped = build_sell_orders(shed, prices, phase="ROTATE_AND_COMPOUND", clone_like=False)
    assert uncapped == [["SELL", "MELON", 500]]

    # With inventory given, the batch is capped so this turn's sale alone
    # doesn't crash melon's steep price curve past MAX_SELL_PRICE_IMPACT_FRAC.
    capped = build_sell_orders(shed, prices, phase="ROTATE_AND_COMPOUND", clone_like=False, inventory=inventory)
    assert 0 < capped[0][2] < 500

    # Cash phase liquidates regardless of impact -- unsold stock doesn't count.
    liquidated = build_sell_orders(shed, prices, phase="CASH", clone_like=False, inventory=inventory)
    assert liquidated == [["SELL", "MELON", 500]]


def test_build_sell_orders_holds_crashed_premium_goods_in_protect_value():
    shed = {"MELON": 4}
    prices = {c: info["base_price"] for c, info in cfg.CROPS.items()}
    prices["MELON"] = 1  # crashed to the floor
    held = build_sell_orders(shed, prices, phase="PROTECT_VALUE", clone_like=False)
    assert held == []

    # Cash phase must liquidate regardless -- unsold stock doesn't count.
    liquidated = build_sell_orders(shed, prices, phase="CASH", clone_like=False)
    assert any(o[1] == "MELON" for o in liquidated)

    # Clone preemption also overrides the hold -- race the mirror to market.
    preempted = build_sell_orders(shed, prices, phase="PROTECT_VALUE", clone_like=True)
    assert any(o[1] == "MELON" for o in preempted)


def test_sell_before_buy_ordering_and_cap():
    shed = {p: 3 for p in cfg.PRODUCTS}  # 9 distinct sellable products
    prices = {c: info["base_price"] for c, info in cfg.CROPS.items()}
    prices.update({"EGG": 50, "MILK": 160, "WOOL": 200, "FERTILIZER": 100})
    sells = build_sell_orders(shed, prices, phase="ROTATE_AND_COMPOUND", clone_like=False)

    me = {"money": 5000, "tiles": [[None] * 10 for _ in range(10)], "unlocked_quadrants": ["NW"], "hires_today": 0}
    buys = build_buy_orders(me, {}, {"WHEAT": 0}, "ROTATE_AND_COMPOUND", prices, "WHEAT", "GOOSE", len(sells))

    combined = (sells + buys)[: cfg.MAX_MARKET_ORDERS_PER_TURN]
    assert len(combined) <= cfg.MAX_MARKET_ORDERS_PER_TURN
    sell_positions = [i for i, o in enumerate(combined) if o[0] == "SELL"]
    buy_positions = [i for i, o in enumerate(combined) if o[0] != "SELL"]
    if sell_positions and buy_positions:
        assert max(sell_positions) < min(buy_positions)


def test_buy_wheat_only_tops_up_shortfall_not_flat_amount():
    me = {
        "money": 5000,
        "tiles": [[{"kind": "COOP", "animal": "GOOSE"}] + [None] * 9] + [[None] * 10 for _ in range(9)],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    prices = {"WHEAT": 25}
    # Shed already has more wheat than the buffer target -- must not buy more.
    shed_full = {"WHEAT": 999}
    buys = build_buy_orders(me, shed_full, {}, "ROTATE_AND_COMPOUND", prices, None, None, 0)
    assert not any(o[0] == "BUY_PRODUCT" and o[1] == "WHEAT" for o in buys)

    # Empty shed -- must buy exactly the buffer shortfall (WHEAT_BUFFER_DAYS per animal, 1 animal).
    shed_empty = {"WHEAT": 0}
    buys2 = build_buy_orders(me, shed_empty, {}, "ROTATE_AND_COMPOUND", prices, None, None, 0)
    wheat_orders = [o for o in buys2 if o[0] == "BUY_PRODUCT" and o[1] == "WHEAT"]
    assert len(wheat_orders) == 1
    assert wheat_orders[0][2] == cfg.WHEAT_BUFFER_DAYS


def test_buy_animal_skipped_while_one_sits_unplaced_in_shed():
    me = {"money": 5000, "tiles": [[None] * 10 for _ in range(10)], "unlocked_quadrants": ["NW"], "hires_today": 0}
    prices = {"GOOSE": 300}
    shed_with_goose = {"GOOSE": 1}
    buys = build_buy_orders(me, shed_with_goose, {}, "ROTATE_AND_COMPOUND", prices, None, "GOOSE", 0)
    assert not any(o[0] == "BUY_ANIMAL" for o in buys)

    shed_empty = {}
    buys2 = build_buy_orders(me, shed_empty, {}, "ROTATE_AND_COMPOUND", prices, None, "GOOSE", 0)
    assert any(o[0] == "BUY_ANIMAL" and o[1] == "GOOSE" for o in buys2)


def test_buy_animal_allowed_again_once_previous_one_is_placed():
    # Regression guard: an animal already placed on a tile (not sitting in
    # the shed) must not block buying another of the same type -- this used
    # to cap the whole game at exactly one animal per type forever.
    me = {
        "money": 5000,
        "tiles": [[{"kind": "COOP", "animal": "GOOSE"}] + [None] * 9] + [[None] * 10 for _ in range(9)],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    prices = {"GOOSE": 300}
    buys = build_buy_orders(me, {}, {}, "ROTATE_AND_COMPOUND", prices, None, "GOOSE", 0)
    assert any(o[0] == "BUY_ANIMAL" and o[1] == "GOOSE" for o in buys)


def test_get_phase_boundaries():
    # Reads the boundary days straight from config.PHASE_BOUNDARIES rather
    # than hardcoding them here, so retuning (e.g. via optimize_config.py)
    # doesn't require touching this test.
    boundaries = cfg.PHASE_BOUNDARIES
    for i, (name, start_day) in enumerate(boundaries):
        end_day = boundaries[i + 1][1] - 1 if i + 1 < len(boundaries) else 29
        assert cfg.get_phase(start_day) == name
        if end_day >= start_day:
            assert cfg.get_phase(end_day) == name


def _empty_farm(money=1000):
    return {"money": money, "tiles": [[None] * 10 for _ in range(10)]}


def test_is_clone_like_identical_farms():
    farm = _empty_farm()
    farm["tiles"][0][0] = {"kind": "PLANT", "crop": "WHEAT"}
    farm["tiles"][0][1] = {"kind": "PLANT", "crop": "WHEAT"}
    me = {**farm, "money": 1000}
    opp = {**farm, "money": 1000}
    assert is_clone_like(me, opp) is True


def test_is_clone_like_different_farms():
    me = _empty_farm(money=1000)
    me["tiles"][0][0] = {"kind": "PLANT", "crop": "WHEAT"}
    opp = _empty_farm(money=100)
    opp["tiles"][0][0] = {"kind": "PLANT", "crop": "MELON"}
    opp["tiles"][0][1] = {"kind": "PLANT", "crop": "MELON"}
    opp["tiles"][0][2] = {"kind": "PLANT", "crop": "MELON"}
    assert is_clone_like(me, opp) is False


def test_is_clone_like_no_opponent():
    me = _empty_farm()
    assert is_clone_like(me, None) is False
