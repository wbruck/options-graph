# Options Price Graph

A web application for visualizing stock options data. Enter a ticker symbol to view option premiums, implied volatility, open interest, and profit/loss projections across strike prices and expiration dates.

## Features

- **Options chain viewer** — Browse calls and puts for up to 6 expiration dates
- **Premium chart** — Option price by strike for each expiration
- **Implied volatility chart** — IV smile/skew visualization
- **Open interest chart** — Volume distribution across strikes
- **Profit/loss calculator** — Enter an investment amount to see projected P/L at expiration for each strike, based on how many contracts are purchasable
- **Data table** — Raw options data with ITM/OTM highlighting
- **ATM indicator** — Dashed line marking the current stock price on all charts

## Prerequisites

- Python 3.10+

## Installation

```bash
git clone <repository-url>
cd options-graph
pip install -r requirements.txt
```

## Running the App

```bash
python main.py
```

The server starts at [http://localhost:8000](http://localhost:8000).

Alternatively, run with uvicorn directly:

```bash
uvicorn main:app --reload
```

## Running Tests

Install test dependencies:

```bash
pip install pytest httpx
```

Run the test suite:

```bash
pytest test_main.py -v
```

## Project Structure

```
options-graph/
├── main.py            # FastAPI backend — API routes, data processing, profit calculation
├── test_main.py       # Test suite (pytest) for backend logic and API endpoints
├── requirements.txt   # Python dependencies
├── .gitignore
└── static/
    └── index.html     # Single-page frontend — UI, charts (Plotly.js), profit calculator
```

### Backend (`main.py`)

- **`GET /`** — Serves the frontend
- **`GET /api/options/{ticker}`** — Fetches options data from Yahoo Finance via `yfinance`. Returns current price, expiration dates, and call/put chains with strike, premium, bid/ask, volume, open interest, and implied volatility
- **`compute_profit(chain, current_price, investment, option_type)`** — Calculates how many contracts can be purchased with a given investment and the resulting profit/loss at expiration
- **`_df_to_records(df)`** — Converts pandas DataFrames to JSON-safe dicts, filtering to relevant columns
- **`_clean_value(v)`** — Converts `NaN`/`Inf` floats to `None` for JSON serialization

### Frontend (`static/index.html`)

Single-page app using [Plotly.js](https://plotly.com/javascript/) for charting. All rendering and profit calculation logic runs client-side after fetching data from the API.

## Tech Stack

- **Backend:** FastAPI, uvicorn, yfinance, pandas
- **Frontend:** Vanilla HTML/JS, Plotly.js (CDN)
- **Testing:** pytest, httpx, FastAPI TestClient

## License

MIT
