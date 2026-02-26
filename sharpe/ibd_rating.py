import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from scipy.stats import percentileofscore
import requests
import time
import os
import configparser
import mariadb  # New import for MariaDB/MySQL connectivity

# Define a default User-Agent string
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def read_mariadb_config(config_file):
    """
    Reads MariaDB configuration from the INI file.
    """
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
        mariadb_config = {
            "host": config["mariadb"]["host"],
            "port": int(config["mariadb"]["port"]),
            "user": config["mariadb"]["user"],
            "password": config["mariadb"]["password"],
            "database": config["mariadb"]["database"]
        }
        return mariadb_config
    except (FileNotFoundError, KeyError) as e:
        print(
            f"Error reading MariaDB configuration file: {e}. Please ensure the 'mariadb' section is present and correct.")
        return None


def initialize_database(mariadb_config):
    """
    Connects to the MariaDB database and creates the 'ibd_ratings' table if it doesn't exist.
    """
    try:
        conn = mariadb.connect(
            host=mariadb_config["host"],
            port=mariadb_config["port"],
            user=mariadb_config["user"],
            password=mariadb_config["password"],
            database=mariadb_config["database"]
        )
        cursor = conn.cursor()

        create_table_query = """
        CREATE TABLE IF NOT EXISTS ibd_ratings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker_symbol VARCHAR(10) NOT NULL UNIQUE,
            ibd_rating INT NOT NULL,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_query)
        conn.commit()
        print("MariaDB table 'ibd_ratings' checked/created successfully.")
        cursor.close()
        conn.close()
        return True
    except mariadb.Error as err:
        print(f"Error initializing MariaDB database: {err}")
        return False


def save_ibd_rating(mariadb_config, ticker_symbol, ibd_rating):
    """
    Saves or updates the IBD Composite Rating for a ticker symbol in the MariaDB database.
    Uses INSERT ... ON DUPLICATE KEY UPDATE for efficiency.
    """
    try:
        conn = mariadb.connect(
            host=mariadb_config["host"],
            port=mariadb_config["port"],
            user=mariadb_config["user"],
            password=mariadb_config["password"],
            database=mariadb_config["database"]
        )
        cursor = conn.cursor()

        insert_update_query = """
        INSERT INTO ibd_ratings (ticker_symbol, ibd_rating)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            ibd_rating = VALUES(ibd_rating),
            last_updated = CURRENT_TIMESTAMP;
        """
        cursor.execute(insert_update_query, (ticker_symbol, ibd_rating))
        conn.commit()
        print(f"Successfully saved/updated IBD rating for {ticker_symbol} in MariaDB.")
        cursor.close()
        conn.close()
        return True
    except mariadb.Error as err:
        print(f"Error saving IBD rating for {ticker_symbol} to MariaDB: {err}")
        return False


def get_stock_data(ticker_symbol, max_retries=5, base_delay=5):
    """
    Fetches historical and fundamental data for a given stock ticker with retries and exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(ticker_symbol)

            end_date = date.today()
            start_date = end_date - timedelta(days=365)
            hist = ticker.history(period='1y')

            info = ticker.info

            if not hist.empty and info:
                print(f"Successfully fetched data for {ticker_symbol} on attempt {attempt + 1}.")
                time.sleep(0.5)
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
                wait_time = base_delay * (2 ** attempt)
                print(f"Waiting {wait_time} seconds before next retry...")
                time.sleep(wait_time)
            else:
                print(f"Max retries ({max_retries}) exhausted for {ticker_symbol}. Could not fetch data.")
                return None, None
        except Exception as e:
            print(f"An unhandled error occurred for {ticker_symbol}: {e}")
            return None, None

    return None, None


def calculate_relative_strength_score(historical_data):
    """
    Calculates an approximate Relative Strength (RS) score, safely handling NaN values.
    """
    if historical_data is None or historical_data.empty:
        return 0

    # Perform ROC calculations, filling NaN with 0 if data is insufficient/missing
    # We use .fillna(0) on the result of iloc[-1] to ensure we get a float, not NaN

    # Note: .iloc[-1] might raise an IndexError if the series is empty or too short.
    # The existing checks handle too-short data by setting ROC to 0 initially.

    # Calculate Rate of Change (ROC), substituting 0 if the last value is NaN
    roc_3_months = historical_data['Close'].pct_change(periods=63).iloc[-1] if len(historical_data) >= 63 else 0
    roc_6_months = historical_data['Close'].pct_change(periods=126).iloc[-1] if len(historical_data) >= 126 else 0
    roc_9_months = historical_data['Close'].pct_change(periods=189).iloc[-1] if len(historical_data) >= 189 else 0
    roc_12_months = historical_data['Close'].pct_change(periods=252).iloc[-1] if len(historical_data) >= 252 else 0

    # New Step: Explicitly check for and replace NaN values with 0
    # This catches cases where yfinance returns a DataFrame, but the last few days' prices are missing.
    roc_3_months = 0.0 if pd.isna(roc_3_months) else roc_3_months
    roc_6_months = 0.0 if pd.isna(roc_6_months) else roc_6_months
    roc_9_months = 0.0 if pd.isna(roc_9_months) else roc_9_months
    roc_12_months = 0.0 if pd.isna(roc_12_months) else roc_12_months

    rs_score = (0.4 * roc_3_months) + (0.2 * roc_6_months) + (0.2 * roc_9_months) + (0.2 * roc_12_months)

    # The conversion to int is now safe because rs_score is guaranteed not to be NaN
    return max(0, min(99, int(rs_score * 10000)))


def calculate_eps_score(fundamental_info):
    """
    Calculates an approximate EPS (Earnings Per Share) score based on growth rates.
    """
    if not fundamental_info:
        return 0

    try:
        eps_growth_quarterly = fundamental_info.get('earningsQuarterlyGrowth', 0) * 100
        eps_growth_yearly = fundamental_info.get('earningsGrowth', 0) * 100

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
    """
    if not fundamental_info:
        return 0

    try:
        sales_growth = fundamental_info.get('revenueGrowth', 0)
        roe = fundamental_info.get('returnOnEquity', 0)

        score = 0
        if sales_growth > 0.15:
            score += 33
        if roe > 0.15:
            score += 33

        return max(0, min(99, score))
    except (KeyError, TypeError):
        return 0


def calculate_composite_rating(ticker_symbol):
    """
    Calculates an approximate IBD Composite Rating for a given ticker.
    """
    historical_data, fundamental_info = get_stock_data(ticker_symbol)

    if historical_data is None or fundamental_info is None:
        return None

    rs_score = calculate_relative_strength_score(historical_data)
    eps_score = calculate_eps_score(fundamental_info)
    smr_score = calculate_smr_score(fundamental_info)

    weight_rs = 0.45
    weight_eps = 0.45
    weight_smr = 0.10

    composite_score = (weight_rs * rs_score) + (weight_eps * eps_score) + (weight_smr * smr_score)

    return int(min(99, max(0, composite_score)))


def read_tickers_from_file(file_path):
    """
    Reads ticker symbols from a text file, one per line.
    """
    tickers = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                ticker = line.strip()
                if ticker:
                    tickers.append(ticker)
        print(f"Successfully read {len(tickers)} tickers from {file_path}")
    except FileNotFoundError:
        print(f"Error: Ticker file not found at {file_path}")
    except Exception as e:
        print(f"An error occurred while reading ticker file {file_path}: {e}")
    return tickers


if __name__ == '__main__':
    config_file = "config.ini"
    ticker_file_path = "my_tickers.txt"  # Ensure this file exists and contains tickers

    # Read MariaDB configuration
    mariadb_config = read_mariadb_config(config_file)
    if not mariadb_config:
        print("MariaDB configuration missing. Exiting.")
        exit()

    # Initialize database (create table if not exists)
    if not initialize_database(mariadb_config):
        print("Database initialization failed. Exiting.")
        exit()

    tickers_to_process = read_tickers_from_file(ticker_file_path)

    if not tickers_to_process:
        print("No tickers found to process. Please check your ticker file.")
    else:
        print("\n--- Calculating IBD Composite Ratings and Saving to MariaDB ---")
        for ticker in tickers_to_process:
            print(f"\nCalculating approximate IBD Composite Rating for {ticker}...")
            composite_rating = calculate_composite_rating(ticker)

            if composite_rating is not None:
                print(f"Approximate IBD Composite Rating for {ticker}: {composite_rating}")
                # Save the rating to MariaDB
                save_ibd_rating(mariadb_config, ticker, composite_rating)
            else:
                print(f"Could not calculate IBD Composite Rating for {ticker}. Not saving to DB.")
        print("\n--- Calculation and Database Update Complete ---")