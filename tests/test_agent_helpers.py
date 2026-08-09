"""Narrow tests for src.agent's pure, deterministic helper functions.

Full-game correctness (does the agent actually win) is covered by
src/simulate.py against the real engine, not here -- these tests only
guard the small pieces of logic that are easy to get subtly wrong and
cheap to check without spinning up kaggle_environments.
"""

from src import config as cfg
from src.agent import (
    build_buy_orders,
    build_sell_orders,
    is_clone_like,
    score_animal,
    score_crop,
)


def test_score_crop_prefers_higher_price():
    low = {"WHEAT": 20}
    high = {"WHEAT": 60}
    assert score_crop("WHEAT", high) > score_crop("WHEAT", low)


def test_score_crop_ranking_shifts_with_price():
    # At base prices, melon (seed 80, base 250) should out-score wheat
    # (seed 10, base 25) on a profit-per-day basis.
    base_prices = {c: info["base_price"] for c, info in cfg.CROPS.items()}
    assert score_crop("MELON", base_prices) > score_crop("WHEAT", base_prices)

    # If wheat's price triples while melon crashes to the floor, wheat
    # should overtake melon -- the score must actually react to live prices,
    # not just the static base table.
    skewed_prices = dict(base_prices)
    skewed_prices["WHEAT"] = 90
    skewed_prices["MELON"] = 1
    assert score_crop("WHEAT", skewed_prices) > score_crop("MELON", skewed_prices)


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

    # Empty shed -- must buy exactly the buffer shortfall (3 per animal, 1 animal).
    shed_empty = {"WHEAT": 0}
    buys2 = build_buy_orders(me, shed_empty, {}, "ROTATE_AND_COMPOUND", prices, None, None, 0)
    wheat_orders = [o for o in buys2 if o[0] == "BUY_PRODUCT" and o[1] == "WHEAT"]
    assert len(wheat_orders) == 1
    assert wheat_orders[0][2] == 3


def test_buy_animal_skipped_once_already_owned():
    me = {"money": 5000, "tiles": [[None] * 10 for _ in range(10)], "unlocked_quadrants": ["NW"], "hires_today": 0}
    prices = {"GOOSE": 300}
    shed_with_goose = {"GOOSE": 1}
    buys = build_buy_orders(me, shed_with_goose, {}, "ROTATE_AND_COMPOUND", prices, None, "GOOSE", 0)
    assert not any(o[0] == "BUY_ANIMAL" for o in buys)

    shed_empty = {}
    buys2 = build_buy_orders(me, shed_empty, {}, "ROTATE_AND_COMPOUND", prices, None, "GOOSE", 0)
    assert any(o[0] == "BUY_ANIMAL" and o[1] == "GOOSE" for o in buys2)


def test_get_phase_boundaries():
    assert cfg.get_phase(0) == "BOOTSTRAP"
    assert cfg.get_phase(2) == "BOOTSTRAP"
    assert cfg.get_phase(3) == "EXPAND"
    assert cfg.get_phase(11) == "EXPAND"
    assert cfg.get_phase(12) == "ROTATE_AND_COMPOUND"
    assert cfg.get_phase(23) == "ROTATE_AND_COMPOUND"
    assert cfg.get_phase(24) == "PROTECT_VALUE"
    assert cfg.get_phase(27) == "PROTECT_VALUE"
    assert cfg.get_phase(28) == "CASH"
    assert cfg.get_phase(29) == "CASH"


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
