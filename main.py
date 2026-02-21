import math
from pathlib import Path

import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Options Price Graph")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/options/{ticker}")
async def get_options(ticker: str):
    symbol = ticker.upper().strip()
    stock = yf.Ticker(symbol)

    # Validate ticker by checking for available expirations
    try:
        expirations = stock.options
    except Exception:
        raise HTTPException(status_code=404, detail=f"Ticker '{symbol}' not found or has no options data")

    if not expirations:
        raise HTTPException(status_code=404, detail=f"No options available for '{symbol}'")

    # Take the first 6 expiration dates
    selected_exps = list(expirations[:6])

    # Get current stock price
    current_price = None
    try:
        current_price = stock.fast_info.get("lastPrice")
    except Exception:
        pass

    # Fetch option chains for each expiration
    calls = {}
    puts = {}
    for exp in selected_exps:
        try:
            chain = stock.option_chain(exp)
        except Exception:
            continue

        calls[exp] = _df_to_records(chain.calls)
        puts[exp] = _df_to_records(chain.puts)

    if not calls and not puts:
        raise HTTPException(status_code=404, detail=f"Could not retrieve options data for '{symbol}'")

    return {
        "ticker": symbol,
        "currentPrice": current_price,
        "expirations": selected_exps,
        "calls": calls,
        "puts": puts,
    }


def compute_profit(chain: list[dict], current_price: float, investment: float, option_type: str = "calls") -> list[dict]:
    """Compute profit/loss for each strike given an investment amount.

    For each option in the chain, calculates how many contracts can be
    purchased with the investment, and the profit at expiration assuming
    the stock remains at current_price.

    Returns a list of dicts with keys: strike, contracts, totalCost, profit.
    """
    results = []
    for opt in chain:
        premium = opt.get("ask") if opt.get("ask") and opt["ask"] > 0 else opt.get("lastPrice")
        if not premium or premium <= 0:
            continue

        cost_per_contract = premium * 100
        contracts = int(investment // cost_per_contract)
        if contracts <= 0:
            continue

        total_cost = contracts * cost_per_contract
        if option_type == "calls":
            intrinsic = max(0.0, current_price - opt["strike"])
        else:
            intrinsic = max(0.0, opt["strike"] - current_price)
        profit = contracts * intrinsic * 100 - total_cost

        results.append({
            "strike": opt["strike"],
            "contracts": contracts,
            "totalCost": round(total_cost, 2),
            "profit": round(profit, 2),
        })
    return results


def _clean_value(v):
    """Convert NaN/Inf to None for JSON serialization."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _df_to_records(df):
    """Convert an options DataFrame to a list of dicts with clean values."""
    cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility", "inTheMoney"]
    subset = df[[c for c in cols if c in df.columns]]
    records = subset.to_dict(orient="records")
    return [{k: _clean_value(v) for k, v in row.items()} for row in records]


# Mount static files LAST so API routes take priority
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
