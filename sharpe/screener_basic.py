import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import csv

# --- Configuration ---
# You need to fill these in with your specific details
SMTP_SERVER = 'bezaman.parkcircus.org'
SENDER_EMAIL = 'iot_admi@parkcircus.org'
RECIPIENT_EMAIL = 'reza@parkcircus.org'

# Screening criteria
EPS_GROWTH_ANNUAL_THRESHOLD = 0.25  # 25%
SALES_GROWTH_ANNUAL_THRESHOLD = 0.20  # 20%
ROE_THRESHOLD = 0.15  # 15%
PRICE_NEAR_52W_HIGH_PERCENTAGE = 0.95  # 95% of 52-week high
AVG_VOLUME_MINIMUM = 500000  # Minimum average daily volume


# --- Helper Functions ---
def get_sp500_tickers():
    """
    Reads the list of S&P 500 tickers from the screener2.csv file.
    The ticker symbol is in the 3rd column.
    """
    tickers = []
    try:
        with open('screener2.csv', 'r') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                # [cite_start]The ticker is in the 3rd column (index 2) of the CSV file [cite: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
                if len(row) > 2:
                    ticker = row[2].strip()
                    if ticker and not ticker.startswith('#'):
                        tickers.append(ticker)
    except FileNotFoundError:
        print("Error: screener2.csv not found. Using a default, small list.")
        # Fallback to a small list if the file is not found
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'JPM', 'V', 'PG', 'HD', 'TSLA']

    return tickers


def get_financial_data(ticker):
    """
    Fetches financial data for a given ticker.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        financials = stock.financials
        history = stock.history(period="1y")

        return {
            'info': info,
            'financials': financials,
            'history': history
        }
    except Exception as e:
        print(f"Could not fetch data for {ticker}: {e}")
        return None


def calculate_metrics(data):
    """
    Calculates key screening metrics from the fetched data.
    """
    metrics = {}
    info = data['info']
    financials = data['financials']
    history = data['history']

    if not financials.empty and len(financials.columns) >= 2:
        try:
            # EPS Growth (Annual YoY)
            current_eps = financials.loc['Diluted EPS', financials.columns[0]]
            prev_eps = financials.loc['Diluted EPS', financials.columns[1]]
            if prev_eps != 0:
                metrics['eps_growth_annual'] = (current_eps - prev_eps) / prev_eps
            else:
                metrics['eps_growth_annual'] = 0

            # Sales Growth (Annual YoY)
            current_sales = financials.loc['Total Revenue', financials.columns[0]]
            prev_sales = financials.loc['Total Revenue', financials.columns[1]]
            if prev_sales != 0:
                metrics['sales_growth_annual'] = (current_sales - prev_sales) / prev_sales
            else:
                metrics['sales_growth_annual'] = 0
        except KeyError as e:
            print(f"Financial data for EPS/Sales not available: {e}")
            metrics['eps_growth_annual'] = 0
            metrics['sales_growth_annual'] = 0
    else:
        metrics['eps_growth_annual'] = 0
        metrics['sales_growth_annual'] = 0

    # Relative Strength
    sp500_ticker = yf.Ticker('^GSPC')
    sp500_history = sp500_ticker.history(period="1y")
    if not history.empty and not sp500_history.empty:
        # Check if history data is sufficient for calculation
        if len(history) > 0 and len(sp500_history) > 0:
            stock_ytd_return = (history['Close'].iloc[-1] / history['Close'].iloc[0]) - 1
            sp500_ytd_return = (sp500_history['Close'].iloc[-1] / sp500_history['Close'].iloc[0]) - 1
            metrics['relative_strength'] = stock_ytd_return - sp500_ytd_return
        else:
            metrics['relative_strength'] = 0
    else:
        metrics['relative_strength'] = 0

    # Return on Equity (ROE)
    if 'returnOnEquity' in info:
        metrics['roe'] = info['returnOnEquity']
    else:
        metrics['roe'] = 0

    # Price Performance (Near 52-week high)
    if 'fiftyTwoWeekHigh' in info and 'currentPrice' in info:
        metrics['price_near_52w_high'] = info['currentPrice'] / info['fiftyTwoWeekHigh']
    else:
        metrics['price_near_52w_high'] = 0

    # Average Daily Volume (last 30 days)
    if not history.empty and len(history) >= 30:
        metrics['avg_daily_volume'] = history['Volume'].iloc[-30:].mean()
    else:
        metrics['avg_daily_volume'] = 0

    return metrics


def run_screener():
    """
    Runs the stock screener against the S&P 500 list.
    """
    tickers = get_sp500_tickers()
    screened_stocks = []

    for ticker in tickers:
        print(f"Processing {ticker}...")
        data = get_financial_data(ticker)
        if data:
            metrics = calculate_metrics(data)

            # Apply screening criteria
            is_high_eps = metrics.get('eps_growth_annual', 0) > EPS_GROWTH_ANNUAL_THRESHOLD
            is_high_sales = metrics.get('sales_growth_annual', 0) > SALES_GROWTH_ANNUAL_THRESHOLD
            is_high_roe = metrics.get('roe', 0) > ROE_THRESHOLD
            is_near_high = metrics.get('price_near_52w_high', 0) >= PRICE_NEAR_52W_HIGH_PERCENTAGE
            is_high_volume = metrics.get('avg_daily_volume', 0) > AVG_VOLUME_MINIMUM
            is_high_rs = metrics.get('relative_strength', 0) > 0  # Simple RS: outperforming S&P 500

            if is_high_eps and is_high_sales and is_high_roe and is_near_high and is_high_volume and is_high_rs:
                screened_stocks.append({
                    'ticker': ticker,
                    'metrics': metrics
                })

    return screened_stocks


def send_email_alert(screened_stocks):
    """
    Sends an email with the screening results using a LAN SMTP server.
    """
    if not screened_stocks:
        print("No stocks met the screening criteria. No email alert sent.")
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = "Daily S&P 500 Stock Screener Alert"
    message["From"] = SENDER_EMAIL
    message["To"] = RECIPIENT_EMAIL

    html_content = """
    <html>
        <body>
            <h3>Daily Stock Screener Results for S&P 500</h3>
            <p>The following stocks met the established quantitative criteria as of {date}.</p>
    """.format(date=datetime.now().strftime("%Y-%m-%d"))

    for stock in screened_stocks:
        ticker = stock['ticker']
        metrics = stock['metrics']

        html_content += f"""
            <h4>{ticker}</h4>
            <table border="1" cellpadding="5" cellspacing="0">
                <thead>
                    <tr>
                        <th>Parameter</th>
                        <th>Value</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>EPS Growth (YoY)</td>
                        <td>{metrics.get('eps_growth_annual', 0):.2%}</td>
                    </tr>
                    <tr>
                        <td>Sales Growth (YoY)</td>
                        <td>{metrics.get('sales_growth_annual', 0):.2%}</td>
                    </tr>
                    <tr>
                        <td>Relative Strength</td>
                        <td>{metrics.get('relative_strength', 0):.2%}</td>
                    </tr>
                    <tr>
                        <td>ROE</td>
                        <td>{metrics.get('roe', 0):.2%}</td>
                    </tr>
                    <tr>
                        <td>Price % of 52W High</td>
                        <td>{metrics.get('price_near_52w_high', 0):.2%}</td>
                    </tr>
                    <tr>
                        <td>Avg Daily Volume</td>
                        <td>{int(metrics.get('avg_daily_volume', 0)):,}</td>
                    </tr>
                </tbody>
            </table>
            <br>
        """

    html_content += """
            <p><i>Note: EPS and Sales Growth are based on annual data. Relative Strength is calculated as the stock's YTD return minus the S&P 500's YTD return.</i></p>
        </body>
    </html>
    """

    part = MIMEText(html_content, "html")
    message.attach(part)

    try:
        with smtplib.SMTP(SMTP_SERVER) as server:
            # The server configuration requires TLS and login
            server.starttls()
            server.login('iot_admi', 'Apna2Chabee!')
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())
        print("Email alert sent successfully.")
    except Exception as e:
        print(f"Failed to send email alert: {e}")


if __name__ == "__main__":
    print("Starting S&P 500 stock screener...")
    screened_stocks = run_screener()
    if screened_stocks:
        print(f"Found {len(screened_stocks)} stocks matching the criteria.")
        send_email_alert(screened_stocks)
    else:
        print("No stocks met the screening criteria.")