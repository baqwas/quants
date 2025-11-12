import yfinance as yf
import pandas as pd

def test_adj_close_column(ticker):
    """
    Fetches historical data for a given ticker and checks if the 'Adj Close'
    column is present, displaying the results in a tabular manner.
    """
    print(f"Testing for ticker: {ticker}")
    try:
        # Fetch data with auto_adjust=False to ensure 'Adj Close' is explicitly present
        # Using a shorter period ('1mo') for quicker testing
        data = yf.download(ticker, period='1mo', interval='1d', auto_adjust=False, progress=False)

        if data.empty:
            print(f"No data returned for {ticker}.")
            return

        print("\n--- Columns in the downloaded data ---")
        print(data.columns.tolist())

        if 'Adj Close' in data.columns:
            print(f"\n'Adj Close' column IS present for {ticker}.")
            print("\n--- Sample data with 'Adj Close' (first 5 rows) ---")
            # Display only relevant columns for 'Adj Close' verification
            print(data[['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']].head())
        else:
            print(f"\n'Adj Close' column IS NOT present for {ticker}.")
            print("\n--- Full data head (for inspection, 'Adj Close' missing) ---")
            print(data.head()) # Show full head if 'Adj Close' is missing for debugging

    except Exception as e:
        print(f"An error occurred while fetching data for {ticker}: {e}")

if __name__ == "__main__":
    test_ticker = 'AAPL'
    test_adj_close_column(test_ticker)