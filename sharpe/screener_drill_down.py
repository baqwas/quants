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
    SMTP_PASSWORD = config['email'].get('smtp_password', fallback="Tapuria#1")
    SMTP_PORT = config['email'].getint('smtp_port', fallback=587)

except KeyError as e:
    print(f"Error reading config.ini: Missing section or key: {e}. Falling back to hardcoded values.")
except FileNotFoundError:
    print("config.ini not found. Please ensure it's in the same directory as the script. Falling back to hardcoded values.")

EPS_GROWTH_ANNUAL_THRESHOLD = config["criteria"].getfloat("EPS_GROWTH_ANNUAL_THRESHOLD", fallback=0.25)
SALES_GROWTH_ANNUAL_THRESHOLD = config["criteria"].getfloat("SALES_GROWTH_ANNUAL_THRESHOLD", fallback=0.2)
ROE_THRESHOLD = config["criteria"].getfloat("ROE_THRESHOLD", fallback=0.15)
PRICE_NEAR_52W_HIGH_PERCENTAGE = config["criteria"].getfloat("PRICE_NEAR_52W_HIGH_PERCENTAGE", fallback=0.95)
AVG_VOLUME_MINIMUM = config["criteria"].getint("AVG_VOLUME_MINIMUM", fallback=500000)
SCREENER_TICKER_FILE = config["criteria"].get("screener", "screener2.csv")

DOWNLOAD_DELAY_SECONDS = 0.5
STOCK_PROCESSING_DELAY_SECONDS = 1

# --- Helper Functions ---
def get_sp500_tickers():
    """
    Reads the list of S&P 500 tickers from the screener2.csv file.
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
        print("screener2.csv not found. Please ensure it's in the same directory as the script. Returning a default list of tickers.")
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'JPM', 'V', 'PG', 'HD', 'TSLA'] # Fallback list
    return tickers


def calculate_ytd_return(data):
    if data.empty or 'Close' not in data.columns or data['Close'].empty or data['Close'].isnull().all():
        return 0.0
    start_price = data['Close'].iloc[0]
    end_price = data['Close'].iloc[-1]
    return (end_price - start_price) / start_price if start_price else 0.0


def plot_momentum(data, ticker):
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
        'plot': None
    }
    try:
        stock = yf.Ticker(ticker)

        end_date = datetime.now()
        start_date_1y = end_date - timedelta(days=365)
        data_1y = yf.download(ticker, start=start_date_1y, end=end_date, progress=False, auto_adjust=True)
        time.sleep(DOWNLOAD_DELAY_SECONDS)

        if data_1y.empty:
            return metrics
        if isinstance(data_1y.columns, pd.MultiIndex):
            data_1y.columns = data_1y.columns.get_level_values(0)
        if 'Close' not in data_1y.columns and 'Adj Close' in data_1y.columns:
            data_1y = data_1y.rename(columns={'Adj Close': 'Close'})
        if 'Close' not in data_1y.columns or data_1y['Close'].empty or data_1y['Close'].isnull().all():
            return metrics

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

        if not data_1y.empty and 'Close' in data_1y.columns and not data_1y['Close'].isnull().all():
            price_52w_high = data_1y['Close'].max()
            current_price = data_1y['Close'].iloc[-1]
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

        metrics['plot'] = plot_momentum(data_1y, ticker)

    except Exception as e:
        print(f"An unexpected error occurred for {ticker}: {e}")
        return metrics

    return metrics


def run_screener():
    sp500_tickers = get_sp500_tickers()
    screened_stocks = []

    sp500_data = pd.DataFrame()
    # https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html#yfinance.download
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
            screened_stocks.append(metrics)
        time.sleep(STOCK_PROCESSING_DELAY_SECONDS)
    return screened_stocks


def send_email_alert(screened_stocks):
    if not screened_stocks:
        return

    message = MIMEMultipart('alternative')
    message['Subject'] = "Daily Stock Screener Alert"
    message['From'] = SENDER_EMAIL
    message['To'] = RECIPIENT_EMAIL

    msg_related = MIMEMultipart('related')
    message.attach(msg_related)

    text_content = "Stock Screener Results:\n\n"
    for stock in screened_stocks:
        text_content += f"Ticker: {stock['ticker']}\n"
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
                }}
                th, td {{
                    border: 1px solid black;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                h2 {{
                    color: #333;
                }}
                p {{
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <h2>Daily Stock Screener Results</h2>
            <p>Here are the stocks matching your criteria:</p>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
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
        html_content += f"""
                    <tr>
                        <td>{stock['ticker']}</td>
                        <td>{stock.get('eps_growth_annual', 0):.2%}</td>
                        <td>{stock.get('sales_growth_annual', 0):.2%}</td>
                        <td>{stock.get('roe', 0):.2%}</td>
                        <td>{stock.get('relative_strength', 0):.2%}</td>
                        <td>{stock.get('price_near_52w_high', 0):.2%}</td>
                        <td>{int(stock.get('avg_daily_volume', 0)):,}</td>
                    </tr>
        """
    for i, stock in enumerate(screened_stocks):
        html_content += f"""
            <div>
                <h3>Drill-Down: {stock['ticker']}</h3>
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
                <img src="cid:image{i + 1}"><br><br>
            </div>
        """

    html_content += """
                </tbody>
            </table>
            <p><i>Note: EPS and Sales Growth are based on annual data. Relative Strength is calculated as the stock's YTD return minus the S&P 500's YTD return.</i></p>
        </body>
    </html>
    """

    msg_html = MIMEText(html_content, 'html')
    msg_related.attach(msg_html)

    for i, stock in enumerate(screened_stocks):
        if stock['plot']:
            plot_buffer = stock['plot']
            plot_image = MIMEImage(plot_buffer.read(), name=f'{stock["ticker"]}_momentum.png')
            plot_image.add_header('Content-ID', f'<image{i + 1}>')
            msg_related.attach(plot_image)

    message.attach(msg_related)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            try:
                server.starttls()
            except smtplib.SMTPException as e:
                print(f"SMTP Error during STARTTLS negotiation: {e}. Check server's TLS support or port.")
                return

            # 2. Authenticate
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

            # 3. Send email
            try:
                server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())
                print("Email alert sent successfully.")
            except smtplib.SMTPRecipientsRefused as e:
                # This often indicates invalid recipient email addresses
                print(f"SMTP Error: Server refused to send to one or more recipients: {e}. Check recipient email addresses.")
                return
            except smtplib.SMTPSenderRefused as e:
                # This often indicates an invalid sender email address
                print(f"SMTP Error: Server refused sender email address: {e}. Check your sender email.")
                return
            except smtplib.SMTPDataError as e:
                # This can indicate issues with the message content (e.g., too large, malformed)
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
        # Catch any other smtplib specific errors not covered above
        print(f"An unexpected SMTP error occurred: {e}. This might be a generic server issue.")
    except Exception as e:
        # Catch any other non-smtplib related exceptions (e.g., network issues not caught by smtplib)
        print(f"An unexpected error occurred while trying to send email: {e}")

if __name__ == "__main__":
    print("Starting S&P 500 stock screener...")
    screened_stocks = run_screener()
    if screened_stocks:
        print(f"Found {len(screened_stocks)} stocks matching the criteria.")
        send_email_alert(screened_stocks)
    else:
        print("No stocks matched the screening criteria.")