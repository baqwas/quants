#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
signal_generator.py

================================================================================
PROJECT: AI/Quantum Tech Stock Momentum Tracker
AUTHOR: Matha Goram
DATE: 2025-11-27
VERSION: 1.6.16 (Fixes: Meaningless status log approximation)
================================================================================

PURPOSE & METHODOLOGY:
--------------------
Monitors high-tech stocks using the MACD crossover strategy.

EXECUTION & OUTPUT:
------------------
1. Downloads 6 months of daily stock data via the yfinance API.
2. Calculates MACD and RSI for all monitored tickers.
3. If a crossover is detected (last 7 days), sends an email alert with the chart.
4. Consolidates data retrieval and database logging failures into a single warning email.
5. Sends a final status report (status_log.txt) via email attachment.

REQUIRED EXTERNAL FILES:
------------------------
1. config.toml: MUST contain valid credentials for [database], [analysis], and [smtp].
2. tickers.txt: MUST contain a newline-separated list of stock tickers (e.g., NVDA (Nvidia - GPUs, Ecosystem)).
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

# --- Configuration Constants ---
STATUS_LOG_FILE = "status_log.txt"
LOOKBACK_DAYS = 7  # Number of days to check for a signal (including today's close)
CHART_DIR = "charts"
SMTP_REPORT_SUBJECT = "⚠️ Momentum Tracker - Data/DB Failure Report"


# --- Utility Functions ---

def load_config():
    """Loads and validates the configuration from config.toml."""
    try:
        config = toml.load("config.toml")

        # Ensure 'database' section is used
        db_config = config.get('database', {})
        if not all(key in db_config for key in ['host', 'port', 'user', 'password', 'database']):
            raise ValueError("Missing required keys in [database] section of config.toml.")

        # Ensure 'smtp' section is used
        smtp_config = config.get('smtp', {})
        if not all(key in smtp_config for key in
                   ['smtp_server', 'smtp_port', 'smtp_username', 'smtp_password', 'sender_email', 'recipient_email']):
            raise ValueError("Missing required keys in [smtp] section of config.toml.")

        # Ensure 'analysis' section is used
        analysis_config = config.get('analysis', {})
        if not all(key in analysis_config for key in ['period_months', 'short_window', 'long_window', 'signal_window']):
            raise ValueError("Missing required keys in [analysis] section of config.toml.")

        # Ensure 'static' section is used
        static_config = config.get('static', {})
        if 'tickers_file' not in static_config:
            raise ValueError("Missing 'tickers_file' key in [static] section of config.toml.")

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
    Logs a detected MACD crossover signal into the MariaDB database.

    Args:
        db_config (dict): Database connection parameters.
        ticker (str): The stock ticker symbol.
        signal_type (str): The type of signal (e.g., 'MACD BULLISH').
        signal_description (str): Detailed description of the event.
        signal_date (date): The date the signal occurred (used as PK).
        data_series (pd.Series): Pandas series containing 'Close', 'MACD', 'Signal_Line', 'RSI'.

    Returns:
        bool: True on successful log, False otherwise.
    """
    conn = None
    success = False  # Flag to track success
    try:
        conn = mariadb.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
        )
        cursor = conn.cursor()

        # CRITICAL FIX: Column names match the DDL:
        # ticker_symbol, signal_date, signal_type, description, price_at_signal, macd_value, signal_value, rsi_value
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

        # Data values must map correctly to the columns in the INSERT query
        values = (
            ticker,  # ticker_symbol (PK part 1)
            signal_date,  # signal_date (PK part 2)
            signal_type,  # signal_type
            signal_description,  # description
            float(data_series['Close']),  # price_at_signal
            float(data_series['MACD']),  # macd_value
            float(data_series['Signal_Line']),  # signal_value
            float(data_series['RSI'])  # rsi_value
        )

        cursor.execute(insert_query, values)
        conn.commit()
        success = True  # Set success to True after commit

        print(f"  -> Successfully logged {ticker} {signal_type} signal to MariaDB.")

    except mariadb.Error as e:
        # Catch and log MariaDB-specific errors
        print(f"  -> ERROR: Failed to log signal for {ticker} to MariaDB: {e}")
        # DO NOT re-raise
    except Exception as e:
        # Catch and log any other exceptions
        print(f"  -> ERROR: An unexpected error occurred during database logging for {ticker}: {e}")
        # DO NOT re-raise
    finally:
        # V1.6.14 FIX: Removed check for 'conn.closed' which is not supported by
        # the mariadb connector, leading to an AttributeError.
        if conn:
            conn.close()

    return success  # Return the status


# V1.6.16: ADDED no_signal_count AND true_failure_count to signature and log content
def generate_status_log(tickers_file, total_processed, crossover_count, no_signal_count, true_failure_count):
    """Creates a simple log file summarizing the execution results with meaningful counts."""

    # 1. Read the raw ticker list from the input file
    try:
        with open(tickers_file, 'r') as f:
            raw_tickers = [line.strip() for line in f if line.strip()]
    except Exception as e:
        raw_tickers = ["(Error reading tickers.txt)"]
        print(f"ERROR: Could not read tickers file for log generation: {e}")

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    log_content = f"""
================================================================================
AI/QUANTUM MOMENTUM TRACKER - DAILY EXECUTION SUMMARY
Timestamp: {timestamp}
--------------------------------------------------------------------------------
Configuration:
- MACD Windows: (12, 26, 9)
- RSI Window: (14)
- Signal Lookback: {LOOKBACK_DAYS} days
- Tickers file: {tickers_file}

Execution Stats:
- Total Tickers Processed: {total_processed}
- Signals Detected (Crossovers): {crossover_count}
- Successfully Processed (No Signal): {no_signal_count}
- CRITICAL Failures (Data/Logging/Unhandled): {true_failure_count}

Full Ticker List:
{', '.join(raw_tickers)}
================================================================================
"""
    try:
        with open(STATUS_LOG_FILE, 'w') as f:
            f.write(log_content.strip())
        print(f"\nSTATUS: Successfully generated execution summary at {STATUS_LOG_FILE}")
    except Exception as e:
        print(f"ERROR: Failed to write status log file: {e}")


def create_chart(df, ticker, signal_title):
    """
    Generates a candlestick chart with MACD and RSI panels.
    Returns the file path of the saved chart.
    """
    if not os.path.exists(CHART_DIR):
        os.makedirs(CHART_DIR)

    chart_path = os.path.join(CHART_DIR, f"{ticker}_{date.today().strftime('%Y%m%d')}.png")

    # 1. Define custom MACD and RSI plots
    # V1.6.15 FIX: Use .iloc[i] to explicitly access by position and suppress FutureWarning.
    macd_colors = ['#1f77b4' if df['MACD_Hist'].iloc[i] >= 0 else '#ff7f0e' for i in range(len(df))]

    apds = [
        # MACD Plot
        mpf.make_addplot(df['MACD'], panel=2, color='blue', secondary_y=False, ylabel='MACD'),
        mpf.make_addplot(df['Signal_Line'], panel=2, color='red', secondary_y=False),
        mpf.make_addplot(df['MACD_Hist'], type='bar', panel=2, color=macd_colors, alpha=0.5, secondary_y=False),

        # RSI Plot
        mpf.make_addplot(df['RSI'], panel=3, color='purple', ylabel='RSI (14)', secondary_y=False),
        mpf.make_addplot([70] * len(df), panel=3, color='gray', linestyle='--'),
        mpf.make_addplot([30] * len(df), panel=3, color='gray', linestyle='--'),
    ]

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
            figsize=(12, 8),
            savefig=dict(fname=chart_path, dpi=100)
        )
        print(f"  -> Chart created and saved to {chart_path}")
        return chart_path
    except Exception as e:
        print(f"ERROR: Failed to create chart for {ticker}: {e}")
        return None


# --- Core Analysis Functions ---

def calculate_indicators(df, short_w, long_w, signal_w):
    """Calculates MACD, MACD Signal Line, MACD Histogram, and RSI."""
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
    # Check for division by zero
    with np.errstate(divide='ignore', invalid='ignore'):
        RS = gain / loss
        df['RSI'] = 100 - (100 / (1 + RS))

    # FIX: Explicitly assign result to avoid FutureWarning on chained assignment/copy
    # This addresses the previous Pandas warning on line 286.
    df['RSI'] = df['RSI'].fillna(50)  # Fill initial NaN values (typical practice)

    return df


def generate_signal(df):
    """
    Checks for a MACD crossover signal within the last LOOKBACK_DAYS.
    Returns the signal string and the date of the most recent signal.
    """

    # Check only the last LOOKBACK_DAYS days
    recent_data = df.tail(LOOKBACK_DAYS)

    signal = None
    signal_date = None

    for i in range(1, len(recent_data)):

        # Current and previous MACD and Signal Line values
        macd_current = recent_data['MACD'].iloc[i]
        signal_current = recent_data['Signal_Line'].iloc[i]
        macd_prev = recent_data['MACD'].iloc[i - 1]
        signal_prev = recent_data['Signal_Line'].iloc[i - 1]

        # Crossover logic
        bullish_crossover = (macd_prev < signal_prev) and (macd_current >= signal_current)
        bearish_crossover = (macd_prev > signal_prev) and (macd_current <= signal_current)

        if bullish_crossover:
            signal = "MACD BULLISH"
            signal_date = recent_data.index[i]
        elif bearish_crossover:
            signal = "MACD BEARISH"
            signal_date = recent_data.index[i]

    # Always return the *most recent* signal detected in the lookback window
    if signal_date is not None:
        signal_data_series = df.loc[signal_date]
        close_price = signal_data_series['Close']
        macd_val = signal_data_series['MACD']
        signal_val = signal_data_series['Signal_Line']
        rsi_val = signal_data_series['RSI']

        description = (
            f"{signal} Crossover detected. "
            f"MACD ({macd_val:.4f}) crossed the Signal Line ({signal_val:.4f}). "
            f"Close: ${close_price:.2f}. RSI: {rsi_val:.2f}."
        )
        return signal, description, signal_date.to_pydatetime()

    return None, None, None


# --- Email Functions ---

def create_email_message(sender, recipient, subject, body, attachment_path=None):
    """Creates a MIME message with optional attachment."""
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject

    # Attach body text
    msg.attach(MIMEText(body, 'plain'))

    # Add a signature to help filter email on the recipient's side
    signature = MIMEText("\n---\nAI/Quantum Momentum Tracker (v1.6.16)", 'plain')
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

        # Use a context manager for the SMTP connection
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

    body = (
        "The following stocks failed data retrieval or database logging during the daily run:\n\n"
        "Ticker | Reason\n"
        "---|---\n"
    )
    for ticker, reason in failed_tickers_report:
        body += f"{ticker} | {reason}\n"

    body += "\nReview the logs for full details."

    # Use the shared function for sending the email
    send_email_with_attachment(
        smtp_config,
        recipient_email,
        SMTP_REPORT_SUBJECT,
        body,
        attachment_path=None  # No attachment for this specific report
    )


def send_signal_email(smtp_config, ticker, signal_type, signal_description, chart_path):
    """Sends a single signal email with the chart attached."""

    subject = f"🚨 MACD Signal Detected: {ticker} - {signal_type}"
    body = (
        f"A strong momentum signal has been detected for {ticker}:\n\n"
        f"**Signal Type:** {signal_type}\n"
        f"**Date:** {date.today().strftime('%Y-%m-%d')}\n"
        f"**Details:** {signal_description}\n\n"
        f"The corresponding technical chart is attached for your review."
    )

    # Use the shared function for sending the email
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
    print("================================================================")

    # 0. Load Configuration and Tickers
    db_config, smtp_config, analysis_config, static_config = load_config()
    TICKERS_FILE = static_config['tickers_file']
    RECIPIENT_EMAIL = smtp_config['recipient_email']

    # Ensure the chart directory exists
    if not os.path.exists(CHART_DIR):
        os.makedirs(CHART_DIR)

    # 1. Load Tickers
    tickers = load_tickers(TICKERS_FILE)
    if not tickers:
        print("INFO: No tickers to process. Exiting.")
        return

    # 2. Initialize counters and lists
    total_tickers_processed = 0
    crossover_count = 0
    no_signal_count = 0                         # V1.6.16: NEW COUNTER
    failed_tickers_report = []
    charts_to_cleanup = []

    # 3. Process each ticker
    for ticker_line in tickers:
        total_tickers_processed += 1

        # Extract the actual ticker symbol (first word/token)
        ticker_parts = ticker_line.split(' ', 1)
        actual_ticker = ticker_parts[0]

        # Skip processing if it's a comment/header line
        if actual_ticker.startswith('#'):
            print(f"\nProcessing Header/Comment: {ticker_line} ({total_tickers_processed}/{len(tickers)})")
            continue

        # Print the full line for user context, but process only the extracted ticker
        print(f"\nProcessing Ticker: {ticker_line} ({total_tickers_processed}/{len(tickers)})")
        chart_path = None  # Reset chart path for each loop iteration

        try:
            # --- Data Retrieval and Calculation ---
            period_months = analysis_config['period_months']
            short_w = analysis_config['short_window']
            long_w = analysis_config['long_window']
            signal_w = analysis_config['signal_window']

            end_date = datetime.now().date()
            start_date = end_date - relativedelta(months=period_months)

            # Fetch data using yfinance - USE THE EXTRACTED TICKER!
            # FIX: Explicitly set auto_adjust=True to suppress FutureWarning
            # FIX: Removed the deprecated 'show_errors' argument (The root cause of the previous crash)
            download_result = yf.download(actual_ticker, start=start_date, end=end_date, progress=False,
                                          auto_adjust=True)

            # CRITICAL FIX (V1.6.9): Robustly handle yfinance return types (DataFrame or Tuple).
            if isinstance(download_result, tuple):
                data = download_result[0]
                # Log a warning if we had to extract data from a tuple
                if len(download_result) > 1 and download_result[1]:
                    print(f"  -> WARNING: YFinance returned data with warnings/messages: {download_result[1]}")
            else:
                data = download_result

            # Ensure 'data' is a DataFrame before proceeding with DataFrame operations
            if not isinstance(data, pd.DataFrame):
                failure_reason = f"Data retrieval failed (yfinance returned non-DataFrame object: {type(data)})."
                print(f"  -> CRITICAL ERROR: {failure_reason}")
                failed_tickers_report.append((ticker_line, failure_reason))
                continue

            if data.empty:
                failure_reason = "Data retrieval failed (yfinance returned empty data)."
                print(f"  -> ERROR: {failure_reason}")
                failed_tickers_report.append((ticker_line, failure_reason))
                continue

            # CRITICAL FIX (V1.6.10): Defensive column handling against unexpected MultiIndex structure
            # This explicitly checks for and flattens column names that are unexpectedly tuples.
            if any(isinstance(col, tuple) for col in data.columns):
                # Flatten MultiIndex columns and capitalize the first element (e.g., ('Close', 'NVDA') -> 'Close')
                data.columns = [item[0].capitalize() if isinstance(item, tuple) else item.capitalize() for item in
                                data.columns]
                print("  -> WARNING: Unexpected multi-level column headers detected and normalized.")
            else:
                # Standard capitalization for single ticker data (e.g., 'open' -> 'Open')
                data.columns = [col.capitalize() for col in data.columns]

            # Calculate indicators
            processed_df = calculate_indicators(data, short_w, long_w, signal_w)

            # --- Signal Generation ---
            signal_type, signal_description, signal_date_dt = generate_signal(processed_df)

            if signal_type:
                crossover_count += 1
                print(f"  -> SIGNAL DETECTED: {signal_type} on {signal_date_dt.strftime('%Y-%m-%d')}")

                # Get the specific data series for the signal date (required for logging)
                # V1.6.13 FIX: Using string-based index lookup to avoid KeyError from
                # mismatch between datetime.date and pandas Timestamp index objects.
                signal_date_str = signal_date_dt.strftime('%Y-%m-%d')
                signal_data_series = processed_df.loc[signal_date_str]

                # --- Log Signal to Database (Now returns status instead of re-raising) ---
                db_success = log_signal_to_db(
                    db_config,
                    actual_ticker,  # Log only the symbol
                    signal_type,
                    signal_description,
                    signal_date_dt.date(),  # Pass as date object
                    signal_data_series
                )

                if not db_success:
                    # Log failure to the report list
                    failure_reason = "DB LOGGING FAILED (See previous error logs for details)"
                    print(f"  -> WARNING: {failure_reason}")
                    failed_tickers_report.append((ticker_line, failure_reason))
                    # Execution continues to charting and email regardless

                # 5. Create Chart (plotting the last 100 days)
                plot_df = processed_df.tail(100)
                chart_title_signal = signal_type  # Use the signal type as the title
                chart_path = create_chart(plot_df, actual_ticker,
                                          chart_title_signal)  # Chart file named with actual ticker

                if chart_path:
                    charts_to_cleanup.append(chart_path)

                    # 6. Send Signal Email
                    send_signal_email(smtp_config, actual_ticker, signal_type, signal_description,
                                      chart_path)  # Email with actual ticker
            else:
                no_signal_count += 1    # V1.6.16: Increment new counter
                print("  -> No recent crossover signal found.")
                pass

        except Exception as e:
            # Catch all unhandled exceptions and log them
            # Added a type check to prevent strange exception object corruption (like datetime.date)
            if isinstance(e, date):
                failure_reason = f"UNHANDLED EXCEPTION: Corrupted/Date Exception object ({e})"
            else:
                failure_reason = f"UNHANDLED EXCEPTION: {e}"

            # Use ticker_line in the output for context
            print(f"  -> An unhandled error occurred while processing {ticker_line}: {failure_reason}")
            failed_tickers_report.append((ticker_line, failure_reason))

    # --- Final Reporting and Cleanup ---
    print("----------------------------------------------------------------")

    # 1. Generate the status log file
    # V1.6.16: Pass all three distinct counts
    generate_status_log(TICKERS_FILE, total_tickers_processed, crossover_count, no_signal_count, len(failed_tickers_report))

    # 2. Send the consolidated failure report
    if failed_tickers_report:
        send_failure_report_email(smtp_config, failed_tickers_report)

    # 3. Email the status log file
    status_subject = f"📈 Momentum Tracker Daily Summary: {datetime.now().strftime('%Y-%m-%d')}"
    # V1.6.16: Update email body
    status_body = (
        f"Daily processing complete.\n\n"
        f"**Signals Detected:** {crossover_count}\n"
        f"**Processed (No Signal):** {no_signal_count}\n"
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

    # 4. File Cleanup - ENABLED
    print("\nStarting file cleanup...")

    # Add the status log file to the cleanup list if it exists
    if os.path.exists(STATUS_LOG_FILE):
        charts_to_cleanup.append(STATUS_LOG_FILE)

    # Clean up all generated chart files and the status log file
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