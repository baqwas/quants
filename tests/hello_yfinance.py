import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from scipy.stats import percentileofscore
import requests
import time  # New import for delays

# Define a default User-Agent string
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def get_stock_data(ticker_symbol, max_retries=5, base_delay=5):
    """
    Fetches historical and fundamental data for a given stock ticker with retries and exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            # Create a session with a custom User-Agent header
            session = requests.Session()
            session.headers.update({'User-Agent': DEFAULT_USER_AGENT})
            # Yahoo API requires curl_cffi session not < class 'requests.sessions.Session'>.
            # Solution: stop using requests and use yfinance directly with a session.
            # Note: yfinance handles its own session management, so we don't need to pass the session
            # However, if you want to use a custom session, you can pass it to yfinance.
            # Note: yfinance does not directly support passing a session, so we will use the default
            # yfinance session. If you need to use a custom session, you can modify the yfinance library
            ticker = yf.Ticker(ticker_symbol) # , session=session)  # Pass the session to yfinance

            # Fetch historical price data for the last year
            end_date = date.today()
            start_date = end_date - timedelta(days=365)
            hist = ticker.history(period='1y')

            # Fetch fundamental data (this may not be complete or always available)
            info = ticker.info

            # If successful, return data and break loop
            if not hist.empty and info:
                print(f"Successfully fetched data for {ticker_symbol} on attempt {attempt + 1}.")
                time.sleep(0.5)  # Be polite: small delay after successful fetch
                return hist, info
            else:
                print(f"Warning: No data returned for {ticker_symbol} on attempt {attempt + 1}. Retrying...")

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError,
                requests.exceptions.JSONDecodeError) as e:
            if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 429:
                print(f"Rate limit hit for {ticker_symbol} (HTTP 429) on attempt {attempt + 1}. Retrying...")
            elif isinstance(e, requests.exceptions.ConnectionError):
                print(f"Connection error for {ticker_symbol} on attempt {attempt + 1}: {e}. Retrying...")
            elif isinstance(e, requests.exceptions.JSONDecodeError):
                print(f"JSON decode error for {ticker_symbol} on attempt {attempt + 1}: {e}. Retrying...")
            else:
                print(f"An unexpected error occurred for {ticker_symbol} on attempt {attempt + 1}: {e}. Retrying...")

            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt)  # Exponential backoff
                print(f"Waiting {wait_time} seconds before next retry...")
                time.sleep(wait_time)
            else:
                print(f"Max retries ({max_retries}) exhausted for {ticker_symbol}. Could not fetch data.")
                return None, None
        except Exception as e:
            # Catch any other unexpected errors
            print(f"An unhandled error occurred for {ticker_symbol}: {e}")
            return None, None

    return None, None  # Should not be reached if max_retries is handled correctly


def calculate_relative_strength_score(historical_data):
    """
    Calculates an approximate Relative Strength (RS) score.
    This method is based on a common approximation: a weighted average of
    the stock's price change over different periods, ranked against other stocks.
    Since we can't rank against all other stocks, we use the raw score as a proxy.
    """
    if historical_data is None or historical_data.empty:
        return 0

    # Calculate rate of change for different periods
    roc_3_months = historical_data['Close'].pct_change(periods=63).iloc[-1] if len(historical_data) >= 63 else 0
    roc_6_months = historical_data['Close'].pct_change(periods=126).iloc[-1] if len(historical_data) >= 126 else 0
    roc_9_months = historical_data['Close'].pct_change(periods=189).iloc[-1] if len(historical_data) >= 189 else 0
    roc_12_months = historical_data['Close'].pct_change(periods=252).iloc[-1] if len(historical_data) >= 252 else 0

    # Approximate IBD weighting (from public sources like Optuma community)
    rs_score = (0.4 * roc_3_months) + (0.2 * roc_6_months) + (0.2 * roc_9_months) + (0.2 * roc_12_months)

    # We will assume a score from 1-99 for the purpose of this demo
    # In reality, this would be a percentile ranking against all other stocks.
    # We will cap it at 99 for illustrative purposes.
    return max(0, min(99, int(rs_score * 10000)))


def calculate_eps_score(fundamental_info):
    """
    Calculates an approximate EPS (Earnings Per Share) score based on growth rates.
    This is a simplified approach, as the official IBD rank is more complex.
    """
    if not fundamental_info:
        return 0

    # Use available growth rates from yfinance info
    try:
        eps_growth_quarterly = fundamental_info.get('earningsQuarterlyGrowth', 0) * 100
        eps_growth_yearly = fundamental_info.get('earningsGrowth', 0) * 100

        # Simplified scoring based on growth, e.g., anything over 25% is good
        if eps_growth_yearly > 40:
            return 90
        elif eps_growth_yearly > 25:
            return 80
        elif eps_growth_yearly > 10:
            return 70
        else:
            return 50

    except (KeyError, TypeError):
        return 0


def calculate_smr_score(fundamental_info):
    """
    Approximates the SMR (Sales, Margins, Return on Equity) Rating.
    This score is highly proprietary, so this is a simplified proxy.
    """
    if not fundamental_info:
        return 0

    try:
        sales_growth = fundamental_info.get('revenueGrowth', 0)
        roe = fundamental_info.get('returnOnEquity', 0)

        # Simplified scoring based on key metrics
        score = 0
        if sales_growth > 0.15:  # > 15% sales growth is a positive
            score += 33
        if roe > 0.15:  # > 15% ROE is a positive
            score += 33

        # The official SMR rating also considers profit margins, which may not be
        # directly available or easily comparable via a public API.

        return max(0, min(99, score))
    except (KeyError, TypeError):
        return 0


def calculate_composite_rating(ticker_symbol):
    """
    Calculates an approximate IBD Composite Rating for a given ticker.
    This function combines the individual component scores with a
    plausible weighting scheme.
    """
    historical_data, fundamental_info = get_stock_data(ticker_symbol)

    if historical_data is None or fundamental_info is None:
        return None

    # Calculate individual scores
    rs_score = calculate_relative_strength_score(historical_data)
    eps_score = calculate_eps_score(fundamental_info)
    smr_score = calculate_smr_score(fundamental_info)

    # Note: We're omitting Industry Group Rank and Accumulation/Distribution
    # as these require extensive data beyond a single stock.
    # The Industry Group Rank requires ranking the industry group itself, and
    # A/D requires tracking institutional buying/selling, which is not readily available.

    # Combine scores with an approximate weighting scheme
    # IBD states more weight is placed on EPS and Relative Strength.
    # We will approximate this with a higher percentage for those two.
    weight_rs = 0.45
    weight_eps = 0.45
    weight_smr = 0.10

    composite_score = (weight_rs * rs_score) + (weight_eps * eps_score) + (weight_smr * smr_score)

    # The final composite rating is a percentile rank from 1-99.
    # Since we can't rank against the entire market, we will use our
    # raw composite score as a proxy and cap it at 99.
    return int(min(99, max(0, composite_score)))


if __name__ == '__main__':
    # Example usage
    ticker = "BRKB"
    print(f"Calculating approximate IBD Composite Rating for {ticker}...")
    composite_rating = calculate_composite_rating(ticker)

    if composite_rating is not None:
        print(f"Approximate IBD Composite Rating for {ticker}: {composite_rating}")

    # Example of a different stock
    ticker_b = "MSFT"  # Changed to MSFT for testing
    print(f"\nCalculating approximate IBD Composite Rating for {ticker_b}...")
    composite_rating_b = calculate_composite_rating(ticker_b)

    if composite_rating_b is not None:
        print(f"Approximate IBD Composite Rating for {ticker_b}: {composite_rating_b}")