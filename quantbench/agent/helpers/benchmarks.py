from quantbench.data.universe import UniverseDefinition


def _benchmark_symbol_from_fetch_params(fetch_params: dict[str, str] | None) -> str | None:
    if not fetch_params:
        return None
    return "BTC/USDT" if "/" in fetch_params.get("symbol", "") else "SPY"


def _benchmark_symbol_for_asset(asset_class: str) -> str:
    return "BTC/USDT" if asset_class == "crypto" else "SPY"


def _is_crypto_symbol(fetch_params: dict[str, str] | None) -> bool:
    return bool(fetch_params and "/" in fetch_params.get("symbol", ""))


def _is_crypto_universe(universe: UniverseDefinition | None) -> bool:
    return bool(universe and universe.asset_class == "crypto")
