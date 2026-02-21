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
