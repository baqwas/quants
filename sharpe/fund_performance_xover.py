import pandas as pd
import mstarpy
from datetime import date, timedelta
import matplotlib.pyplot as plt


def get_historical_performance_data(ticker, start_date=None, end_date=None):
    """
    Retrieves the historical NAV data for a mutual fund using its ticker symbol.

    Args:
        ticker (str): The common ticker symbol of the mutual fund.
        start_date (datetime.date): The start date for the data.
        end_date (datetime.date): The end date for the data.

    Returns:
        pd.DataFrame: A DataFrame with historical NAV data, or None if data is unavailable.
    """
    if start_date is None:
        end_date = date.today()
        start_date = end_date - timedelta(days=5 * 365)

    try:
        fund = mstarpy.Funds(term=ticker)

        if fund.name == 'No name found':
            print(f"Warning: Could not find fund for ticker '{ticker}'. Skipping.")
            return None

        print(f"Successfully found fund: {fund.name}")

        nav_history = fund.nav(start_date=start_date, end_date=end_date, frequency="daily")

        if not nav_history:
            print(f"Warning: No historical data found for '{fund.name}'.")
            return None

        data = pd.DataFrame(nav_history)
        data['date'] = pd.to_datetime(data['date'])
        data.set_index('date', inplace=True)
        data = data.sort_index()

        if data.empty or 'nav' not in data.columns:
            print(f"Warning: Insufficient data or 'nav' column not found for '{fund.name}'.")
            return None

        data['Fund Name'] = fund.name

        return data

    except Exception as e:
        print(f"An error occurred for ticker '{ticker}': {e}")
        return None


def find_crossover_points(df, fund_name):
    """
    Finds and prints the 20-day and 100-day Simple Moving Average (SMA) crossover points.

    Args:
        df (pd.DataFrame): DataFrame containing the fund's historical NAV data.
        fund_name (str): The name of the fund for printing purposes.
    """
    # Define color codes for console output
    GREEN = '\033[92m'
    RED = '\033[91m'
    ENDC = '\033[0m'

    # Calculate 20-day and 100-day SMAs
    df['SMA20'] = df['nav'].rolling(window=20).mean()
    df['SMA100'] = df['nav'].rolling(window=100).mean()

    # Drop rows with NaN values resulting from rolling calculations
    df.dropna(inplace=True)

    # Check if there's enough data for crossovers
    if len(df) < 2:
        print(f"Not enough data to calculate crossovers for {fund_name}.")
        return

    # Create a boolean series where True means SMA20 > SMA100
    df['crossover_signal'] = df['SMA20'] > df['SMA100']

    # Find where the signal changes from one day to the next
    # A crossover occurs where the `crossover_signal` is different from the previous day's signal
    df['position_change'] = df['crossover_signal'].diff()

    print(f"\n--- Crossover Points for {fund_name} ---")

    # Bullish crossover (20-day SMA crosses ABOVE 100-day SMA)
    bullish_crossovers = df[df['position_change'] == True]
    if not bullish_crossovers.empty:
        print(f"{GREEN}Green (Bullish) Crossovers:{ENDC}")
        for index, row in bullish_crossovers.iterrows():
            print(f"  - Date: {index.strftime('%Y-%m-%d')}")
    else:
        print(f"{GREEN}No green (bullish) crossovers found.{ENDC}")

    # Bearish crossover (20-day SMA crosses BELOW 100-day SMA)
    bearish_crossovers = df[df['position_change'] == False]
    if not bearish_crossovers.empty:
        print(f"{RED}Red (Bearish) Crossovers:{ENDC}")
        for index, row in bearish_crossovers.iterrows():
            print(f"  - Date: {index.strftime('%Y-%m-%d')}")
    else:
        print(f"{RED}No red (bearish) crossovers found.{ENDC}")


def plot_performance_trends(all_data, comparison_days, benchmark_ticker):
    """
    Plots the normalized performance trends of funds and the benchmark.

    Args:
        all_data (dict): Dictionary of pandas DataFrames with historical NAV data.
        comparison_days (int): The number of days for the comparison period.
        benchmark_ticker (str): The ticker symbol for the benchmark.
    """
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(12, 8))

    for ticker, df in all_data.items():
        # Normalize the performance to a starting value of 100
        normalized_data = (df['nav'] / df['nav'].iloc[0]) * 100

        label = f"{df['Fund Name'].iloc[0]} ({ticker})"

        # Highlight the benchmark
        if ticker == benchmark_ticker:
            ax.plot(normalized_data.index, normalized_data, label=label, linewidth=3, color='black', alpha=0.8)
        else:
            ax.plot(normalized_data.index, normalized_data, label=label, linewidth=1.5, linestyle='--')

    ax.set_title(f'Performance Comparison over the Last {comparison_days} Days', fontsize=16, fontweight='bold')
    ax.set_xlabel('Date', fontsize=12)
    ax.set_ylabel('Normalized Performance (Start = 100)', fontsize=12)
    ax.axhline(y=100, color='gray', linestyle=':', linewidth=1)
    ax.legend(loc='upper left', frameon=True, shadow=True)
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.tight_layout()
    plt.show()


def main():
    """
    Main function to read tickers from a file, retrieve their historical
    performance data, and compare it to the S&P 500, including a chart and
    crossover points.
    """
    fund_tickers_file = '../tickers/ml_rollover_ira.txt'
    benchmark_ticker = 'VOO'  # Using Vanguard's S&P 500 ETF as a proxy
    comparison_days = 365

    try:
        with open(fund_tickers_file, 'r') as file:
            tickers = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        print(f"Error: File '{fund_tickers_file}' not found. Please create the file with ticker symbols.")
        return

    all_tickers = tickers + [benchmark_ticker]
    all_performance_data = {}
    total_returns = {}

    print(f"Processing {len(all_tickers)} funds/indices...")
    print("-" * 50)

    for ticker in all_tickers:
        end_date = date.today()
        start_date = end_date - timedelta(days=comparison_days)

        historical_data = get_historical_performance_data(ticker, start_date=start_date, end_date=end_date)

        if historical_data is not None and not historical_data.empty:
            all_performance_data[ticker] = historical_data

            # Find and print moving average crossovers
            find_crossover_points(historical_data, historical_data['Fund Name'].iloc[0])

            start_price = historical_data['nav'].iloc[0]
            end_price = historical_data['nav'].iloc[-1]
            total_return = ((end_price - start_price) / start_price) * 100
            total_returns[ticker] = total_return

            print(f"Successfully retrieved data for {ticker} ({historical_data['Fund Name'].iloc[0]}).")
            print(f"Total return over the last {comparison_days} days: {total_return:.2f}%")
            print("-" * 30)
        else:
            print(f"Failed to retrieve historical data for {ticker}.")

    if total_returns:
        print("\n--- Performance Comparison (Last 365 Days) ---")
        comparison_df = pd.DataFrame(
            {'Total Return (%)': total_returns}
        )
        comparison_df = comparison_df.sort_values(by='Total Return (%)', ascending=False)
        print(comparison_df)

        # Plot the performance trends
        plot_performance_trends(all_performance_data, comparison_days, benchmark_ticker)
    else:
        print("No performance data was successfully retrieved for comparison.")


if __name__ == "__main__":
    main()