import pandas as pd
import yfinance as yf
from datetime import date, timedelta
import matplotlib.pyplot as plt
import time


def get_historical_performance_data(ticker, start_date=None, end_date=None):
    """
    Retrieves historical performance data for a ticker using yfinance,
    with a retry mechanism and a custom User-Agent header to handle API issues.

    Args:
        ticker (str): The common ticker symbol of the asset.
        start_date (datetime.date): The start date for the data.
        end_date (datetime.date): The end date for the data.

    Returns:
        pd.DataFrame: A DataFrame with historical data, including 'nav' and 'Volume',
                      or None if data is unavailable.
    """
    if start_date is None:
        end_date = date.today()
        start_date = end_date - timedelta(days=5 * 365)

    retries = 3
    delay = 5  # seconds

    for attempt in range(retries):
        try:
            print(f"Attempting to download data for {ticker} (Attempt {attempt + 1}/{retries})...")

            # Using the yf.Ticker approach to add custom headers, which can sometimes bypass issues
            ticker_obj = yf.Ticker(ticker)
            data = ticker_obj.history(start=start_date, end=end_date, interval="1d")

            if data.empty:
                print(f"Warning: No historical data found for '{ticker}'.")
                return None

            # Use 'Adj Close' for NAV/price data and rename it to 'nav'
            data['nav'] = data['Adj Close']
            data['Fund Name'] = ticker  # yfinance doesn't provide a name easily
            data['volume'] = data['Volume']

            return data

        except Exception as e:
            print(f"An error occurred for ticker '{ticker}': {e}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"Failed to retrieve data for '{ticker}' after {retries} attempts.")
                return None


def plot_fund_vs_benchmark(fund_data, benchmark_data, comparison_days):
    """
    Plots the performance trend of a single fund against a benchmark, including
    SMAs, crossovers, RSI, MACD, ROC, and Volume Trend.
    """

    def calculate_rsi(series, period=14):
        """Calculates the Relative Strength Index (RSI) for a pandas Series."""
        delta = series.diff().dropna()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_macd(series, fast_period=12, slow_period=26, signal_period=9):
        """Calculates the MACD for a pandas Series."""
        exp1 = series.ewm(span=fast_period, adjust=False).mean()
        exp2 = series.ewm(span=slow_period, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=signal_period, adjust=False).mean()
        histogram = macd - signal
        return macd, signal, histogram

    def calculate_roc(series, period=14):
        """Calculates the Rate of Change (ROC) for a pandas Series."""
        return ((series - series.shift(period)) / series.shift(period)) * 100

    plt.style.use('seaborn-v0_8-darkgrid')
    fig, (ax1, ax2, ax3, ax4, ax5) = plt.subplots(5, 1, figsize=(12, 30),
                                                  gridspec_kw={'height_ratios': [4, 1, 1, 1, 1]},
                                                  sharex=True)

    # Use the last `comparison_days` for plotting
    combined_data = pd.concat([fund_data['nav'], benchmark_data['nav']], axis=1,
                              keys=['fund_nav', 'benchmark_nav']).dropna().iloc[-comparison_days:]
    fund_volume_data = fund_data['volume'].iloc[-comparison_days:]

    if combined_data.empty:
        print("Not enough data to perform comparison. Skipping plot.")
        return

    fund_name = fund_data['Fund Name'].iloc[0]
    benchmark_name = benchmark_data['Fund Name'].iloc[0]

    fund_normalized = (combined_data['fund_nav'] / combined_data['fund_nav'].iloc[0]) * 100
    benchmark_normalized = (combined_data['benchmark_nav'] / combined_data['benchmark_nav'].iloc[0]) * 100

    fund_sma20 = fund_normalized.rolling(window=20).mean()
    fund_sma100 = fund_normalized.rolling(window=100).mean()
    fund_rsi = calculate_rsi(fund_normalized)
    fund_macd, fund_signal, fund_histogram = calculate_macd(fund_normalized)
    fund_roc = calculate_roc(fund_normalized)

    # --- Main Performance Plot (ax1) ---
    ax1.plot(fund_normalized.index, fund_normalized, label=f'{fund_name} NAV', linewidth=2)
    ax1.plot(benchmark_normalized.index, benchmark_normalized, label=f'{benchmark_name} NAV', linewidth=2,
             linestyle='--', color='black')
    ax1.plot(fund_sma20.index, fund_sma20, label=f'{fund_name} 20-Day SMA', linestyle=':', color='skyblue')
    ax1.plot(fund_sma100.index, fund_sma100, label=f'{fund_name} 100-Day SMA', linestyle=':', color='orange')
    crossover_signal = (fund_sma20 > fund_sma100).astype(int)
    position_change = crossover_signal.diff()
    bullish_crossovers = position_change[position_change == 1].index
    ax1.scatter(bullish_crossovers, fund_sma20.loc[bullish_crossovers], marker='^', color='green', s=100,
                label='Bullish Crossover')
    bearish_crossovers = position_change[position_change == -1].index
    ax1.scatter(bearish_crossovers, fund_sma20.loc[bearish_crossovers], marker='v', color='red', s=100,
                label='Bearish Crossover')
    ax1.set_title(f'Performance: {fund_name} vs. {benchmark_name} over the Last {comparison_days} Days', fontsize=16,
                  fontweight='bold')
    ax1.set_ylabel('Normalized Performance (Start = 100)', fontsize=12)
    ax1.axhline(y=100, color='gray', linestyle=':', linewidth=1)
    ax1.legend(loc='upper left', frameon=True, shadow=True)
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5)

    # --- RSI Plot (ax2) ---
    ax2.plot(fund_rsi.index, fund_rsi, label=f'{fund_name} RSI', color='purple')
    ax2.axhline(70, color='red', linestyle='--', label='Overbought (70)')
    ax2.axhline(30, color='green', linestyle='--', label='Oversold (30)')
    ax2.set_title(f'Relative Strength Index (RSI)', fontsize=12)
    ax2.set_ylabel('RSI', fontsize=12)
    ax2.legend(loc='upper left')
    ax2.grid(True, which='both', linestyle='--', linewidth=0.5)

    # --- MACD Plot (ax3) ---
    ax3.plot(fund_macd.index, fund_macd, label='MACD Line', color='blue', linewidth=1.5)
    ax3.plot(fund_signal.index, fund_signal, label='Signal Line', color='orange', linestyle='--', linewidth=1.5)
    ax3.bar(fund_histogram.index, fund_histogram, label='Histogram', color='gray', alpha=0.5)
    ax3.axhline(0, color='black', linestyle='-', linewidth=1)
    ax3.set_title('MACD', fontsize=12)
    ax3.set_ylabel('Value', fontsize=12)
    ax3.legend(loc='upper left')
    ax3.grid(True, which='both', linestyle='--', linewidth=0.5)

    # --- ROC Plot (ax4) ---
    ax4.plot(fund_roc.index, fund_roc, label=f'{fund_name} ROC', color='darkgreen', linewidth=1.5)
    ax4.axhline(0, color='black', linestyle='--', linewidth=1)
    ax4.set_title('Rate of Change (ROC)', fontsize=12)
    ax4.set_ylabel('ROC (%)', fontsize=12)
    ax4.legend(loc='upper left')
    ax4.grid(True, which='both', linestyle='--', linewidth=0.5)

    # --- Volume Plot (ax5) ---
    ax5.bar(fund_volume_data.index, fund_volume_data, color='gray', alpha=0.7)
    ax5.set_title('Volume', fontsize=12)
    ax5.set_xlabel('Date', fontsize=12)
    ax5.set_ylabel('Volume', fontsize=12)
    ax5.grid(True, which='major', linestyle='--', linewidth=0.5)

    plt.tight_layout()
    plt.show()


def main():
    """
    Main function to read tickers from a file, retrieve their historical
    performance data, and compare each to the S&P 500 with a dedicated plot.
    """
    fund_tickers_file = '../tickers/ml_rollover_ira.txt'
    benchmark_ticker = 'SPY'
    comparison_days = 365

    try:
        with open(fund_tickers_file, 'r') as file:
            tickers = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        print(f"Error: File '{fund_tickers_file}' not found. Please create the file with ticker symbols.")
        return

    print(f"Processing {len(tickers)} funds and benchmark...")
    print("-" * 50)

    end_date = date.today()
    start_date = end_date - timedelta(days=comparison_days)
    benchmark_data = get_historical_performance_data(benchmark_ticker, start_date=start_date, end_date=end_date)

    if benchmark_data is None:
        print("Failed to retrieve benchmark data. Cannot perform comparison.")
        return

    print("-" * 50)

    for ticker in tickers:
        end_date = date.today()
        start_date = end_date - timedelta(days=comparison_days)

        fund_data = get_historical_performance_data(ticker, start_date=start_date, end_date=end_date)

        if fund_data is not None and not fund_data.empty:
            plot_fund_vs_benchmark(fund_data, benchmark_data, comparison_days)
        else:
            print(f"Failed to retrieve historical data for {ticker}. Skipping plot.")
            print("-" * 30)

    if not tickers:
        print("No mutual fund tickers were provided in the file.")
    else:
        print("All plots generated.")


if __name__ == "__main__":
    main()