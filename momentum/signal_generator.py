#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
signal_generator.py

================================================================================
PROJECT: AI/Quantum Tech Stock Momentum Tracker
AUTHOR: Matha Goram
DATE: 2025-11-11/2025-11-12
VERSION: 1.0.9
================================================================================

PURPOSE & METHODOLOGY:
--------------------
This script is designed to run automatically (e.g., via a daily cron job) to
monitor a list of high-tech stocks highly correlated with challenges and
breakthroughs in AI and Quantum computing.

It employs a common technical analysis strategy: the MACD (Moving Average
Convergence Divergence) crossover.
- A **BULLISH** signal is generated when the MACD line crosses **above** the
  Signal line, indicating upward momentum.
- A **BEARISH** signal is generated when the MACD line crosses **below** the
  Signal line, indicating downward momentum.

The Relative Strength Index (RSI) is calculated and charted for context but is
not used as a primary signal trigger in this version.

EXECUTION & OUTPUT:
------------------
1. Downloads 6 months of daily stock data via the yfinance API.
2. Calculates MACD (12, 26, 9) and RSI (14) for all monitored tickers.
3. If a momentum crossover is detected on the latest closing price, it generates:
    a. A high-resolution candlestick chart showing the price, volume, RSI, and MACD.
    b. An email alert containing the signal details and attaching the chart.
4. Charts for non-signaling tickers are cleaned up (deleted) after processing.

REQUIRED EXTERNAL FILES:
------------------------
1. config.toml: MUST be present and contain valid credentials for the LAN SMTP
   server for email delivery.
2. tickers.txt: MUST be present and contain a newline-separated list of stock
   tickers (e.g., NVDA, IONQ).

DEPENDENCIES (Install via pip):
-----------------------------
- yfinance: Stock data retrieval.
- pandas: Data manipulation and DataFrame management.
- toml: Secure parsing of the config.toml file.
- ta: Technical Analysis library for indicator calculation (RSI, MACD).
- mplfinance: High-quality financial candlestick charting.

SECURITY NOTE:
--------------
The script relies on `config.toml` for sensitive SMTP credentials. Ensure this
file is protected with restricted permissions and excluded from version control
(e.g., added to .gitignore). Never hardcode credentials within the script itself.
"""
import math
from datetime import datetime
from dateutil.relativedelta import relativedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import mplfinance as mpf
import numpy as np
import os
import pandas as pd
import smtplib
import ta
import toml
from typing import List, Dict, Tuple
import yfinance as yf

# --- Configuration ---
CONFIG_FILE = "config.toml"
TICKERS_FILE = "tickers.txt"


def load_config(filename: str) -> Dict:
    """Loads configuration from a TOML file."""
    try:
        return toml.load(filename)
    except FileNotFoundError:
        print(f"Error: Config file '{filename}' not found.")
        return {}
    except toml.TomlDecodeError as e:
        print(f"Error decoding TOML file: {e}")
        return {}


def load_tickers(filename: str) -> List[str]:
    """
    Reads the list of stock tickers from a file.
    It reads only the first token (word) on each line, ignoring the rest.
    """
    tickers = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                clean_line = line.strip()

                if not clean_line or clean_line.startswith('#'):
                    continue

                try:
                    # Reads only the first word and converts to uppercase
                    ticker = clean_line.split()[0].upper()
                    tickers.append(ticker)
                except IndexError:
                    continue

    except FileNotFoundError:
        print(f"Error: Tickers file '{filename}' not found.")
        return []

    print(f"Loaded {len(tickers)} tickers.")
    return tickers


def fetch_data(ticker: str, period_months: int) -> pd.DataFrame:
    """
    Fetches historical stock data using yfinance and ensures the output
    is a clean, flat DataFrame for indicator calculation.
    """
    # Use the execution date from your logs (Nov 11, 2025) for consistency in future data runs
    end_date = datetime(2025, 11, 11)
    start_date = end_date - relativedelta(months=period_months)

    print(f"  -> Fetching data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")

    df = yf.download(
        ticker,
        start=start_date.strftime('%Y-%m-%d'),
        end=end_date.strftime('%Y-%m-%d'),
        interval="1d",
        auto_adjust=True,
        progress=False
    )

    if df.empty:
        return df

    # --- Ensure Flat DataFrame Structure (Essential for resolving ambiguity) ---
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten MultiIndex columns, prioritizing the 'Close' column via Adj Close
        if 'Adj Close' in df.columns.get_level_values(0):
            df = df['Adj Close']
        else:
            df.columns = df.columns.get_level_values(0)

    # Ensure we only keep the expected columns after potential multi-index flattening
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    valid_columns = [col for col in required_columns if col in df.columns]
    df = df[valid_columns]

    # Final check to ensure the index is a datetime index
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    return df


def add_indicators(df: pd.DataFrame, short_w=12, long_w=26, signal_w=9) -> pd.DataFrame:
    """Adds technical indicators (RSI and MACD) and EMAs to the DataFrame."""
    if df.empty:
        return df

    # --- Exponential Moving Averages (EMAs) ---
    # 10-day EMA (Short-term trend) - Fast EMA
    df['EMA10'] = df['Close'].ewm(span=10, adjust=False).mean()
    # 50-day EMA (Medium-term trend) - Slow EMA
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()

    # Relative Strength Index (RSI)
    df['RSI'] = ta.momentum.RSIIndicator(df['Close']).rsi()

    # Moving Average Convergence Divergence (MACD)
    macd_indicator = ta.trend.MACD(
        close=df['Close'],
        window_fast=short_w,
        window_slow=long_w,
        window_sign=signal_w
    )
    df['MACD'] = macd_indicator.macd()
    df['MACD_Signal'] = macd_indicator.macd_signal()

    return df


def generate_signal(df: pd.DataFrame) -> Tuple[str, str]:
    """
    Generates a simple bullish or bearish signal based on the last row.
    """
    if df.empty or len(df) < 2:
        return "", "Not enough data for signal generation."

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    try:
        # Get scalar values for the current day
        l_macd = latest['MACD'].item()
        l_signal = latest['MACD_Signal'].item()
        l_rsi = latest['RSI'].item()

        # Get scalar values for the previous day
        p_macd = prev['MACD'].item()
        p_signal = prev['MACD_Signal'].item()

    except ValueError:
        # Catches if .item() fails on a NaN value
        return "", "Indicators not calculated for the latest period (data is NaN)."

    except IndexError:
        # Catches if iloc[-1] or iloc[-2] fails
        return "", "Not enough data for comparison."

    signal_type = ""
    description = "No clear momentum signal."

    # MACD Crossover Signal
    macd_crossover_up = (l_macd > l_signal) and (p_macd <= p_signal)
    if macd_crossover_up and l_rsi < 70:
        signal_type = "MACD BULLISH"
        description = "MACD crossed above its signal line (Buy signal)."

    macd_crossover_down = (l_macd < l_signal) and (p_macd >= p_signal)
    if macd_crossover_down and l_rsi > 30:
        signal_type = "MACD BEARISH"
        description = "MACD crossed below its signal line (Sell signal)."

    return signal_type, description


def get_macd_crossover_markers(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Identifies MACD crossover points and returns two separate Series for plotting
    bullish and bearish markers at the MACD Signal line value.
    """
    # Calculate the difference between MACD and Signal for the whole period
    diff = df['MACD'] - df['MACD_Signal']

    # Identify crossover conditions
    bullish_cross = (diff > 0) & (diff.shift(1) <= 0)
    bearish_cross = (diff < 0) & (diff.shift(1) >= 0)

    # Create marker Series for bullish crosses (NaN except on cross days)
    bullish_markers = pd.Series(np.nan, index=df.index)
    bullish_markers[bullish_cross] = df['MACD_Signal'][bullish_cross]

    # Create marker Series for bearish crosses (NaN except on cross days)
    bearish_markers = pd.Series(np.nan, index=df.index)
    bearish_markers[bearish_cross] = df['MACD_Signal'][bearish_cross]

    return bullish_markers, bearish_markers


def get_ema_crossover_markers(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Identifies EMA crossover points and returns two separate Series for plotting
    bullish and bearish markers at the level of the crossover price.
    """
    # Calculate the difference between the Fast EMA (10) and Slow EMA (50)
    diff = df['EMA10'] - df['EMA50']

    # Identify crossover conditions
    # Bullish: Fast EMA is currently above Slow EMA, and was below in the previous period
    bullish_cross = (diff > 0) & (diff.shift(1) <= 0)
    # Bearish: Fast EMA is currently below Slow EMA, and was above in the previous period
    bearish_cross = (diff < 0) & (diff.shift(1) >= 0)

    # Create marker Series for bullish crosses (NaN except on cross days). Marker value is set to the price of the 50-day EMA
    bullish_markers = pd.Series(np.nan, index=df.index)
    bullish_markers[bullish_cross] = df['EMA50'][bullish_cross]

    # Create marker Series for bearish crosses (NaN except on cross days). Marker value is set to the price of the 50-day EMA
    bearish_markers = pd.Series(np.nan, index=df.index)
    bearish_markers[bearish_cross] = df['EMA50'][bearish_cross]

    return bullish_markers, bearish_markers


def create_chart(df: pd.DataFrame, ticker: str, signal_type: str) -> str:
    """Generates a candlestick chart with EMAs, RSI and MACD and saves it to a file."""

    # --- FILENAME: Ticker suffixed ---
    filename = f"signal_chart_{ticker}.png"

    # Initialize the addplots list
    addplots = []

    # 1. EMA Addplots (Added to the main panel=0)
    addplots.append(mpf.make_addplot(
        df['EMA10'],
        color='gold',
        panel=0,
        width=1.0
    ))

    addplots.append(mpf.make_addplot(
        df['EMA50'],
        color='purple',
        panel=0,
        width=1.5
    ))

    # 2. EMA Crossover Markers (Added to the main panel=0)
    ema_bullish_markers, ema_bearish_markers = get_ema_crossover_markers(df)

    # --- FIX: Conditionally add the scatter plots to avoid 'zero-size array' error ---

    # Bullish EMA markers (Green up-arrow)
    # Only plot if there is at least one non-NaN marker
    if not ema_bullish_markers.isnull().all():
        addplots.append(mpf.make_addplot(
            ema_bullish_markers,
            type='scatter',
            panel=0,  # Plot on the main price chart
            markersize=250,
            marker='^',
            color='green'
        ))

    # Bearish EMA markers (Brown down-arrow)
    # Only plot if there is at least one non-NaN marker
    if not ema_bearish_markers.isnull().all():
        addplots.append(mpf.make_addplot(
            ema_bearish_markers,
            type='scatter',
            panel=0,  # Plot on the main price chart
            markersize=250,
            marker='v',
            color='brown'
        ))

    # 3. RSI Addplot (Panel 1)
    addplots.append(mpf.make_addplot(
        df['RSI'],
        panel=1,
        ylabel='RSI',
        y_on_right=False
    ))

    # 4. MACD Addplots (Panel 2)
    addplots.append(mpf.make_addplot(
        df['MACD'],
        panel=2,
        color='blue',
        ylabel='MACD'
    ))

    addplots.append(mpf.make_addplot(
        df['MACD_Signal'],
        panel=2,
        color='red'
    ))

    # 5. MACD Crossover Markers (Added to panel=2)
    macd_bullish_markers, macd_bearish_markers = get_macd_crossover_markers(df)

    # Bullish MACD markers (Green up-arrow)
    # Only plot if there is at least one non-NaN marker
    if not macd_bullish_markers.isnull().all():
        addplots.append(mpf.make_addplot(
            macd_bullish_markers,
            type='scatter',
            panel=2,
            markersize=150,
            marker='^',
            color='green'
        ))

    # Bearish MACD markers (Brown down-arrow)
    # Only plot if there is at least one non-NaN marker
    if not macd_bearish_markers.isnull().all():
        addplots.append(mpf.make_addplot(
            macd_bearish_markers,
            type='scatter',
            panel=2,
            markersize=150,
            marker='v',
            color='brown'
        ))

    # 6. Plot Configuration
    hlines_rsi = dict(hlines=[30, 70], colors=['r', 'r'], linestyle='-.', alpha=0.5, linewidths=0.5)

    # Plot highlight for the last day's signal (vertical line)
    vlines_signal = None
    if signal_type:
        signal_date = df.index[-1].to_pydatetime()
        color = 'g' if 'BULLISH' in signal_type else 'r'
        vlines_signal = dict(vlines=[signal_date], colors=color, linewidths=1.5, alpha=0.8)

    plot_kwargs = {
        'type': 'candle',
        'style': 'yahoo',
        'title': f"{ticker} Momentum Analysis ({signal_type or 'No Signal'})",
        'volume': True,
        'addplot': addplots,
        'figscale': 1.5,
        'hlines': hlines_rsi,
        'savefig': filename
    }

    if vlines_signal is not None:
        plot_kwargs['vlines'] = vlines_signal

    try:
        mpf.plot(
            df,
            **plot_kwargs
        )
        print(f"  -> Chart saved as {filename}")
        return filename
    except Exception as e:
        print(f"  -> Error plotting chart for {ticker}. Check data quality: {e}")
        return ""


def send_email(config: Dict, ticker: str, signal_type: str, description: str, chart_path: str):
    """Sends an email alert with the signal and the chart."""

    # ... [Email parameters and logic, which are outside the current scope of fixing]
    # We skip the full SMTP block as per user's confirmation that the server is offline.
    print(f"  -> Skipping email for {ticker}: SMTP server is offline.")


def main():
    """Main execution function."""
    config = load_config(CONFIG_FILE)
    if not config:
        return

    # --- FIX for QSocketNotifier: Set environment variables for non-GUI plotting ---
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['QT_NO_LIBREPLACE'] = '1'

    required_sections = ['analysis', 'email']
    for section in required_sections:
        if section not in config:
            print(f"Configuration Error: Missing required section '[{section}]' in '{CONFIG_FILE}'.")
            return

    tickers = load_tickers(TICKERS_FILE)
    if not tickers:
        print("No tickers loaded. Exiting.")
        return

    analysis_cfg = config['analysis']

    for ticker in tickers:
        print(f"\nProcessing {ticker}...")
        chart_path = ""
        try:
            # 1. Fetch Data
            df = fetch_data(ticker, analysis_cfg['period_months'])

            # --- Data Validation (Check 1: Download success) ---
            if df.empty or df['Close'].isnull().all():
                print(f"  -> Skipping {ticker}: No valid historical data found or data is empty.")
                continue

            # 2. Add Indicators
            processed_df = add_indicators(
                df,
                analysis_cfg['short_window'],
                analysis_cfg['long_window'],
                analysis_cfg['signal_window']
            )

            # 3. Generate Signal
            signal_type, signal_description = generate_signal(processed_df)
            print(f"  -> Signal: {signal_type or 'Neutral'} ({signal_description})")

            # --- Data Validation (Check 2: Plotting Readiness) ---
            plot_df = processed_df.tail(100)

            if plot_df['Close'].isnull().all() or plot_df.empty:
                print(f"  -> Skipping {ticker}: Last 100 bars contain no valid 'Close' price data after processing.")
                continue

            # Use the robust .item() check for the last RSI value
            try:
                if np.isnan(plot_df['RSI'].iloc[-1].item()):
                    print(
                        f"  -> Skipping {ticker}: RSI indicator is NaN for the latest period (check period_months/data size).")
                    continue
            except (ValueError, IndexError):
                print(
                    f"  -> Skipping {ticker}: Failed to extract last RSI value for validation.")
                continue

            # 4. Create Chart
            chart_path = create_chart(plot_df, ticker, signal_type)

            # 5. Send Email (Only send if a chart was successfully created)
            if chart_path:
                send_email(config, ticker, signal_type, signal_description, chart_path)

        except Exception as e:
            # This is the catch-all for all other errors.
            print(f"  -> An unhandled error occurred while processing {ticker}: {e}")

        finally:
            # Cleanup: Delete the chart file after processing (now commented out for persistence)
            if chart_path and os.path.exists(chart_path):
                os.remove(chart_path)
                # pass

if __name__ == "__main__":
    main()