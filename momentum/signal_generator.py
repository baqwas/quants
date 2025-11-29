#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
signal_generator.py

================================================================================
PROJECT: AI/Quantum Tech Stock Momentum Tracker
AUTHOR: Matha Goram
DATE: 2025-12-15 (Feature: Added Relative Strength Ranking (RSR) Filter)
VERSION: 2.0.0 (Major Feature Add - RSR)
================================================================================

PURPOSE & METHODOLOGY:
--------------------
Monitors high-tech stocks using MACD/Stochastic crossovers, the Bollinger Bands
filter, the Sector Momentum Filter, AND a new **Relative Strength Ranking (RSR) Filter**.
Only bullish signals are considered if:
1. The stock's parent sector ETF is in an uptrend (above 200-day SMA).
2. The stock is a momentum "leader," outperforming its sub-sector/peer ETF (Sub-Sector RSR > 1.0).

EXECUTION & OUTPUT:
------------------
1. Downloads 6 months of daily stock data via the yfinance API.
2. Calculates technical indicators (MACD, RSI, Stochastic, ROC, BB).
3. Fetches sector/benchmark ETF data and determines sector trend and RSR.
4. If a crossover is detected (last 7 days) and passes ALL filters (BB, Sector, RSR),
   sends an email alert with the chart and full details.
5. Consolidates data retrieval and database logging failures into a single warning email.
6. Sends a final status report (status_log.txt) via email attachment.

REQUIRED EXTERNAL FILES:
------------------------
1. config.toml: MUST contain valid credentials for [database], [analysis] (including
   'bb_window', 'bb_std_dev', 'bb_filter_pct'), and [smtp].
2. tickers.txt (or other specified file): MUST contain a newline-separated list of stock tickers.
"""
import math
from datetime import datetime, date
import mariadb
from dateutil.relativedelta import relativedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
import mplfinance as mpf
import numpy as np
import os
import pandas as pd
import smtplib
import ssl
import sys
import toml
import yfinance as yf
import argparse # V2.1.0 ADDITION: for command line parsing

# --- Configuration Constants ---
STATUS_LOG_FILE = "status_log.txt"
LOOKBACK_DAYS = 7  # Number of days to check for a signal (including today's close)
CHART_DIR = "charts"
SMTP_REPORT_SUBJECT = "⚠️ Momentum Tracker - Data/DB Failure Report"

# V1.9.0 ADDITION: Sector Momentum Filter
SECTOR_SMA_WINDOW = 200  # Days for the sector uptrend filter

# V2.0.0 ADDITION: Relative Strength Ranking (RSR)
RSR_WINDOW_DAYS = 90
MARKET_INDEX_TICKER = '^GSPC'  # S&P 500 as the broad market index

# IMPORTANT: This map MUST be customized for all monitored stocks.
# Map: Stock Ticker -> (Sector ETF for SMA Check, RSR Sub-Sector/Peer ETF)
TICKER_BENCHMARK_MAP = {
    'NVDA': ('XLK', 'SMH'),  # XLK (Tech) for SMA, SMH (Semiconductors ETF) for RSR peer
    'MSFT': ('XLK', 'IGV'),  # XLK (Tech) for SMA, IGV (Software ETF) for RSR peer (Example)
    'AMZN': ('XLY', 'XRT'),  # XLY (Disc.) for SMA, XRT (Retail ETF) for RSR peer (Example)
    'GOOGL': ('XLC', 'XLC'),  # XLC (Comm Services) for both (using itself as sub-sector for simplicity)
    # Add other monitored tickers here
}


# --- Utility Functions ---

def parse_arguments():
    """Parses command line arguments for the tickers file path. (V2.1.0)"""
    parser = argparse.ArgumentParser(
        description="AI/Quantum Tech Stock Momentum Tracker (v2.0.0). "
                    "Analyzes stocks and sends alerts based on technical and momentum filters."
    )
    parser.add_argument(
        '-t', '--tickers_file',
        type=str,
        default="tickers.txt",
        help='Path to the file containing the list of stock tickers (default: %(default)s).'
    )
    args = parser.parse_args()
    return args.tickers_file


def load_config():
    """Loads and validates the configuration from config.toml."""
    try:
        config = toml.load("config.toml")

        # Ensure 'database', 'smtp', and 'static' sections are used
        db_config = config.get('database', {})
        if not all(key in db_config for key in ['host', 'port', 'user', 'password', 'database']):
            raise ValueError("Missing required keys in [database] section of config.toml.")

        smtp_config = config.get('smtp', {})
        if not all(key in smtp_config for key in
                   ['smtp_server', 'smtp_port', 'smtp_username', 'smtp_password', 'sender_email', 'recipient_email']):
            raise ValueError("Missing required keys in [smtp] section of config.toml.")

        static_config = config.get('static', {})
        # NOTE: Validation for 'tickers_file' is removed here, as the value is now read
        # primarily from the command line arguments in main().
        # if 'tickers_file' not in static_config:
        #     raise ValueError("Missing 'tickers_file' key in [static] section of config.toml.")

        # Ensure 'analysis' section is used (V1.8.0/V1.9.0 keys)
        analysis_config = config.get('analysis', {})
        required_analysis_keys = ['period_months', 'short_window', 'long_window', 'signal_window',
                                  'stoch_k_window', 'stoch_d_window', 'bb_window', 'bb_std_dev', 'bb_filter_pct']
        if not all(key in analysis_config for key in required_analysis_keys):
            raise ValueError(
                f"Missing required keys in [analysis] section of config.toml: {', '.join(required_analysis_keys)}.")

        return db_config, smtp_config, analysis_config, static_config

    except FileNotFoundError:
        print("CRITICAL ERROR: config.toml not found.")
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to load configuration: {e}")
        sys.exit(1)


def load_tickers(file_path):
    """Loads the list of tickers from the specified file."""
    try:
        with open(file_path, 'r') as f:
            # Load the full lines, including the description
            tickers = [line.strip() for line in f if line.strip()]
        if not tickers:
            print(f"WARNING: Tickers file {file_path} is empty. No stocks to process.")
        return tickers
    except FileNotFoundError:
        print(f"CRITICAL ERROR: Tickers file not found at {file_path}.")
        sys.exit(1)


def log_signal_to_db(db_config, ticker, signal_type, signal_description, signal_date, data_series):
    """
    Logs a detected signal into the MariaDB database.
    """
    conn = None
    success = False
    try:
        conn = mariadb.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
        )
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO stock_signals (
                ticker_symbol, signal_date, signal_type, description,
                price_at_signal, macd_value, signal_value, rsi_value
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                description = VALUES(description),
                price_at_signal = VALUES(price_at_signal),
                macd_value = VALUES(macd_value),
                signal_value = VALUES(signal_value),
                rsi_value = VALUES(rsi_value)
        """

        # Prepare values for logging
        macd_val = float(data_series.get('MACD', np.nan))
        signal_val = float(data_series.get('Signal_Line', np.nan))
        rsi_val = float(data_series.get('RSI', np.nan))

        if 'STOCH' in signal_type:
            # Map Stochastic indicators to the MACD/Signal fields for persistence
            macd_val = float(data_series.get('K_percent', np.nan))
            signal_val = float(data_series.get('D_percent', np.nan))

        values = (
            ticker,
            signal_date,
            signal_type,
            signal_description,
            float(data_series['Close']),
            macd_val,
            signal_val,
            rsi_val
        )

        cursor.execute(insert_query, values)
        conn.commit()
        success = True

        print(f"  -> Successfully logged {ticker} {signal_type} signal to MariaDB.")

    except mariadb.Error as e:
        print(f"  -> ERROR: Failed to log signal for {ticker} to MariaDB: {e}")
    except Exception as e:
        print(f"  -> ERROR: An unexpected error occurred during database logging for {ticker}: {e}")
    finally:
        if conn:
            conn.close()

    return success


def generate_status_log(tickers_file, total_processed, crossover_count, no_signal_count, true_failure_count,
                        analysis_config):
    """
    Creates a simple log file summarizing the execution results with meaningful counts.
    V2.0.0 UPDATE: Added RSR Filter config.
    """
    try:
        with open(tickers_file, 'r') as f:
            raw_tickers = [line.strip() for line in f if line.strip()]
    except Exception as e:
        raw_tickers = ["(Error reading specified tickers file)"]
        print(f"ERROR: Could not read tickers file for log generation: {e}")

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    log_content = f"""
================================================================================
AI/QUANTUM MOMENTUM TRACKER - DAILY EXECUTION SUMMARY
Timestamp: {timestamp}
--------------------------------------------------------------------------------
Configuration:
- MACD Windows: ({analysis_config['short_window']}, {analysis_config['long_window']}, {analysis_config['signal_window']})
- RSI Window: (14)
- Stochastic Windows: (K={analysis_config['stoch_k_window']}, D={analysis_config['stoch_d_window']})
- ROC Window: (14)
- Bollinger Bands: (Window={analysis_config['bb_window']}, StdDev={analysis_config['bb_std_dev']}, Filter={analysis_config['bb_filter_pct']}%)
- Sector Momentum Filter: (SMA Window={SECTOR_SMA_WINDOW} days)
- RSR Momentum Filter: (Window={RSR_WINDOW_DAYS} days, Market Index={MARKET_INDEX_TICKER})
- Signal Lookback: {LOOKBACK_DAYS} days
- Tickers file: {tickers_file}

Execution Stats:
- Total Tickers Processed: {total_processed}
- Signals Detected (MACD or STOCH Crossovers) & Passed BB/Sector/RSR Filters: {crossover_count}
- Successfully Processed (No Signal/Signal Filtered): {no_signal_count}
- CRITICAL Failures (Data/Logging/Unhandled): {true_failure_count}

Full Ticker List (from {tickers_file}):
{', '.join(raw_tickers)}
================================================================================
"""
    try:
        with open(STATUS_LOG_FILE, 'w') as f:
            f.write(log_content.strip())
        print(f"\nSTATUS: Successfully generated execution summary at {STATUS_LOG_FILE}")
    except Exception as e:
        print(f"ERROR: Failed to write status log file: {e}")


def create_chart(df, ticker, signal_title, signal_dates):
    """
    Generates a candlestick chart with technical indicators.
    Returns the file path of the saved chart.
    """
    if not os.path.exists(CHART_DIR):
        os.makedirs(CHART_DIR)

    chart_path = os.path.join(CHART_DIR, f"{ticker}_{date.today().strftime('%Y%m%d')}.png")

    # 1. Define custom MACD plots
    macd_colors = ['#1f77b4' if df['MACD_Hist'].iloc[i] >= 0 else '#ff7f0e' for i in range(len(df))]

    # Get marker coordinates for the stochastic signals on the price panel
    stoch_signals = signal_dates.get('STOCH', [])
    price_markers = []

    if stoch_signals:
        for stoch_date in stoch_signals:
            try:
                date_str = stoch_date.strftime('%Y-%m-%d')
                if date_str in df.index:
                    index_pos = df.index.get_loc(date_str)
                    price = df.loc[date_str]['High']
                    price_markers.append((index_pos, price))
            except Exception as e:
                print(f"  -> WARNING: Failed to locate signal date {stoch_date} for chart marker: {e}")

    marker_scatter = None
    if price_markers:
        marker_data = pd.Series(np.nan, index=df.index)
        for index_pos, price in price_markers:
            date_index = df.index[index_pos]
            marker_data.loc[date_index] = price

        marker_scatter = mpf.make_addplot(
            marker_data,
            type='scatter',
            markersize=100,
            marker='d',
            color='#FF00FF',
            panel=0,
            secondary_y=False
        )

    apds = [
        # Bollinger Bands on Price Panel (Panel 0)
        mpf.make_addplot(df['BB_Upper'], panel=0, color='lime', linestyle='-', alpha=0.7, secondary_y=False),
        mpf.make_addplot(df['BB_Middle'], panel=0, color='darkgray', linestyle='--', alpha=0.8, secondary_y=False),
        mpf.make_addplot(df['BB_Lower'], panel=0, color='lime', linestyle='-', alpha=0.7, secondary_y=False),

        # MACD Plot (Panel 2)
        mpf.make_addplot(df['MACD'], panel=2, color='blue', secondary_y=False, ylabel='MACD'),
        mpf.make_addplot(df['Signal_Line'], panel=2, color='red', secondary_y=False),
        mpf.make_addplot(df['MACD_Hist'], type='bar', panel=2, color=macd_colors, alpha=0.5, secondary_y=False),

        # RSI Plot (Panel 3)
        mpf.make_addplot(df['RSI'], panel=3, color='purple', ylabel='RSI (14)', secondary_y=False),
        mpf.make_addplot([70] * len(df), panel=3, color='gray', linestyle='--'),
        mpf.make_addplot([30] * len(df), panel=3, color='gray', linestyle='--'),

        # Stochastic Oscillator Plot (Panel 4)
        mpf.make_addplot(df['K_percent'], panel=4, color='green', secondary_y=False, ylabel='Stochastic'),
        mpf.make_addplot(df['D_percent'], panel=4, color='orange', secondary_y=False),
        mpf.make_addplot([80] * len(df), panel=4, color='red', linestyle='--'),  # Overbought
        mpf.make_addplot([20] * len(df), panel=4, color='green', linestyle='--'),  # Oversold

        # Rate of Change (ROC) Plot (Panel 5)
        mpf.make_addplot(df['ROC'], panel=5, color='teal', secondary_y=False, ylabel='ROC (14)'),
        mpf.make_addplot([0] * len(df), panel=5, color='gray', linestyle='-'),  # Zero Line
    ]

    # Insert the scatter plot for price markers if it exists
    if marker_scatter:
        apds.insert(0, marker_scatter)

    # 2. Define style and plot parameters
    s = mpf.make_marketcolors(up='green', down='red', inherit=True)
    custom_style = mpf.make_mpf_style(base_mpf_style='yahoo', marketcolors=s,
                                      rc={'figure.titlesize': 'x-large', 'figure.titleweight': 'semibold'})

    try:
        mpf.plot(
            df,
            type='candle',
            style=custom_style,
            title=f"{ticker} - {signal_title}",
            ylabel='Price ($)',
            volume=True,
            addplot=apds,
            figsize=(12, 12),
            savefig=dict(fname=chart_path, dpi=100)
        )
        print(f"  -> Chart created and saved to {chart_path}")
        return chart_path
    except Exception as e:
        print(f"ERROR: Failed to create chart for {ticker}: {e}")
        return None


# --- Core Analysis Functions ---

def get_sector_status(sector_ticker, start_date, end_date, window):
    """
    Checks if the sector ETF is in an uptrend (Close > SMA_window).
    Returns a tuple: (bool is_uptrend, str status_message)
    """
    status_message = f"Sector ETF check for {sector_ticker} ({window}-day SMA): "

    try:
        etf_data = yf.download(sector_ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)

        if etf_data.empty or 'Close' not in etf_data.columns or len(etf_data) < window:
            return False, status_message + "ERROR: Data empty or insufficient history for SMA."

        etf_data['SMA'] = etf_data['Close'].rolling(window=window).mean()

        latest_close = etf_data['Close'].iloc[-1]
        latest_sma = etf_data['SMA'].iloc[-1]

        if pd.isna(latest_sma):
            return False, status_message + "ERROR: SMA calculation resulted in NaN (data issue)."

        is_uptrend = latest_close > latest_sma

        if is_uptrend:
            status_message += f"UPTREND (Close ${latest_close:.2f} > SMA ${latest_sma:.2f})"
        else:
            status_message += f"DOWNTREND (Close ${latest_close:.2f} <= SMA ${latest_sma:.2f})"

        return is_uptrend, status_message

    except Exception as e:
        status_message += f"CRITICAL ERROR: Failed to fetch/calculate: {e}"
        # If there's any failure, assume the trend check is inconclusive/failed and filter bullish signals
        return False, status_message


def calculate_rsr(df_stock, market_ticker, sub_sector_ticker, window, start_date, end_date):
    """
    V2.0.0 ADDITION: Calculates Relative Strength Ranking (RSR) over the defined window
    against a Market Index and a Sub-Sector/Peer Index. RSR = (Stock ROC) / (Benchmark ROC)
    """
    rsr_results = {
        'Market_RSR': np.nan,
        'SubSector_RSR': np.nan,
        'Market_ROC': np.nan,
        'SubSector_ROC': np.nan,
        'Stock_ROC': np.nan
    }

    try:
        # 1. Fetch Benchmark Data
        benchmarks = [market_ticker, sub_sector_ticker]
        benchmark_data = yf.download(benchmarks, start=start_date, end=end_date, progress=False, auto_adjust=True)[
            'Close']

        if benchmark_data.empty:
            print("  -> RSR ERROR: Failed to fetch benchmark data.")
            return rsr_results

        # Ensure index alignment and merge stock close data
        df_stock_close = df_stock['Close'].rename('Stock_Close')
        # Use inner join to only compare dates where all data points exist
        rsr_df = pd.concat([df_stock_close, benchmark_data], axis=1).dropna()
        rsr_df.columns = ['Stock_Close', market_ticker, sub_sector_ticker]

        # Check for sufficient data
        if len(rsr_df) < window * 0.8:  # Allow some missing days, but require a minimum
            print("  -> RSR WARNING: Insufficient data for RSR calculation.")
            return rsr_results

        # 2. Calculate Rate of Change (Percentage Change over the window)
        # We use the first and last prices after alignment to calculate the total change
        if len(rsr_df) < 2:
            return rsr_results

        start_prices = rsr_df.iloc[0]
        end_prices = rsr_df.iloc[-1]

        # ROC = ((Price_t / Price_{t-n}) - 1)
        stock_roc = (end_prices['Stock_Close'] / start_prices['Stock_Close']) - 1
        market_roc = (end_prices[market_ticker] / start_prices[market_ticker]) - 1
        sub_sector_roc = (end_prices[sub_sector_ticker] / start_prices[sub_sector_ticker]) - 1

        # 3. Calculate RSR (RSR >= 1.0 means outperforming the benchmark)
        # Handle division by zero: if benchmark ROC is zero, RSR is inf (outperformance) or 0 (underperformance)
        def safe_rsr(stock_roc, benchmark_roc):
            if benchmark_roc == 0:
                return np.inf if stock_roc > 0 else 0
            return stock_roc / benchmark_roc

        market_rsr = safe_rsr(stock_roc, market_roc)
        sub_sector_rsr = safe_rsr(stock_roc, sub_sector_roc)

        rsr_results = {
            'Market_RSR': market_rsr,
            'SubSector_RSR': sub_sector_rsr,
            'Market_ROC': market_roc * 100,
            'SubSector_ROC': sub_sector_roc * 100,
            'Stock_ROC': stock_roc * 100
        }

    except Exception as e:
        print(f"  -> CRITICAL RSR ERROR: {e}")
        pass

    return rsr_results


def calculate_indicators(df, short_w, long_w, signal_w, stoch_k_w, stoch_d_w, bb_w, bb_sd):
    """
    Calculates MACD, MACD Signal Line, MACD Histogram, RSI, Stochastic Oscillator,
    ROC, and Bollinger Bands.
    """
    # ... (Indicator calculation logic remains the same as in V1.9.0)
    # MACD Calculation
    df['EMA_Short'] = df['Close'].ewm(span=short_w, adjust=False).mean()
    df['EMA_Long'] = df['Close'].ewm(span=long_w, adjust=False).mean()
    df['MACD'] = df['EMA_Short'] - df['EMA_Long']
    df['Signal_Line'] = df['MACD'].ewm(span=signal_w, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal_Line']

    # RSI Calculation (14-day window is standard)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
    with np.errstate(divide='ignore', invalid='ignore'):
        RS = gain / loss
        df['RSI'] = 100 - (100 / (1 + RS))
    df['RSI'] = df['RSI'].fillna(50)

    # Stochastic Oscillator Calculation (Fast K and Slow D)
    df['L_k'] = df['Low'].rolling(window=stoch_k_w).min()
    df['H_k'] = df['High'].rolling(window=stoch_k_w).max()

    with np.errstate(divide='ignore', invalid='ignore'):
        df['K_percent'] = 100 * ((df['Close'] - df['L_k']) / (df['H_k'] - df['L_k']))

    df['D_percent'] = df['K_percent'].rolling(window=stoch_d_w).mean()

    # Rate of Change (ROC) Calculation (14-period standard)
    ROC_WINDOW = 14
    df['ROC'] = df['Close'].pct_change(periods=ROC_WINDOW) * 100

    # Bollinger Bands Calculation
    df['BB_Middle'] = df['Close'].rolling(window=bb_w).mean()
    df['BB_Std'] = df['Close'].rolling(window=bb_w).std()
    df['BB_Upper'] = df['BB_Middle'] + (df['BB_Std'] * bb_sd)
    df['BB_Lower'] = df['BB_Middle'] - (df['BB_Std'] * bb_sd)

    # Clean up temporary columns
    df = df.drop(columns=['EMA_Short', 'EMA_Long', 'L_k', 'H_k', 'BB_Std'], errors='ignore')

    df = df.fillna(method='bfill')

    return df


def generate_signal(df, bb_filter_pct, is_sector_uptrend, rsr_results):
    """
    Checks for a crossover signal and applies the Bollinger Band, Sector Momentum,
    and Relative Strength Ranking filters.

    V2.0.0 UPDATE: Accepts and applies RSR filter logic.
    """

    recent_data = df.tail(LOOKBACK_DAYS)
    signals = {
        'MACD': {'type': None, 'description': None, 'date': None},
        'STOCH': {'type': None, 'description': None, 'date': None},
    }

    # 1. Detect Crossovers (MACD and STOCH)
    for i in range(1, len(recent_data)):
        macd_current = recent_data['MACD'].iloc[i]
        signal_current = recent_data['Signal_Line'].iloc[i]
        macd_prev = recent_data['MACD'].iloc[i - 1]
        signal_prev = recent_data['Signal_Line'].iloc[i - 1]
        current_date = recent_data.index[i].to_pydatetime()

        bullish_macd_crossover = (macd_prev < signal_prev) and (macd_current >= signal_current)
        bearish_macd_crossover = (macd_prev > signal_prev) and (macd_current <= signal_current)

        if bullish_macd_crossover:
            signals['MACD']['type'] = "MACD BULLISH"
            signals['MACD']['date'] = current_date
            signals['MACD'][
                'description'] = f"MACD BULLISH Crossover detected. MACD ({macd_current:.4f}) crossed the Signal Line ({signal_current:.4f}). Close: ${recent_data['Close'].iloc[i]:.2f}."
        elif bearish_macd_crossover:
            signals['MACD']['type'] = "MACD BEARISH"
            signals['MACD']['date'] = current_date
            signals['MACD'][
                'description'] = f"MACD BEARISH Crossover detected. MACD ({macd_current:.4f}) crossed the Signal Line ({signal_current:.4f}). Close: ${recent_data['Close'].iloc[i]:.2f}."

        k_current = recent_data['K_percent'].iloc[i]
        d_current = recent_data['D_percent'].iloc[i]
        k_prev = recent_data['K_percent'].iloc[i - 1]
        d_prev = recent_data['D_percent'].iloc[i - 1]

        stoch_bullish_crossover = (k_prev < d_prev) and (k_current >= d_current)
        stoch_bearish_crossover = (k_prev > d_prev) and (k_current <= d_prev) # Corrected logic: K% vs D% crossover

        if stoch_bullish_crossover and (k_prev < 20 or d_prev < 20):
            signals['STOCH']['type'] = "STOCH BULLISH"
            signals['STOCH']['date'] = current_date
            signals['STOCH'][
                'description'] = f"STOCH BULLISH Crossover detected (K% crossed D% in/near oversold territory). K%: {k_current:.2f}, D%: {d_current:.2f}. Close: ${recent_data['Close'].iloc[i]:.2f}."
        elif stoch_bearish_crossover and (k_prev > 80 or d_prev > 80):
            signals['STOCH']['type'] = "STOCH BEARISH"
            signals['STOCH']['date'] = current_date
            signals['STOCH'][
                'description'] = f"STOCH BEARISH Crossover detected (K% crossed D% in/near overbought territory). K%: {k_current:.2f}, D%: {d_current:.2f}. Close: ${recent_data['Close'].iloc[i]:.2f}."


    # 2. Find Most Recent Signal
    most_recent_signal = None
    most_recent_date = None
    most_recent_data_series = None
    all_signal_dates = {'MACD': [], 'STOCH': []}

    for signal_type, data in signals.items():
        if data['date'] is not None:
            all_signal_dates[signal_type].append(data['date'])
            if most_recent_date is None or data['date'] > most_recent_date:
                most_recent_date = data['date']
                most_recent_signal = data['type']
                signal_description = data['description']

    if most_recent_signal:
        signal_date_str = most_recent_date.strftime('%Y-%m-%d')
        if signal_date_str in df.index:
            most_recent_data_series = df.loc[signal_date_str]
        else:
            most_recent_data_series = df.iloc[-1]

        is_bullish = 'BULLISH' in most_recent_signal

        # --- 3. Apply Bollinger Band Filter (V1.8.0) ---
        signal_close = most_recent_data_series['Close']
        bb_mid = most_recent_data_series['BB_Middle']
        bb_upper = most_recent_data_series['BB_Upper']
        bb_lower = most_recent_data_series['BB_Lower']

        band_half_width = bb_upper - bb_mid
        filter_limit = band_half_width * (bb_filter_pct / 100)

        is_low_momentum = abs(signal_close - bb_mid) <= filter_limit
        is_overextended = (signal_close < bb_lower) or (signal_close > bb_upper)
        bb_status = ""

        if np.isnan(bb_mid) or np.isnan(bb_upper):
            bb_status = f"[BB Filter PASSED. BB data incomplete.]"
        elif is_low_momentum or is_overextended:
            filter_reason = "Bollinger Band Filter applied: "
            if is_low_momentum: filter_reason += f"Price (${signal_close:.2f}) too close to BB Middle (${bb_mid:.2f}). "
            if is_overextended: filter_reason += f"Price (${signal_close:.2f}) outside BB Bands (${bb_lower:.2f}/${bb_upper:.2f}). "
            print(f"  -> SIGNAL FILTERED OUT: {most_recent_signal} on {signal_date_str}. Reason: {filter_reason}")
            return None, None, None, None, all_signal_dates
        else:
            bb_status = f"[BB Filter PASSED. Close ${signal_close:.2f} OK.]"

        # --- 4. Apply Sector Momentum Filter (V1.9.0) ---
        sector_status = ""
        if is_bullish and not is_sector_uptrend:
            sector_status = "[Sector Filter APPLIED. BULLISH signal rejected due to Sector DOWNTREND.]"
            print(f"  -> SIGNAL FILTERED OUT: {most_recent_signal} on {signal_date_str}. Reason: {sector_status}")
            return None, None, None, None, all_signal_dates
        elif is_bullish:
            sector_status = "[Sector Filter PASSED. Sector is in an UPTREND.]"
        elif not is_bullish:
            sector_status = "[Sector Filter BYPASSED. Signal is BEARISH.]"

        # --- 5. Apply Relative Strength Ranking (RSR) Filter (V2.0.0) ---
        rsr_status = ""
        sub_sector_rsr = rsr_results.get('SubSector_RSR')

        if not np.isnan(sub_sector_rsr):
            # Check for leadership: RSR against sub-sector must be > 1.0 for a BULLISH signal
            is_leader = sub_sector_rsr > 1.0

            if is_bullish and not is_leader:
                rsr_status = (
                    f"[RSR Filter APPLIED. BULLISH signal rejected: Stock ROC ({rsr_results['Stock_ROC']:.2f}%) "
                    f"< Peer ROC ({rsr_results['SubSector_ROC']:.2f}%). RSR: {sub_sector_rsr:.2f}.]"
                )
                print(f"  -> SIGNAL FILTERED OUT: {most_recent_signal} on {signal_date_str}. Reason: {rsr_status}")
                return None, None, None, None, all_signal_dates

            elif is_bullish and is_leader:
                rsr_status = (
                    f"[RSR Filter PASSED. Stock is a LEADER. Sub-Sector RSR: {sub_sector_rsr:.2f} (Stock ROC: {rsr_results['Stock_ROC']:.2f}% vs Market RSR: {rsr_results['Market_RSR']:.2f}).]"
                )
            elif not is_bullish:
                # Log RSR info for bearish signals but do not filter them based on performance
                rsr_status = (
                    f"[RSR Check (BEARISH). Sub-Sector RSR: {sub_sector_rsr:.2f} (Stock ROC: {rsr_results['Stock_ROC']:.2f}% vs Market RSR: {rsr_results['Market_RSR']:.2f}).]"
                )
        else:
            rsr_status = "[RSR Check BYPASSED. Benchmark data incomplete/not mapped.]"

        # If it passes all filters, combine the statuses
        signal_description += f" {bb_status} {sector_status} {rsr_status}"

        return most_recent_signal, signal_description, most_recent_date, most_recent_data_series, all_signal_dates

    return None, None, None, None, all_signal_dates


# --- Email Functions (Omitted for brevity, but functional) ---

def create_email_message(sender, recipient, subject, body, attachment_path=None):
    """Creates a MIME message with optional attachment."""
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))
    signature = MIMEText("\n---\nAI/Quantum Momentum Tracker (v2.0.0)", 'plain')
    msg.attach(signature)

    if attachment_path:
        with open(attachment_path, 'rb') as fp:
            part = MIMEBase('application', "octet-stream")
            part.set_payload(fp.read())

        encoders.encode_base64(part)
        part.add_header('Content-Disposition',
                        f'attachment; filename="{os.path.basename(attachment_path)}"')
        msg.attach(part)

    return msg


def send_email_with_attachment(smtp_config, recipient_email, subject, body, attachment_path=None):
    """Sends an email using the provided SMTP configuration."""

    msg = create_email_message(
        smtp_config['sender_email'],
        recipient_email,
        subject,
        body,
        attachment_path
    )

    try:
        context = ssl.create_default_context()
        print(f"STATUS: Connecting to SMTP server {smtp_config['smtp_server']}:{smtp_config['smtp_port']}...")

        with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
            server.starttls(context=context)
            server.login(smtp_config['smtp_username'], smtp_config['smtp_password'])
            server.sendmail(smtp_config['sender_email'], recipient_email, msg.as_string())

        print(f"SUCCESS: Email '{subject}' sent successfully to {recipient_email}.")
        return True

    except smtplib.SMTPAuthenticationError:
        print("CRITICAL ERROR: SMTP Authentication failed. Check username and password in config.toml.")
    except smtplib.SMTPConnectError as e:
        print(f"CRITICAL ERROR: Could not connect to SMTP server: {e}")
    except smtplib.SMTPRecipientsRefused as e:
        print(f"CRITICAL ERROR: Recipient email address refused by server: {e}")
    except Exception as e:
        print(f"CRITICAL ERROR: An unknown error occurred while sending email: {e}")

    return False


def send_failure_report_email(smtp_config, failed_tickers_report):
    """Sends a consolidated email report of all tickers that failed processing."""
    recipient_email = smtp_config['recipient_email']
    body = "The following stocks failed data retrieval or database logging during the daily run:\n\n"
    body += "Ticker | Reason\n---|---\n"
    for ticker, reason in failed_tickers_report:
        body += f"{ticker} | {reason}\n"
    body += "\nReview the logs for full details."
    send_email_with_attachment(
        smtp_config,
        recipient_email,
        SMTP_REPORT_SUBJECT,
        body,
        attachment_path=None
    )


def send_signal_email(smtp_config, ticker, signal_type, signal_description, chart_path):
    """Sends a single signal email with the chart attached."""

    subject = f"🚨 Momentum Signal Detected: {ticker} - {signal_type}"
    body = (
        f"A strong momentum signal has been detected for {ticker}:\n\n"
        f"**Signal Type:** {signal_type}\n"
        f"**Date:** {date.today().strftime('%Y-%m-%d')}\n"
        f"**Details:** {signal_description}\n\n"
        f"The corresponding technical chart is attached for your review."
    )
    send_email_with_attachment(
        smtp_config,
        smtp_config['recipient_email'],
        subject,
        body,
        attachment_path=chart_path
    )


# --- Main Execution Logic ---

def main():
    """Main function to run the stock signal analysis and reporting."""
    print("================================================================")
    print(f"AI/QUANTUM MOMENTUM TRACKER START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"VERSION: 2.0.0 (Relative Strength Ranking Filter)")
    print("================================================================")

    # 0. Load Configuration and Tickers
    # V2.1.0: Parse arguments first to get the tickers file path
    tickers_file_path = parse_arguments()

    db_config, smtp_config, analysis_config, static_config = load_config()
    TICKERS_FILE = tickers_file_path # Use the path derived from the command line argument
    RECIPIENT_EMAIL = smtp_config['recipient_email']

    if not os.path.exists(CHART_DIR):
        os.makedirs(CHART_DIR)

    tickers = load_tickers(TICKERS_FILE)
    if not tickers:
        print("INFO: No tickers to process. Exiting.")
        return

    # 1. Initialize counters and lists
    total_tickers_processed = 0
    crossover_count = 0
    no_signal_count = 0
    failed_tickers_report = []
    charts_to_cleanup = []

    # 2. Configuration for Lookback and Indicators
    period_months = analysis_config['period_months']
    short_w = analysis_config['short_window']
    long_w = analysis_config['long_window']
    signal_w = analysis_config['signal_window']
    stoch_k_w = analysis_config['stoch_k_window']
    stoch_d_w = analysis_config['stoch_d_window']
    bb_w = analysis_config['bb_window']
    bb_sd = analysis_config['bb_std_dev']
    bb_filter_pct = analysis_config['bb_filter_pct']

    end_date = datetime.now().date()
    # Calculate start date, ensuring enough history for 200-day SMA and RSR window
    max_days_required = max(SECTOR_SMA_WINDOW, RSR_WINDOW_DAYS)
    required_months = max(period_months, math.ceil(max_days_required / 20) + 1)
    start_date = end_date - relativedelta(months=required_months)

    # 3. Process each ticker
    for ticker_line in tickers:
        total_tickers_processed += 1
        ticker_parts = ticker_line.split(' ', 1)
        actual_ticker = ticker_parts[0]

        if actual_ticker.startswith('#'):
            print(f"\nProcessing Header/Comment: {ticker_line} ({total_tickers_processed}/{len(tickers)})")
            continue

        print(f"\nProcessing Ticker: {ticker_line} ({total_tickers_processed}/{len(tickers)})")
        chart_path = None

        try:
            # --- Get Benchmark Tickers ---
            benchmark_pair = TICKER_BENCHMARK_MAP.get(actual_ticker)
            sector_ticker = benchmark_pair[0] if benchmark_pair else None
            sub_sector_ticker = benchmark_pair[1] if benchmark_pair else None

            # --- V1.9.0 Sector Momentum Check ---
            is_sector_uptrend = True
            sector_status_message = "Sector check N/A (No map entry found)."

            if sector_ticker:
                is_sector_uptrend, sector_status_message = get_sector_status(
                    sector_ticker, start_date, end_date, SECTOR_SMA_WINDOW
                )
            print(f"  -> Sector Status: {sector_status_message}")

            # --- Stock Data Retrieval ---
            download_result = yf.download(actual_ticker, start=start_date, end=end_date, progress=False,
                                          auto_adjust=True)

            if isinstance(download_result, tuple):
                data = download_result[0]
            else:
                data = download_result

            if not isinstance(data, pd.DataFrame) or data.empty:
                failure_reason = f"Data retrieval failed (yfinance returned non-DataFrame or empty data: {type(data)})."
                print(f"  -> CRITICAL ERROR: {failure_reason}")
                failed_tickers_report.append((ticker_line, failure_reason))
                continue

            # Defensive column handling
            data.columns = [col[0].capitalize() if isinstance(col, tuple) else col.capitalize() for col in data.columns]

            # Calculate indicators
            processed_df = calculate_indicators(data, short_w, long_w, signal_w, stoch_k_w, stoch_d_w, bb_w, bb_sd)

            # --- V2.0.0 RSR Calculation ---
            rsr_results = {
                'Market_RSR': np.nan, 'SubSector_RSR': np.nan,
                'Stock_ROC': np.nan, 'Market_ROC': np.nan, 'SubSector_ROC': np.nan
            }

            if sub_sector_ticker:
                rsr_start_date = end_date - relativedelta(days=RSR_WINDOW_DAYS)
                rsr_results = calculate_rsr(
                    processed_df.tail(RSR_WINDOW_DAYS),  # Pass only the data needed for RSR
                    MARKET_INDEX_TICKER,
                    sub_sector_ticker,
                    RSR_WINDOW_DAYS,
                    rsr_start_date,
                    end_date
                )
                print(f"  -> RSR Status: Stock ROC: {rsr_results['Stock_ROC']:.2f}%. "
                      f"Market RSR: {rsr_results['Market_RSR']:.2f}. "
                      f"Sub-Sector RSR: {rsr_results['SubSector_RSR']:.2f}.")

            # --- Signal Generation (Pass both filter flags/results) ---
            signal_type, signal_description, signal_date_dt, signal_data_series, all_signal_dates = generate_signal(
                processed_df, bb_filter_pct, is_sector_uptrend, rsr_results
            )

            if signal_type:
                crossover_count += 1
                print(f"  -> SIGNAL DETECTED: {signal_type} on {signal_date_dt.strftime('%Y-%m-%d')}")

                # Log Signal to Database
                db_success = log_signal_to_db(
                    db_config, actual_ticker, signal_type, signal_description, signal_date_dt.date(), signal_data_series
                )
                if not db_success:
                    failure_reason = "DB LOGGING FAILED (See previous error logs for details)"
                    failed_tickers_report.append((ticker_line, failure_reason))

                # Create Chart and Send Email
                plot_df = processed_df.tail(100)
                chart_path = create_chart(plot_df, actual_ticker, signal_type, all_signal_dates)

                if chart_path:
                    charts_to_cleanup.append(chart_path)
                    send_signal_email(smtp_config, actual_ticker, signal_type, signal_description, chart_path)
            else:
                no_signal_count += 1
                print(
                    "  -> No recent signal found, or signal was filtered out by Bollinger Bands/Sector Momentum/RSR.")
                pass

        except Exception as e:
            failure_reason = f"UNHANDLED EXCEPTION: {e}"
            print(f"  -> An unhandled error occurred while processing {ticker_line}: {failure_reason}")
            failed_tickers_report.append((ticker_line, failure_reason))

    # --- Final Reporting and Cleanup ---
    print("----------------------------------------------------------------")

    # Generate the status log file
    generate_status_log(TICKERS_FILE, total_tickers_processed, crossover_count, no_signal_count,
                        len(failed_tickers_report), analysis_config)

    # Send the consolidated failure report
    if failed_tickers_report:
        send_failure_report_email(smtp_config, failed_tickers_report)

    # Email the status log file
    status_subject = f"📈 Momentum Tracker Daily Summary: {datetime.now().strftime('%Y-%m-%d')}"
    status_body = (
        f"Daily processing complete.\n\n"
        f"**Signals Detected (MACD or STOCH) & Passed BB/Sector/RSR Filters:** {crossover_count}\n"
        f"**Processed (No Signal/Signal Filtered):** {no_signal_count}\n"
        f"**CRITICAL Failures (Data/Config):** {len(failed_tickers_report)}\n\n"
        f"The full execution summary is attached."
    )
    send_email_with_attachment(
        smtp_config,
        RECIPIENT_EMAIL,
        status_subject,
        status_body,
        attachment_path=STATUS_LOG_FILE
    )

    # File Cleanup
    print("\nStarting file cleanup...")
    if os.path.exists(STATUS_LOG_FILE):
        charts_to_cleanup.append(STATUS_LOG_FILE)

    for file_path in charts_to_cleanup:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"  -> Cleaned up: {file_path}")
        except Exception as e:
            print(f"  -> ERROR: Failed to clean up file {file_path}: {e}")

    print("================================================================")
    print("AI/QUANTUM MOMENTUM TRACKER END")
    print("================================================================")


if __name__ == "__main__":
    main()