import marketforge as mf


def test_instruments_lists_the_catalog_by_symbol():
    table = mf.instruments()
    assert len(table) == 208 and table.index.name == "symbol"
    assert table.loc["AAPL", "market"] == "stocks"
    assert bool(table.loc["EURJPY", "derived"]) and not table.loc["EURUSD", "derived"]
    assert not table[table.market != "forex"].derived.any()


def test_instruments_filters_markets_and_applies_overrides():
    crypto = mf.instruments("crypto", overrides={"BTCUSD": {"start_price": 42000}})
    assert set(crypto.market) == {"crypto"}
    assert crypto.loc["BTCUSD", "start_price"] == 42000
