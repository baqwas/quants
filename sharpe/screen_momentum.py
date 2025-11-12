#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@brief: A stock screener script that fetches financial data for S&P 500 stocks, calculates key metrics, and sends an email alert with the results.
@details: This script uses the yfinance library to download stock data, calculates metrics such as EPS growth, sales growth, ROE, relative strength, and price near 52-week high. It then sends an email with the results using a configured SMTP server.
@note: Ensure you have the required libraries installed: yfinance, pandas, matplotlib, smtplib, email.mime.
@note: The script reads configuration from a config.ini file, which should contain SMTP server details and screening criteria.
@version: 1.0
@date: 2023-10-01
@license: MIT License
@contact:
    Math Goram

@reference: https://ranaroussi.github.io/yfinance/
"""
import argparse
import configparser
import csv
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import io
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import smtplib
import time
import yfinance as yf

# --- Configuration ---
config = configparser.ConfigParser()

try:
    config.read('config.ini')

    SMTP_SERVER = config['email'].get('smtp_server', fallback="bezaman.parkcircus.org")
    SENDER_EMAIL = config['email'].get('sender_email', fallback="chowkidar@parkcircus.org")
    RECIPIENT_EMAIL = config['email'].get('recipient_email', fallback="reza@parkcircus.org")
    SMTP_PASSWORD = config['email'].get('smtp_password',
                                        fallback="your_email_password")  # Make sure this is a valid password
    SMTP_PORT = config['email'].getint('smtp_port', fallback=587)

except KeyError as e:
    print(f"Error reading config.ini: Missing section or key: {e}. Falling back to hardcoded values.")
except FileNotFoundError:
    print(
        "config.ini not found. Please ensure it's in the same directory as the script. Falling back to hardcoded values.")
except Exception as e:
    print(f"An unexpected error occurred while reading the config file: {e}. Falling back to hardcoded values.")

# Screening criteria (with fallbacks)
EPS_GROWTH_ANNUAL_THRESHOLD = config["criteria"].getfloat("EPS_GROWTH_ANNUAL_THRESHOLD", fallback=0.25)
SALES_GROWTH_ANNUAL_THRESHOLD = config["criteria"].getfloat("SALES_GROWTH_ANNUAL_THRESHOLD", fallback=0.2)
ROE_THRESHOLD = config["criteria"].getfloat("ROE_THRESHOLD", fallback=0.15)
PRICE_NEAR_52W_HIGH_PERCENTAGE = config["criteria"].getfloat("PRICE_NEAR_52W_HIGH_PERCENTAGE", fallback=0.95)
AVG_VOLUME_MINIMUM = config["criteria"].getint("AVG_VOLUME_MINIMUM", fallback=500000)
SCREENER_TICKER_FILE = config["criteria"].get("screener_file", fallback="screener2.csv")

DOWNLOAD_DELAY_SECONDS = 0.5
STOCK_PROCESSING_DELAY_SECONDS = 1


# --- Helper Functions ---
def get_sp500_tickers():
    """
    Reads the list of S&P 500 tickers from the configured screener file.
    The ticker symbol is in the 3rd column.
    """
    tickers = []
    try:
        with open(SCREENER_TICKER_FILE, 'r') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                if len(row) > 2:
                    tickers.append(row[2])
    except FileNotFoundError:
        print(
            f"{SCREENER_TICKER_FILE} not found. Please ensure it's in the same directory as the script. Returning a default list of tickers.")
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'JPM', 'V', 'PG', 'HD', 'TSLA']  # Fallback list
    return tickers


def calculate_ytd_return(data):
    if data.empty or 'Close' not in data.columns or data['Close'].empty or data['Close'].isnull().all():
        return 0.0
    start_price = data['Close'].iloc[0]
    end_price = data['Close'].iloc[-1]
    return (end_price - start_price) / start_price if start_price else 0.0


def plot_momentum(data, ticker, crossover_type=None):
    if data.empty or 'Close' not in data.columns or data['Close'].empty or data['Close'].isnull().all():
        return None

    data['SMA_50'] = data['Close'].rolling(window=50).mean()
    data['SMA_200'] = data['Close'].rolling(window=200).mean()

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(data.index, data['Close'], label=f'{ticker} Close Price', color='blue')
    ax.plot(data.index, data['SMA_50'], label='50-Day SMA', color='orange')
    ax.plot(data.index, data['SMA_200'], label='200-Day SMA', color='red')

    title_suffix = ""
    if crossover_type == "bullish":
        title_suffix = " (Recent Bullish Crossover)"
    elif crossover_type == "bearish":
        title_suffix = " (Recent Bearish Crossover)"

    ax.set_title(f'{ticker} Stock Price and Moving Averages{title_suffix}')
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.legend()
    ax.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf


def check_bullish_crossover(data, lookback_days=3):
    """
    Checks for a 50-day SMA crossing above the 200-day SMA within the last `lookback_days`.
    Returns True if crossover occurred on any of the last `lookback_days`, False otherwise.
    """
    # Ensure enough data for 200-day SMA calculation plus the lookback period
    if data.empty or len(data) < 200 + lookback_days + 1:  # +1 for previous day in comparison
        return False

    data['SMA_50'] = data['Close'].rolling(window=50, min_periods=1).mean()
    data['SMA_200'] = data['Close'].rolling(window=200, min_periods=1).mean()

    # Iterate backwards from the latest data point
    for i in range(1, lookback_days + 1):
        # Calculate indices for current and previous day within the lookback window
        current_idx = -i
        previous_idx = -i - 1

        # Check if indices are valid and SMAs are not NaN
        if abs(previous_idx) > len(data) - 1 or \
                pd.isna(data['SMA_50'].iloc[current_idx]) or pd.isna(data['SMA_200'].iloc[current_idx]) or \
                pd.isna(data['SMA_50'].iloc[previous_idx]) or pd.isna(data['SMA_200'].iloc[previous_idx]):
            continue

        latest_sma50 = data['SMA_50'].iloc[current_idx]
        latest_sma200 = data['SMA_200'].iloc[current_idx]
        previous_sma50 = data['SMA_50'].iloc[previous_idx]
        previous_sma200 = data['SMA_200'].iloc[previous_idx]

        # Check for bullish crossover condition
        if (previous_sma50 <= previous_sma200) and (latest_sma50 > latest_sma200):
            return True  # Bullish crossover found within lookback

    return False


def check_bearish_crossover(data, lookback_days=3):
    """
    Checks for a 50-day SMA crossing below the 200-day SMA within the last `lookback_days`.
    Returns True if crossover occurred on any of the last `lookback_days`, False otherwise.
    """
    # Ensure enough data for 200-day SMA calculation plus the lookback period
    if data.empty or len(data) < 200 + lookback_days + 1:  # +1 for previous day in comparison
        return False

    data['SMA_50'] = data['Close'].rolling(window=50, min_periods=1).mean()
    data['SMA_200'] = data['Close'].rolling(window=200, min_periods=1).mean()

    # Iterate backwards from the latest data point
    for i in range(1, lookback_days + 1):
        # Calculate indices for current and previous day within the lookback window
        current_idx = -i
        previous_idx = -i - 1

        # Check if indices are valid and SMAs are not NaN
        if abs(previous_idx) > len(data) - 1 or \
                pd.isna(data['SMA_50'].iloc[current_idx]) or pd.isna(data['SMA_200'].iloc[current_idx]) or \
                pd.isna(data['SMA_50'].iloc[previous_idx]) or pd.isna(data['SMA_200'].iloc[previous_idx]):
            continue

        latest_sma50 = data['SMA_50'].iloc[current_idx]
        latest_sma200 = data['SMA_200'].iloc[current_idx]
        previous_sma50 = data['SMA_50'].iloc[previous_idx]
        previous_sma200 = data['SMA_200'].iloc[previous_idx]

        # Check for bearish crossover condition
        if (previous_sma50 >= previous_sma200) and (latest_sma50 < latest_sma200):
            return True  # Bearish crossover found within lookback

    return False


# --- New Plotting Functions for Indicators ---

def plot_rsi(data, ticker, window=14):
    if data.empty or 'Close' not in data.columns or len(data) < window:
        return None

    # Ensure Close prices are numeric, drop NaN if any
    close_prices = pd.to_numeric(data['Close'], errors='coerce').dropna()
    if close_prices.empty or len(close_prices) < window:
        return None

    delta = close_prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()

    # Handle cases where avg_loss might be zero to avoid division by zero
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # Align RSI to the original data index
    data_with_rsi = data.copy()
    data_with_rsi['RSI'] = rsi.reindex(data.index)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(data_with_rsi.index, data_with_rsi['RSI'], label=f'{ticker} RSI', color='purple')
    ax.axhline(70, linestyle='--', alpha=0.6, color='red', label='Overbought (70)')
    ax.axhline(30, linestyle='--', alpha=0.6, color='green', label='Oversold (30)')
    ax.set_title(f'{ticker} Relative Strength Index (RSI)')
    ax.set_xlabel('Date')
    ax.set_ylabel('RSI Value')
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf


def plot_macd(data, ticker, fast_period=12, slow_period=26, signal_period=9):
    if data.empty or 'Close' not in data.columns or len(data) < slow_period:
        return None

    close_prices = pd.to_numeric(data['Close'], errors='coerce').dropna()
    if close_prices.empty or len(close_prices) < slow_period:
        return None

    ema_fast = close_prices.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close_prices.ewm(span=slow_period, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    # Align to the original data index for plotting
    data_with_macd = data.copy()
    data_with_macd['MACD_Line'] = macd_line.reindex(data.index)
    data_with_macd['Signal_Line'] = signal_line.reindex(data.index)
    data_with_macd['Histogram'] = histogram.reindex(data.index)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(data_with_macd.index, data_with_macd['MACD_Line'], label='MACD Line', color='blue')
    ax.plot(data_with_macd.index, data_with_macd['Signal_Line'], label='Signal Line', color='red')
    ax.bar(data_with_macd.index, data_with_macd['Histogram'], label='Histogram', color='gray', alpha=0.7)
    ax.set_title(f'{ticker} Moving Average Convergence Divergence (MACD)')
    ax.set_xlabel('Date')
    ax.set_ylabel('Value')
    ax.legend()
    ax.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf


def plot_roc(data, ticker, window=12):
    if data.empty or 'Close' not in data.columns or len(data) < window + 1:  # need window + 1 for shift
        return None

    close_prices = pd.to_numeric(data['Close'], errors='coerce').dropna()
    if close_prices.empty or len(close_prices) < window + 1:
        return None

    roc_val = ((close_prices - close_prices.shift(window)) / close_prices.shift(window)) * 100

    data_with_roc = data.copy()
    data_with_roc['ROC'] = roc_val.reindex(data.index)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(data_with_roc.index, data_with_roc['ROC'], label=f'{ticker} ROC', color='darkgreen')
    ax.axhline(0, linestyle='--', alpha=0.6, color='gray')
    ax.set_title(f'{ticker} Rate of Change (ROC)')
    ax.set_xlabel('Date')
    ax.set_ylabel('ROC (%)')
    ax.legend()
    ax.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf


def plot_cmo(data, ticker, window=14):
    if data.empty or 'Close' not in data.columns or len(data) < window + 1:  # need window + 1 for diff then sum
        return None

    close_prices = pd.to_numeric(data['Close'], errors='coerce').dropna()
    if close_prices.empty or len(close_prices) < window + 1:
        return None

    diff = close_prices.diff()
    sum_up = diff.where(diff > 0, 0).rolling(window=window).sum()
    sum_down = -diff.where(diff < 0, 0).rolling(window=window).sum()

    # Handle cases where sum_up + sum_down might be zero
    cmo_val = (sum_up - sum_down) / (sum_up + sum_down).replace(0, np.nan) * 100

    data_with_cmo = data.copy()
    data_with_cmo['CMO'] = cmo_val.reindex(data.index)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(data_with_cmo.index, data_with_cmo['CMO'], label=f'{ticker} CMO', color='teal')
    ax.axhline(0, linestyle='--', alpha=0.6, color='gray')
    ax.axhline(50, linestyle='--', alpha=0.6, color='red', label='Overbought (50)')
    ax.axhline(-50, linestyle='--', alpha=0.6, color='green', label='Oversold (-50)')
    ax.set_title(f'{ticker} Chande Momentum Oscillator (CMO)')
    ax.set_xlabel('Date')
    ax.set_ylabel('CMO Value')
    ax.set_ylim(-100, 100)
    ax.legend()
    ax.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf


def get_stock_metrics(ticker, sp500_returns):
    metrics = {
        'ticker': ticker,
        'eps_growth_annual': 0.0,
        'sales_growth_annual': 0.0,
        'roe': 0.0,
        'relative_strength': 0.0,
        'price_near_52w_high': 0.0,
        'avg_daily_volume': 0,
        'plot': None,
        'bullish_crossover_recent': False,  # Renamed to reflect recent check
        'bearish_crossover_recent': False,  # Renamed to reflect recent check
        'rsi_plot': None,
        'macd_plot': None,
        'roc_plot': None,
        'cmo_plot': None
    }
    try:
        stock = yf.Ticker(ticker)

        end_date = datetime.now()
        # Fetch enough data for 200-day SMA + a buffer for the 3-day lookback
        start_date_required = end_date - timedelta(days=365 + 10)  # 1 year + 10 days buffer
        data_full = yf.download(ticker, start=start_date_required, end=end_date, progress=False, auto_adjust=True)
        time.sleep(DOWNLOAD_DELAY_SECONDS)

        if data_full.empty:
            return metrics
        if isinstance(data_full.columns, pd.MultiIndex):
            data_full.columns = data_full.columns.get_level_values(0)
        if 'Close' not in data_full.columns and 'Adj Close' in data_full.columns:
            data_full = data_full.rename(columns={'Adj Close': 'Close'})
        if 'Close' not in data_full.columns or data_full['Close'].empty or data_full['Close'].isnull().all():
            return metrics

        # Check for both types of crossovers over the last 3 days
        metrics['bullish_crossover_recent'] = check_bullish_crossover(data_full.copy(), lookback_days=3)
        metrics['bearish_crossover_recent'] = check_bearish_crossover(data_full.copy(), lookback_days=3)

        current_year_start = datetime(end_date.year, 1, 1)
        ytd_data = yf.download(ticker, start=current_year_start, end=end_date, progress=False, auto_adjust=True)
        time.sleep(DOWNLOAD_DELAY_SECONDS)

        if isinstance(ytd_data.columns, pd.MultiIndex):
            ytd_data.columns = ytd_data.columns.get_level_values(0)
        if 'Close' not in ytd_data.columns and 'Adj Close' in ytd_data.columns:
            ytd_data = ytd_data.rename(columns={'Adj Close': 'Close'})

        stock_ytd_return = calculate_ytd_return(ytd_data)

        sp500_ytd_return = sp500_returns.get('^GSPC', 0.0)
        metrics['relative_strength'] = stock_ytd_return - sp500_ytd_return

        if not data_full.empty and 'Close' in data_full.columns and not data_full['Close'].isnull().all():
            price_52w_high = data_full['Close'].max()
            current_price = data_full['Close'].iloc[-1]
            if price_52w_high > 0:
                metrics['price_near_52w_high'] = current_price / price_52w_high
            else:
                metrics['price_near_52w_high'] = 0.0
        else:
            metrics['price_near_52w_high'] = 0.0

        data_30d = yf.download(ticker, period='30d', interval='1d', progress=False, auto_adjust=True)
        time.sleep(DOWNLOAD_DELAY_SECONDS)

        if isinstance(data_30d.columns, pd.MultiIndex):
            data_30d.columns = data_30d.columns.get_level_values(0)

        if not data_30d.empty and 'Volume' in data_30d.columns and not data_30d['Volume'].isnull().all():
            metrics['avg_daily_volume'] = data_30d['Volume'].mean()
        else:
            metrics['avg_daily_volume'] = 0

        financials = stock.financials
        balance_sheet = stock.balance_sheet
        time.sleep(DOWNLOAD_DELAY_SECONDS)

        if not financials.empty and 'Net Income' in financials.index and len(financials.columns) >= 2:
            current_net_income = financials.loc['Net Income'].iloc[0]
            previous_net_income = financials.loc['Net Income'].iloc[1]
            if pd.notna(current_net_income) and pd.notna(previous_net_income):
                if previous_net_income != 0:
                    metrics['eps_growth_annual'] = (current_net_income - previous_net_income) / previous_net_income
                elif current_net_income > 0:
                    metrics['eps_growth_annual'] = 1.0
                else:
                    metrics['eps_growth_annual'] = 0.0
            else:
                metrics['eps_growth_annual'] = 0.0
        else:
            metrics['eps_growth_annual'] = 0.0

        if not financials.empty and 'Total Revenue' in financials.index and len(financials.columns) >= 2:
            current_revenue = financials.loc['Total Revenue'].iloc[0]
            previous_revenue = financials.loc['Total Revenue'].iloc[1]
            if pd.notna(current_revenue) and pd.notna(previous_revenue):
                if previous_revenue != 0:
                    metrics['sales_growth_annual'] = (current_revenue - previous_revenue) / previous_revenue
                elif current_revenue > 0:
                    metrics['sales_growth_annual'] = 1.0
                else:
                    metrics['sales_growth_annual'] = 0.0
            else:
                metrics['sales_growth_annual'] = 0.0
        else:
            metrics['sales_growth_annual'] = 0.0

        if (not financials.empty and 'Net Income' in financials.index and
                not balance_sheet.empty and 'Total Stockholder Equity' in balance_sheet.index):
            net_income = financials.loc['Net Income'].iloc[0]
            shareholder_equity = balance_sheet.loc['Total Stockholder Equity'].iloc[0]

            if pd.notna(net_income) and pd.notna(shareholder_equity) and shareholder_equity > 0:
                metrics['roe'] = net_income / shareholder_equity
            else:
                metrics['roe'] = 0.0
        else:
            metrics['roe'] = 0.0

        # Only generate plots if either a bullish or bearish crossover happened recently
        if metrics['bullish_crossover_recent'] or metrics['bearish_crossover_recent']:
            crossover_type_for_plot = "bullish" if metrics['bullish_crossover_recent'] else "bearish"
            metrics['plot'] = plot_momentum(data_full, ticker, crossover_type_for_plot)
            metrics['rsi_plot'] = plot_rsi(data_full, ticker)
            metrics['macd_plot'] = plot_macd(data_full, ticker)
            metrics['roc_plot'] = plot_roc(data_full, ticker)
            metrics['cmo_plot'] = plot_cmo(data_full, ticker)


    except Exception as e:
        print(f"An unexpected error occurred for {ticker}: {e}")
        return metrics

    return metrics


def run_screener():
    sp500_tickers = get_sp500_tickers()
    all_stocks_metrics = []  # Renamed to store all metrics temporarily

    sp500_data = pd.DataFrame()
    try:
        sp500_data = yf.download('^GSPC', start=datetime(datetime.now().year, 1, 1), end=datetime.now(),
                                 progress=False, auto_adjust=True)
        time.sleep(DOWNLOAD_DELAY_SECONDS)

        if sp500_data.empty:
            sp500_ytd_return_val = 0.0
        else:
            if isinstance(sp500_data.columns, pd.MultiIndex):
                sp500_data.columns = sp500_data.columns.get_level_values(0)
            if 'Close' not in sp500_data.columns and 'Adj Close' in sp500_data.columns:
                sp500_data = sp500_data.rename(columns={'Adj Close': 'Close'})
            sp500_ytd_return_val = calculate_ytd_return(sp500_data)

    except Exception as e:
        print(f"Error downloading S&P 500 data (^GSPC): {e}")
        sp500_data = pd.DataFrame()
        sp500_ytd_return_val = 0.0

    sp500_returns = {'^GSPC': sp500_ytd_return_val}
    time.sleep(STOCK_PROCESSING_DELAY_SECONDS)

    for ticker in sp500_tickers:
        metrics = get_stock_metrics(ticker, sp500_returns)
        if metrics is not None:
            all_stocks_metrics.append(metrics)
        time.sleep(STOCK_PROCESSING_DELAY_SECONDS)

    # Filter for stocks that meet EITHER the bullish OR the bearish crossover criteria recently
    # And other existing screening criteria (EPS, Sales, ROE, etc.)
    filtered_screened_stocks = [
        s for s in all_stocks_metrics
        if (s['bullish_crossover_recent'] or s['bearish_crossover_recent']) and
           s['eps_growth_annual'] >= EPS_GROWTH_ANNUAL_THRESHOLD and
           s['sales_growth_annual'] >= SALES_GROWTH_ANNUAL_THRESHOLD and
           s['roe'] >= ROE_THRESHOLD and
           s['price_near_52w_high'] >= PRICE_NEAR_52W_HIGH_PERCENTAGE and
           s['avg_daily_volume'] >= AVG_VOLUME_MINIMUM
    ]
    return filtered_screened_stocks


def send_email_alert(screened_stocks):
    if not screened_stocks:
        print("No stocks met the criteria for email alert. Email will not be sent.")
        return

    message = MIMEMultipart('alternative')
    # Update subject line for both crossovers over recent days
    message['Subject'] = "Daily Stock Screener Alert: Recent Bullish and/or Bearish Crossovers (Last 3 Days)!"
    message['From'] = SENDER_EMAIL
    message['To'] = RECIPIENT_EMAIL

    msg_related = MIMEMultipart('related')
    message.attach(msg_related)

    text_content = "Stock Screener Results for Recent Crossovers (Last 3 Days):\n\n"
    for stock in screened_stocks:
        crossover_type = ""
        if stock['bullish_crossover_recent']:
            crossover_type = "Bullish Crossover"
        elif stock['bearish_crossover_recent']:
            crossover_type = "Bearish Crossover"

        text_content += f"Ticker: {stock['ticker']} ({crossover_type})\n"
        text_content += f"  EPS Growth (Annual): {stock.get('eps_growth_annual', 0):.2%}\n"
        text_content += f"  Sales Growth (Annual): {stock.get('sales_growth_annual', 0):.2%}\n"
        text_content += f"  ROE: {stock.get('roe', 0):.2%}\n"
        text_content += f"  Relative Strength: {stock.get('relative_strength', 0):.2%}\n"
        text_content += f"  Price % of 52W High: {stock.get('price_near_52w_high', 0):.2%}\n"
        text_content += f"  Avg Daily Volume: {int(stock.get('avg_daily_volume', 0)):,}\n\n"

    msg_text = MIMEText(text_content, 'plain')
    msg_related.attach(msg_text)

    html_content = f"""\
    <html>
        <head>
            <style>
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}
                th, td {{
                    border: 1px solid black;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                h2, h3 {{
                    color: #333;
                }}
                p {{
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <h2>Daily Stock Screener Results: Recent Bullish and/or Bearish Crossovers (Last 3 Days)!</h2>
            <p>Here are the stocks matching your criteria and showing a 50/200-day SMA crossover in the last 3 trading days:</p>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Crossover Type</th>
                        <th>EPS Growth (Annual)</th>
                        <th>Sales Growth (Annual)</th>
                        <th>ROE</th>
                        <th>Relative Strength</th>
                        <th>Price % of 52W High</th>
                        <th>Avg Daily Volume</th>
                    </tr>
                </thead>
                <tbody>
    """

    for stock in screened_stocks:
        crossover_display_type = ""
        if stock['bullish_crossover_recent']:
            crossover_display_type = "Bullish"
        elif stock['bearish_crossover_recent']:
            crossover_display_type = "Bearish"

        html_content += f"""
                    <tr>
                        <td>{stock['ticker']}</td>
                        <td>{crossover_display_type}</td>
                        <td>{stock.get('eps_growth_annual', 0):.2%}</td>
                        <td>{stock.get('sales_growth_annual', 0):.2%}</td>
                        <td>{stock.get('roe', 0):.2%}</td>
                        <td>{stock.get('relative_strength', 0):.2%}</td>
                        <td>{stock.get('price_near_52w_high', 0):.2%}</td>
                        <td>{int(stock.get('avg_daily_volume', 0)):,}</td>
                    </tr>
        """
    html_content += """
                </tbody>
            </table>
    """

    # Add drill-down and plots ONLY for stocks that met either crossover criteria recently
    for i, stock in enumerate(screened_stocks):
        crossover_label = ""
        if stock['bullish_crossover_recent']:
            crossover_label = "Recent Bullish Crossover"
        elif stock['bearish_crossover_recent']:
            crossover_label = "Recent Bearish Crossover"

        if (stock['bullish_crossover_recent'] or stock['bearish_crossover_recent']):
            html_content += f"""
            <div>
                <h3>Drill-Down: {stock['ticker']} ({crossover_label})</h3>
                <table>
                    <tbody>
                        <tr>
                            <td>EPS Growth (Annual)</td>
                            <td>{stock.get('eps_growth_annual', 0):.2%}</td>
                        </tr>
                        <tr>
                            <td>Sales Growth (Annual)</td>
                            <td>{stock.get('sales_growth_annual', 0):.2%}</td>
                        </tr>
                        <tr>
                            <td>ROE</td>
                            <td>{stock.get('roe', 0):.2%}</td>
                        </tr>
                        <tr>
                            <td>Relative Strength</td>
                            <td>{stock.get('relative_strength', 0):.2%}</td>
                        </tr>
                        <tr>
                            <td>Price % of 52W High</td>
                            <td>{stock.get('price_near_52w_high', 0):.2%}</td>
                        </tr>
                        <tr>
                            <td>Avg Daily Volume</td>
                            <td>{int(stock.get('avg_daily_volume', 0)):,}</td>
                        </tr>
                    </tbody>
                </table>
                <p>Momentum analysis plot for {stock['ticker']}:</p>
            """
            if stock['plot']:
                html_content += f'<img src="cid:image_momentum_{i + 1}"><br><br>'
            else:
                html_content += '<p>No Momentum plot available due to insufficient data or error.</p><br><br>'

            html_content += f"""
                <p>Relative Strength Index (RSI) plot for {stock['ticker']}:</p>
            """
            if stock['rsi_plot']:
                html_content += f'<img src="cid:image_rsi_{i + 1}"><br><br>'
            else:
                html_content += '<p>No RSI plot available due to insufficient data or error.</p><br><br>'

            html_content += f"""
                <p>Moving Average Convergence Divergence (MACD) plot for {stock['ticker']}:</p>
            """
            if stock['macd_plot']:
                html_content += f'<img src="cid:image_macd_{i + 1}"><br><br>'
            else:
                html_content += '<p>No MACD plot available due to insufficient data or error.</p><br><br>'

            html_content += f"""
                <p>Rate of Change (ROC) plot for {stock['ticker']}:</p>
            """
            if stock['roc_plot']:
                html_content += f'<img src="cid:image_roc_{i + 1}"><br><br>'
            else:
                html_content += '<p>No ROC plot available due to insufficient data or error.</p><br><br>'

            html_content += f"""
                <p>Chande Momentum Oscillator (CMO) plot for {stock['ticker']}:</p>
            """
            if stock['cmo_plot']:
                html_content += f'<img src="cid:image_cmo_{i + 1}"><br><br>'
            else:
                html_content += '<p>No CMO plot available due to insufficient data or error.</p><br><br>'

            html_content += '</div>'
        else:
            html_content += f"""
            <div>
                <h3>Drill-Down: {stock['ticker']}</h3>
                <p>This stock did not meet recent crossover criteria, so detailed plots are not included.</p>
                <br><br>
            </div>
            """

    html_content += """
            <p><i>Note: EPS and Sales Growth are based on annual data. Relative Strength is calculated as the stock's YTD return minus the S&P 500's YTD return.</i></p>
            <p><i>The stocks listed above have also shown a 50-day SMA crossing above or below the 200-day SMA in the last 3 trading days.</i></p>
        </body>
    </html>
    """

    msg_html = MIMEText(html_content, 'html')
    msg_related.attach(msg_html)

    for i, stock in enumerate(screened_stocks):
        if stock['plot']:
            plot_buffer = stock['plot']
            plot_image = MIMEImage(plot_buffer.read(), name=f'{stock["ticker"]}_momentum.png')
            plot_image.add_header('Content-ID', f'<image_momentum_{i + 1}>')
            msg_related.attach(plot_image)

        if stock['rsi_plot']:
            rsi_plot_buffer = stock['rsi_plot']
            rsi_plot_image = MIMEImage(rsi_plot_buffer.read(), name=f'{stock["ticker"]}_rsi.png')
            rsi_plot_image.add_header('Content-ID', f'<image_rsi_{i + 1}>')
            msg_related.attach(rsi_plot_image)

        if stock['macd_plot']:
            macd_plot_buffer = stock['macd_plot']
            macd_plot_image = MIMEImage(macd_plot_buffer.read(), name=f'{stock["ticker"]}_macd.png')
            macd_plot_image.add_header('Content-ID', f'<image_macd_{i + 1}>')
            msg_related.attach(macd_plot_image)

        if stock['roc_plot']:
            roc_plot_buffer = stock['roc_plot']
            roc_plot_image = MIMEImage(roc_plot_buffer.read(), name=f'{stock["ticker"]}_roc.png')
            roc_plot_image.add_header('Content-ID', f'<image_roc_{i + 1}>')
            msg_related.attach(roc_plot_image)

        if stock['cmo_plot']:
            cmo_plot_buffer = stock['cmo_plot']
            cmo_plot_image = MIMEImage(cmo_plot_buffer.read(), name=f'{stock["ticker"]}_cmo.png')
            cmo_plot_image.add_header('Content-ID', f'<image_cmo_{i + 1}>')
            msg_related.attach(cmo_plot_image)

    message.attach(msg_related)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            try:
                server.starttls()
            except smtplib.SMTPException as e:
                print(f"SMTP Error during STARTTLS negotiation: {e}. Check server's TLS support or port.")
                return

            try:
                server.login(SENDER_EMAIL, SMTP_PASSWORD)
            except smtplib.SMTPAuthenticationError as e:
                print(f"SMTP Authentication Error: {e}. Check your username and password in config.ini.")
                print(f":{SENDER_EMAIL}:{SMTP_PASSWORD}:")
                return
            except smtplib.SMTPRecipientsRefused as e:
                print(f"SMTP Error: Server refused recipients during login (unusual, but possible if configured): {e}")
                return
            except smtplib.SMTPSenderRefused as e:
                print(f"SMTP Error: Server refused sender during login (unusual, but possible if configured): {e}")
                return
            except smtplib.SMTPDataError as e:
                print(f"SMTP Error: Unexpected data error during login: {e}")
                return
            except smtplib.SMTPException as e:
                print(f"Generic SMTP Error during login: {e}")
                return

            try:
                server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())
                print("Email alert sent successfully.")
            except smtplib.SMTPRecipientsRefused as e:
                print(
                    f"SMTP Error: Server refused to send to one or more recipients: {e}. Check recipient email addresses.")
                return
            except smtplib.SMTPSenderRefused as e:
                print(f"SMTP Error: Server refused sender email address: {e}. Check your sender email.")
                return
            except smtplib.SMTPDataError as e:
                print(f"SMTP Data Error: Server refused to accept the message data: {e}. Check email content/size.")
                return
            except smtplib.SMTPException as e:
                print(f"Generic SMTP Error during sending email: {e}")
                return

        print("Email alert sent successfully.")

    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: Could not connect to the SMTP server at {SMTP_SERVER}:{SMTP_PORT}. "
              f"Check server address, port, and network connectivity. Error: {e}")
    except smtplib.SMTPNotSupportedError as e:
        print(f"SMTP Protocol Error: Server does not support the requested command (e.g., STARTTLS): {e}.")
    except smtplib.SMTPException as e:
        print(f"An unexpected SMTP error occurred: {e}. This might be a generic server issue.")
    except Exception as e:
        print(f"An unexpected error occurred while trying to send email: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a stock screener with a user-defined configuration file.")
    parser.add_argument('--config', type=str, default='config.ini',
                        help='Path to the configuration file (e.g., my_config.ini)')
    args = parser.parse_args()

    try:
        config.read(args.config)

        SMTP_SERVER = config['email'].get('smtp_server', fallback="bezaman.parkcircus.org")
        SENDER_EMAIL = config['email'].get('sender_email', fallback="chowkidar@parkcircus.org")
        RECIPIENT_EMAIL = config['email'].get('recipient_email', fallback="reza@parkcircus.org")
        SMTP_PASSWORD = config['email'].get('smtp_password', fallback="your_email_password")
        SMTP_PORT = config['email'].getint('smtp_port', fallback=587)

        EPS_GROWTH_ANNUAL_THRESHOLD = config["criteria"].getfloat("EPS_GROWTH_ANNUAL_THRESHOLD", fallback=0.25)
        SALES_GROWTH_ANNUAL_THRESHOLD = config["criteria"].getfloat("SALES_GROWTH_ANNUAL_THRESHOLD", fallback=0.2)
        ROE_THRESHOLD = config["criteria"].getfloat("ROE_THRESHOLD", fallback=0.15)
        PRICE_NEAR_52W_HIGH_PERCENTAGE = config["criteria"].getfloat("PRICE_NEAR_52W_HIGH_PERCENTAGE", fallback=0.95)
        AVG_VOLUME_MINIMUM = config["criteria"].getint("AVG_VOLUME_MINIMUM", fallback=500000)
        SCREENER_TICKER_FILE = config["criteria"].get("screener_file", fallback="screener2.csv")


    except KeyError as e:
        print(f"Error reading {args.config}: Missing section or key: {e}. Falling back to hardcoded values.")
    except FileNotFoundError:
        print(
            f"{args.config} not found. Please ensure it's in the same directory as the script or provide the correct path. Falling back to hardcoded values.")
    except Exception as e:
        print(f"An unexpected error occurred while reading the config file: {e}. Falling back to hardcoded values.")

    print("Starting S&P 500 stock screener...")
    screened_stocks_for_email = run_screener()
    if screened_stocks_for_email:
        print(
            f"Found {len(screened_stocks_for_email)} stocks matching the criteria and showing a bullish or bearish crossover recently.")
        send_email_alert(screened_stocks_for_email)
    else:
        print("No stocks matched the screening criteria or showed a bullish or bearish crossover recently.")