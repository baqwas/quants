#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@brief: A Streamlit stock screener dashboard that fetches financial data,
calculates key metrics, and displays interactive charts.
@details: This script converts the original stock screener into a Streamlit web
application. Users can select a stock from a sidebar, and the main area will
display various technical analysis charts for the selected stock.
It uses yfinance for data, pandas for data manipulation, and matplotlib for plotting.
@note: Ensure you have the required libraries installed: streamlit, yfinance, pandas, matplotlib.
@version: 1.0
@date: 2023-10-01 (Modified for Streamlit: 2025-07-24)
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
import streamlit as st

# --- Configuration (can be put in config.ini or set as Streamlit secrets) ---
config = configparser.ConfigParser()

# Define SCREENER_TICKER_FILE globally with a default value
SCREENER_TICKER_FILE = "screener2.csv"

try:
    config.read('config.ini')

    # Email configuration (kept for completeness if needed for other parts, but not used in Streamlit UI directly)
    SMTP_SERVER = config['email'].get('smtp_server', fallback="bezaman.parkcircus.org")
    SENDER_EMAIL = config['email'].get('sender_email', fallback="chowkidar@parkcircus.org")
    RECIPIENT_EMAIL = config['email'].get('recipient_email', fallback="reza@parkcircus.org")
    # FIX: Change getint to get for SMTP_PASSWORD
    SMTP_PASSWORD = config['email'].get('smtp_password', fallback="Tapuria#1")
    SMTP_PORT = config['email'].getint('smtp_port', fallback=587) # Ensure this remains getint

    # Screening criteria (might be exposed as sliders/inputs in Streamlit if desired)
    EPS_GROWTH_ANNUAL_THRESHOLD = config["criteria"].getfloat("EPS_GROWTH_ANNUAL_THRESHOLD", fallback=0.25)
    SALES_GROWTH_ANNUAL_THRESHOLD = config["criteria"].getfloat("SALES_GROWTH_ANNUAL_THRESHOLD", fallback=0.2)
    ROE_THRESHOLD = config["criteria"].getfloat("ROE_THRESHOLD", fallback=0.15)
    PRICE_NEAR_52W_HIGH_PERCENTAGE = config["criteria"].getfloat("PRICE_NEAR_52W_HIGH_PERCENTAGE", fallback=0.95)
    AVG_VOLUME_MINIMUM = config["criteria"].getint("AVG_VOLUME_MINIMUM", fallback=500000)
    # Update SCREENER_TICKER_FILE from config if available
    SCREENER_TICKER_FILE = config["criteria"].get("screener_file", fallback=SCREENER_TICKER_FILE)

except KeyError as e:
    st.warning(f"Error reading config.ini: Missing section or key: {e}. Using default values.")
except FileNotFoundError:
    st.warning("config.ini not found. Please ensure it's in the same directory as the script. Using default values.")
except Exception as e:
    st.error(f"An unexpected error occurred while reading the config file: {e}. Using default values.")


# --- Helper Functions (adapted for Streamlit) ---

@st.cache_data
def load_stock_list_for_sidebar(file_path="screener2.csv"):
    """
    Reads the list of S&P 500 tickers, company names, and sectors from the screener file.
    Returns a DataFrame sorted by Sector and Company Name.
    Columns in screener2.csv are assumed to be (0-indexed):
    0: Sequence Number (not used)
    1: Company Name
    2: Ticker Symbol
    3: Sector
    """
    stock_data = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                if len(row) >= 4:
                    # Column indices: Company Name (1), Sector (3), Ticker Symbol (2)
                    stock_data.append({'Company Name': row[1], 'Sector': row[3], 'Ticker': row[2]})
    except FileNotFoundError:
        st.error(f"{file_path} not found. Please ensure it's in the same directory as the script.")
        # Fallback list for demonstration if file is missing
        return pd.DataFrame([
            {'Company Name': 'Apple Inc.', 'Sector': 'Technology', 'Ticker': 'AAPL'},
            {'Company Name': 'Microsoft Corp.', 'Sector': 'Technology', 'Ticker': 'MSFT'},
            {'Company Name': 'Amazon.com Inc.', 'Sector': 'Consumer Discretionary', 'Ticker': 'AMZN'},
            {'Company Name': 'JPMorgan Chase & Co.', 'Sector': 'Financials', 'Ticker': 'JPM'},
            {'Company Name': 'Tesla Inc.', 'Sector': 'Consumer Discretionary', 'Ticker': 'TSLA'}
        ])
    except Exception as e:
        st.error(f"Error reading {file_path}: {e}")
        return pd.DataFrame()

    df = pd.DataFrame(stock_data)
    # Sort by Sector, then by Company Name
    df_sorted = df.sort_values(by=['Sector', 'Company Name']).reset_index(drop=True)
    return df_sorted


@st.cache_data(ttl=3600)  # Cache data for 1 hour
def get_data_for_streamlit(ticker, start_date, end_date):
    """
    Fetches historical stock data for a given ticker within a specified date range.
    """
    try:
        data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if data.empty:
            return None
        # Ensure 'Close' column exists and is not multi-indexed
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        if 'Close' not in data.columns and 'Adj Close' in data.columns:
            data = data.rename(columns={'Adj Close': 'Close'})
        if 'Close' not in data.columns or data['Close'].empty or data['Close'].isnull().all():
            return None
        return data
    except Exception as e:
        st.error(f"Error fetching data for {ticker} from {start_date} to {end_date}: {e}")
        return None


def calculate_ytd_return(data):
    if data.empty or 'Close' not in data.columns or data['Close'].empty or data['Close'].isnull().all():
        return 0.0
    start_price = data['Close'].iloc[0]
    end_price = data['Close'].iloc[-1]
    return (end_price - start_price) / start_price if start_price else 0.0


# --- Plotting Functions (modified to return matplotlib Figure objects) ---

def plot_momentum_streamlit(data, ticker):
    if data.empty or 'Close' not in data.columns or data['Close'].empty or data['Close'].isnull().all():
        return None

    data['SMA_50'] = data['Close'].rolling(window=50).mean()
    data['SMA_200'] = data['Close'].rolling(window=200).mean()

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(data.index, data['Close'], label=f'{ticker} Close Price', color='blue')
    ax.plot(data.index, data['SMA_50'], label='50-Day SMA', color='orange')
    ax.plot(data.index, data['SMA_200'], label='200-Day SMA', color='red')

    ax.set_title(f'{ticker} Stock Price and Moving Averages')
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.legend()
    ax.grid(True)

    return fig


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


def plot_rsi_streamlit(data, ticker, window=14):
    if data.empty or 'Close' not in data.columns or len(data) < window:
        return None

    close_prices = pd.to_numeric(data['Close'], errors='coerce').dropna()
    if close_prices.empty or len(close_prices) < window:
        return None

    delta = close_prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(span=window, adjust=False).mean()
    avg_loss = loss.ewm(span=window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

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

    return fig


def plot_macd_streamlit(data, ticker, fast_period=12, slow_period=26, signal_period=9):
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

    data_with_macd = data.copy()
    data_with_macd['MACD_Line'] = macd_line.reindex(data.index)
    data_with_macd['Signal_Line'] = signal_line.reindex(data.index)
    data_with_macd['Histogram'] = histogram.reindex(data.index)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(data_with_macd.index, data_with_macd['MACD_Line'], label='MACD Line', color='blue')
    ax.plot(data_with_macd.index, data_with_macd['Signal_Line'], label='Signal Line', color='red')
    ax.bar(data_with_macd.index, data_with_macd['Histogram'], label='Histogram', color='gray', alpha=0.7)

    # Identify crossover signals
    # Bullish crossover: MACD crosses above Signal Line
    buy_signals = (data_with_macd['MACD_Line'].shift(1) <= data_with_macd['Signal_Line'].shift(1)) & \
                  (data_with_macd['MACD_Line'] > data_with_macd['Signal_Line'])
    # Bearish crossover: MACD crosses below Signal Line
    sell_signals = (data_with_macd['MACD_Line'].shift(1) >= data_with_macd['Signal_Line'].shift(1)) & \
                   (data_with_macd['MACD_Line'] < data_with_macd['Signal_Line'])

    # Plot crossover signals
    ax.scatter(data_with_macd.index[buy_signals], data_with_macd['MACD_Line'][buy_signals],
               marker='^', color='green', s=100, label='Buy Signal', zorder=5)
    ax.scatter(data_with_macd.index[sell_signals], data_with_macd['MACD_Line'][sell_signals],
               marker='v', color='red', s=100, label='Sell Signal', zorder=5)

    ax.set_title(f'{ticker} Moving Average Convergence Divergence (MACD) with Crossover Signals')
    ax.set_xlabel('Date')
    ax.set_ylabel('Value')
    ax.legend()
    ax.grid(True)

    return fig


def plot_roc_streamlit(data, ticker, window=12):
    if data.empty or 'Close' not in data.columns or len(data) < window + 1:
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

    return fig


def plot_cmo_streamlit(data, ticker, window=14):
    if data.empty or 'Close' not in data.columns or len(data) < window + 1:
        return None

    close_prices = pd.to_numeric(data['Close'], errors='coerce').dropna()
    if close_prices.empty or len(close_prices) < window + 1:
        return None

    diff = close_prices.diff()
    sum_up = diff.where(diff > 0, 0).rolling(window=window).sum()
    sum_down = -diff.where(diff < 0, 0).rolling(window=window).sum()

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

    return fig


# --- Original (non-Streamlit) functions, kept if they are called elsewhere or for future use ---

def get_sp500_tickers():
    """Reads the list of S&P 500 tickers from the configured screener file."""
    tickers = []
    try:
        with open(SCREENER_TICKER_FILE, 'r') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                if len(row) > 2:
                    tickers.append(row[2])
    except FileNotFoundError:
        print(f"{SCREENER_TICKER_FILE} not found. Returning a default list of tickers.")
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'JPM', 'V', 'PG', 'HD', 'TSLA']  # Fallback list
    return tickers


def get_stock_metrics(ticker, sp500_returns):
    metrics = {
        'ticker': ticker,
        'eps_growth_annual': 0.0,
        'sales_growth_annual': 0.0,
        'roe': 0.0,
        'relative_strength': 0.0,
        'price_near_52w_high': 0.0,
        'avg_daily_volume': 0,
        'bullish_crossover_recent': False,
        'bearish_crossover_recent': False,
    }
    try:
        stock = yf.Ticker(ticker)

        end_date = datetime.now()
        start_date_required = end_date - timedelta(days=365 + 10)
        data_full = yf.download(ticker, start=start_date_required, end=end_date, progress=False, auto_adjust=True)
        time.sleep(0.5)  # DOWNLOAD_DELAY_SECONDS

        if data_full.empty:
            return metrics
        if isinstance(data_full.columns, pd.MultiIndex):
            data_full.columns = data_full.columns.get_level_values(0)
        if 'Close' not in data_full.columns and 'Adj Close' in data_full.columns:
            data_full = data_full.rename(columns={'Adj Close': 'Close'})
        if 'Close' not in data_full.columns or data_full['Close'].empty or data_full['Close'].isnull().all():
            return metrics

        metrics['bullish_crossover_recent'] = check_bullish_crossover(data_full.copy(), lookback_days=3)
        metrics['bearish_crossover_recent'] = check_bearish_crossover(data_full.copy(), lookback_days=3)

        current_year_start = datetime(end_date.year, 1, 1)
        ytd_data = yf.download(ticker, start=current_year_start, end=end_date, progress=False, auto_adjust=True)
        time.sleep(0.5)  # DOWNLOAD_DELAY_SECONDS

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
        time.sleep(0.5)  # DOWNLOAD_DELAY_SECONDS
        if isinstance(data_30d.columns, pd.MultiIndex):
            data_30d.columns = data_30d.columns.get_level_values(0)
        if not data_30d.empty and 'Volume' in data_30d.columns and not data_30d['Volume'].isnull().all():
            metrics['avg_daily_volume'] = data_30d['Volume'].mean()
        else:
            metrics['avg_daily_volume'] = 0

        financials = stock.financials
        balance_sheet = stock.balance_sheet
        time.sleep(0.5)  # DOWNLOAD_DELAY_SECONDS

        if not financials.empty and 'Net Income' in financials.index and len(financials.columns) >= 2:
            current_net_income = financials.loc['Net Income'].iloc[0]
            prev_net_income = financials.loc['Net Income'].iloc[1]
            if prev_net_income > 0:
                metrics['eps_growth_annual'] = (current_net_income - prev_net_income) / prev_net_income

        if not financials.empty and 'Total Revenue' in financials.index and len(financials.columns) >= 2:
            current_revenue = financials.loc['Total Revenue'].iloc[0]
            prev_revenue = financials.loc['Total Revenue'].iloc[1]
            if prev_revenue > 0:
                metrics['sales_growth_annual'] = (current_revenue - prev_revenue) / prev_revenue

        if not financials.empty and 'Net Income' in financials.index and not balance_sheet.empty and \
                'Total Equity' in balance_sheet.index and len(financials.columns) >= 1 and len(
            balance_sheet.columns) >= 1:
            net_income = financials.loc['Net Income'].iloc[0]
            total_equity = balance_sheet.loc['Total Equity'].iloc[0]
            if total_equity > 0:
                metrics['roe'] = net_income / total_equity

    except Exception as e:
        print(f"Could not get metrics for {ticker}: {e}")

    return metrics


def send_email_alert(screened_stocks, subject_prefix="Stock Screener Alert"):
    """
    Sends an email alert with the screened stocks and their metrics.
    """
    if not screened_stocks:
        print("No stocks to send in the email alert.")
        return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = f"{subject_prefix} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    body_html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .crossover-bullish {{ color: green; font-weight: bold; }}
            .crossover-bearish {{ color: red; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2>Stock Screener Results</h2>
        <p>The following stocks matched your screening criteria:</p>
        <table>
            <thead>
                <tr>
                    <th>Ticker</th>
                    <th>EPS Growth (Annual)</th>
                    <th>Sales Growth (Annual)</th>
                    <th>ROE</th>
                    <th>Relative Strength (YTD vs S&P 500)</th>
                    <th>Price Near 52W High (%)</th>
                    <th>Avg Daily Volume (30D)</th>
                    <th>Crossover</th>
                </tr>
            </thead>
            <tbody>
    """

    for stock in screened_stocks:
        crossover_info = ""
        if stock.get('bullish_crossover_recent'):
            crossover_info = "<span class='crossover-bullish'>Bullish SMA Crossover</span>"
        elif stock.get('bearish_crossover_recent'):
            crossover_info = "<span class='crossover-bearish'>Bearish SMA Crossover</span>"
        else:
            crossover_info = "No recent SMA crossover"

        body_html += f"""
                <tr>
                    <td>{stock['ticker']}</td>
                    <td>{stock['eps_growth_annual']:.2%}</td>
                    <td>{stock['sales_growth_annual']:.2%}</td>
                    <td>{stock['roe']:.2%}</td>
                    <td>{stock['relative_strength']:.2%}</td>
                    <td>{stock['price_near_52w_high']:.2%}</td>
                    <td>{stock['avg_daily_volume']:,}</td>
                    <td>{crossover_info}</td>
                </tr>
        """
    body_html += """
            </tbody>
        </table>
        <p><i>Note: Financial data is based on available information from yfinance and may vary.</i></p>
    </body>
    </html>
    """

    msg.attach(MIMEText(body_html, 'html'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Upgrade the connection to a secure encrypted SSL/TLS connection
            server.login(SENDER_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        print("Email alert sent successfully.")

    except smtplib.SMTPAuthenticationError as e:
        print(
            f"SMTP Authentication Error: Could not log in to the SMTP server. Check username/password. Error: {e}")
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: Could not connect to the SMTP server at {SMTP_SERVER}:{SMTP_PORT}. "
              f"Check server address, port, and network connectivity. Error: {e}")
    except smtplib.SMTPNotSupportedError as e:
        print(f"SMTP Protocol Error: Server does not support the requested command (e.g., STARTTLS): {e}.")
    except smtplib.SMTPRecipientsRefused as e:
        print(f"SMTP Recipient Error: The server refused to accept the recipient email address: {e.recipients}. "
              f"Check RECIPIENT_EMAIL address.")
    except smtplib.SMTPSenderRefused as e:
        print(
            f"SMTP Sender Error: The server refused the sender email address: {e.sender}. Check SENDER_EMAIL address.")
    except smtplib.SMTPDataError as e:
        # This error can occur if the message content is rejected (e.g., too large, malformed)
        print(f"SMTP Data Error: Server refused to accept the message data: {e}. Check email content/size.")
    except smtplib.SMTPException as e:
        print(f"Generic SMTP Error during sending email: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while trying to send email: {e}")


def run_screener():
    """
    Runs the stock screener based on defined criteria.
    Returns a list of dictionaries, each representing a screened stock with its metrics.
    """
    sp500_tickers = get_sp500_tickers()
    screened_stocks = []

    # Get S&P 500 YTD return for relative strength calculation
    sp500_returns = {}
    try:
        sp500_data = yf.download('^GSPC', start=datetime(datetime.now().year, 1, 1), end=datetime.now(),
                                 progress=False, auto_adjust=True)
        if not sp500_data.empty and 'Close' in sp500_data.columns and not sp500_data['Close'].isnull().all():
            sp500_returns['^GSPC'] = calculate_ytd_return(sp500_data)
        else:
            print("Could not fetch S&P 500 data for YTD return calculation. Relative strength will be 0.")
    except Exception as e:
        print(f"Error fetching S&P 500 data: {e}. Relative strength will be 0.")

    st.write(f"Analyzing {len(sp500_tickers)} S&P 500 stocks...")
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, ticker in enumerate(sp500_tickers):
        status_text.text(f"Processing {ticker} ({i + 1}/{len(sp500_tickers)})")
        progress_bar.progress((i + 1) / len(sp500_tickers))

        metrics = get_stock_metrics(ticker, sp500_returns)
        if (metrics['eps_growth_annual'] >= EPS_GROWTH_ANNUAL_THRESHOLD and
                metrics['sales_growth_annual'] >= SALES_GROWTH_ANNUAL_THRESHOLD and
                metrics['roe'] >= ROE_THRESHOLD and
                metrics['price_near_52w_high'] >= PRICE_NEAR_52W_HIGH_PERCENTAGE and
                metrics['avg_daily_volume'] >= AVG_VOLUME_MINIMUM and
                (metrics['bullish_crossover_recent'] or metrics['bearish_crossover_recent'])):  # Include crossovers in screening
            screened_stocks.append(metrics)
        time.sleep(0.05)  # Add a small delay to avoid hitting API limits too hard and for UI update

    progress_bar.empty()
    status_text.empty()
    return screened_stocks


# --- Streamlit UI Layout ---
def main():
    st.set_page_config(layout="wide", page_title="Stock Screener & Chart Viewer")

    st.sidebar.title("Stock Screener & Chart Viewer")

    stock_df = load_stock_list_for_sidebar(SCREENER_TICKER_FILE)

    if not stock_df.empty:
        # Create a combined display string for the selectbox: "Company Name (Ticker)"
        stock_df['Display'] = stock_df['Company Name'] + ' (' + stock_df['Ticker'] + ')'

        # Create a mapping from display string to ticker symbol
        display_to_ticker = pd.Series(stock_df.Ticker.values, index=stock_df.Display).to_dict()

        # Sort the display list alphabetically for the selectbox
        sorted_display_list = sorted(stock_df['Display'].tolist())

        selected_display = st.sidebar.selectbox(
            "Select a Stock to View Charts",
            sorted_display_list
        )

        selected_ticker = display_to_ticker.get(selected_display)

    else:
        selected_ticker = None
        st.sidebar.warning("No stock list loaded. Please check 'screener2.csv'.")

    # Date Picker Widgets
    today = datetime.now().date()
    default_start_date = today - timedelta(days=365 * 2) # Default to 2 years ago for charting
    default_end_date = today

    st.sidebar.subheader("Select Date Range for Charts")
    start_date = st.sidebar.date_input("Start Date", value=default_start_date, max_value=today)
    end_date = st.sidebar.date_input("End Date", value=default_end_date, max_value=today, min_value=start_date)

    st.title(f"Charts for {selected_ticker if selected_ticker else 'Selected Stock'}")

    if selected_ticker:
        stock_data = get_data_for_streamlit(selected_ticker, start_date, end_date)

        if stock_data is not None and not stock_data.empty:
            st.subheader("1. Price and Moving Averages")
            momentum_fig = plot_momentum_streamlit(stock_data, selected_ticker)
            if momentum_fig:
                st.pyplot(momentum_fig)
                plt.close(momentum_fig)  # Close the figure to free up memory
            else:
                st.warning("Could not generate Price and Moving Averages plot due to insufficient data for the selected date range.")

            st.subheader("2. Relative Strength Index (RSI)")
            rsi_fig = plot_rsi_streamlit(stock_data, selected_ticker)
            if rsi_fig:
                st.pyplot(rsi_fig)
                plt.close(rsi_fig)
            else:
                st.warning("Could not generate RSI plot due to insufficient data for the selected date range.")

            st.subheader("3. Moving Average Convergence Divergence (MACD)")
            macd_fig = plot_macd_streamlit(stock_data, selected_ticker)
            if macd_fig:
                st.pyplot(macd_fig)
                plt.close(macd_fig)
            else:
                st.warning("Could not generate MACD plot due to insufficient data for the selected date range.")

            st.subheader("4. Rate of Change (ROC)")
            roc_fig = plot_roc_streamlit(stock_data, selected_ticker)
            if roc_fig:
                st.pyplot(roc_fig)
                plt.close(roc_fig)
            else:
                st.warning("Could not generate ROC plot due to insufficient data for the selected date range.")

            st.subheader("5. Chande Momentum Oscillator (CMO)")
            cmo_fig = plot_cmo_streamlit(stock_data, selected_ticker)
            if cmo_fig:
                st.pyplot(cmo_fig)
                plt.close(cmo_fig)
            else:
                st.warning("Could not generate CMO plot due to insufficient data for the selected date range.")

        else:
            st.error(
                f"Could not fetch historical data for {selected_ticker} in the range {start_date} to {end_date}. Please ensure the ticker is valid and adjust the date range.")
    else:
        st.info("Please select a stock from the sidebar to view its charts.")


if __name__ == "__main__":
    # Streamlit applications are run using `streamlit run your_script_name.py`
    # The argparse part is retained for compatibility but won't be used by `streamlit run`.
    # The email sending part is also retained but not called directly by the Streamlit app flow.
    # To run this script: save it as e.g., `streamlit_screener.py` and run `streamlit run streamlit_screener.py`
    main()