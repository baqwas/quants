#!/usr/bin/env python3
"""
analyze_and_alert.py (Updated to use smtplib for direct SMTP connection)

###################################################################################
# SCRIPT: analyze_and_alert.py
# AUTHOR: AI Assistant
# DATE:   December 2025
#
# DESCRIPTION:
# This script analyzes time series data from the 'ha.ibd_ratings' MariaDB table.
# It performs the following steps:
# 1. Reads database and SMTP configurations from a 'config.toml' file.
# 2. Fetches all historical IBD ratings for every unique ticker.
# 3. For each ticker, it uses Exponential Smoothing to predict the next day's rating.
# 4. If the predicted rating breaches the critical 20/80 thresholds, a time series
#    plot is generated and saved as a temporary image file.
# 5. An email alert is sent directly to the SMTP server (bezaman.parkcircus.org)
#    using 'smtplib', attaching the plot.
# 6. Temporary plot files are cleaned up.
#
# USER INTERFACE OPTIONS:
# - Configuration: Modify 'config.toml' for database and direct SMTP credentials.
# - Execution: Run directly from the command line:
#   $ python analyze_and_alert.py
# - Dependencies: Requires 'mariadb', 'pandas', 'toml', 'statsmodels', 'matplotlib'.
#   Install using: pip install mariadb pandas toml statsmodels matplotlib
#
###################################################################################
"""

import mariadb
import pandas as pd
from statsmodels.tsa.api import ExponentialSmoothing
import matplotlib.pyplot as plt
import toml
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import date, timedelta

# --- CONFIGURATION & SETUP ---
CONFIG_FILE = "config.toml"
TEMP_PLOT_FILE = "ibd_rating_alert_{}.png"
ALERT_THRESHOLD_LOW = 20
ALERT_THRESHOLD_HIGH = 80


def read_config(config_file):
    """Reads configuration settings from the TOML file."""
    try:
        with open(config_file, 'r') as f:
            config = toml.load(f)
        return config
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_file}")
        return None
    except toml.TomlDecodeError as e:
        print(f"Error decoding TOML file: {e}")
        return None


def fetch_all_ratings(db_config):
    """Fetches all historical IBD ratings from the MariaDB table."""
    try:
        conn = mariadb.connect(**db_config)
        cursor = conn.cursor()

        query = """
                SELECT ticker_symbol, ibd_rating, last_updated
                FROM ibd_ratings
                ORDER BY ticker_symbol, last_updated; \
                """
        cursor.execute(query)
        data = cursor.fetchall()

        df = pd.DataFrame(data, columns=['ticker_symbol', 'ibd_rating', 'last_updated'])

        cursor.close()
        conn.close()
        return df

    except mariadb.Error as err:
        print(f"Database error: {err}")
        return pd.DataFrame()


def send_alert_email(ticker, prediction, plot_path, smtp_config):
    """Sends an email alert with the plot attached using smtplib."""

    sender = smtp_config.get("sender_email")
    recipient = smtp_config.get("recipient_email")
    smtp_host = smtp_config.get("smtp_host")
    smtp_port = smtp_config.get("smtp_port")
    smtp_user = smtp_config.get("smtp_user")
    smtp_password = smtp_config.get("smtp_password")

    direction = "FALL BELOW" if prediction < ALERT_THRESHOLD_LOW else "RISE ABOVE"
    subject = f"IBD ALERT: {ticker} Predicted to {direction} {ALERT_THRESHOLD_LOW}/{ALERT_THRESHOLD_HIGH}!"

    # Create the root message (multipart/mixed)
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject

    # 1. Attach the text body
    text_body = f"""
Critical IBD Rating Alert:

The approximate IBD Composite Rating for {ticker} is predicted to move significantly tomorrow.
- Today's Date: {date.today().strftime('%Y-%m-%d')}
- Predicted Rating (Tomorrow): {prediction:.2f}

Action Required: Please review the attached time series plot for confirmation.
"""
    msg.attach(MIMEText(text_body, 'plain'))

    # 2. Attach the image file
    try:
        with open(plot_path, 'rb') as fp:
            img = MIMEImage(fp.read())
        img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(plot_path))
        msg.attach(img)
    except FileNotFoundError:
        print(f"Warning: Plot file {plot_path} not found. Sending text-only alert.")

    # 3. Connect and send
    try:
        # Use SMTP_SSL for port 465 or SMTP + STARTTLS for port 587
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()  # Upgrade connection to secure/encrypted mode
        server.login(smtp_user, smtp_password)
        server.sendmail(sender, recipient, msg.as_string())
        server.quit()
        print(f"Alert email for {ticker} sent successfully via SMTPLIB.")

    except smtplib.SMTPAuthenticationError:
        print("ERROR: SMTP Authentication Failed. Check smtp_user and smtp_password in config.toml.")
    except smtplib.SMTPConnectError as e:
        print(f"ERROR: Could not connect to SMTP server {smtp_host}:{smtp_port}. {e}")
    except Exception as e:
        print(f"An unexpected error occurred during email sending: {e}")


def analyze_and_plot(df_all, db_config, smtp_config):
    """Analyzes each ticker's ratings, predicts the next value, and plots/alerts if necessary."""

    critical_tickers = []

    # Group by ticker symbol
    for ticker, df_ticker in df_all.groupby('ticker_symbol'):

        # We need at least 3 data points for robust Exponential Smoothing
        if len(df_ticker) < 3:
            print(f"Skipping {ticker}: Insufficient data points ({len(df_ticker)}).")
            continue

        # 1. Prepare Data for Time Series Model
        # Set the update time as the index for time series analysis
        ts_data = df_ticker.set_index('last_updated')['ibd_rating']

        # 2. Build and Fit Exponential Smoothing Model
        try:
            # Use Triple Exponential Smoothing (ETS) with an additive trend/seasonality
            model = ExponentialSmoothing(
                ts_data,
                seasonal_periods=7,
                trend='add',
                seasonal='add',
                initialization_method='estimated'
            ).fit()

            # 3. Predict the Next Day's Rating
            forecast = model.forecast(1)
            predicted_rating = forecast.iloc[0]

        except Exception as e:
            print(f"Error modeling data for {ticker}: {e}")
            continue

        print(f"Prediction for {ticker}: {predicted_rating:.2f}")

        # 4. Check Alert Threshold
        if predicted_rating <= ALERT_THRESHOLD_LOW or predicted_rating >= ALERT_THRESHOLD_HIGH:
            print(f"!!! ALERT: {ticker} predicted rating ({predicted_rating:.2f}) is critical.")
            critical_tickers.append(ticker)

            # 5. Generate Plot
            plot_path = TEMP_PLOT_FILE.format(ticker)

            plt.figure(figsize=(10, 6))

            # Plot historical data
            plt.plot(ts_data.index, ts_data.values, marker='o', linestyle='-', color='blue',
                     label='Historical IBD Rating')

            # Plot prediction
            last_date = ts_data.index[-1]
            next_date = last_date + timedelta(days=1)

            plt.plot(
                [last_date, next_date],
                [ts_data.iloc[-1], predicted_rating],
                marker='X',
                linestyle='--',
                color='red',
                label='Next Day Prediction'
            )

            # Add alert line
            plt.axhline(y=ALERT_THRESHOLD_HIGH, color='green', linestyle=':',
                        label=f'Threshold ({ALERT_THRESHOLD_HIGH})')
            plt.axhline(y=ALERT_THRESHOLD_LOW, color='orange', linestyle=':',
                        label=f'Threshold ({ALERT_THRESHOLD_LOW})')

            plt.title(f'IBD Rating Trend for {ticker}\nPredicted Next Rating: {predicted_rating:.2f}', fontsize=14)
            plt.xlabel('Date', fontsize=12)
            plt.ylabel('IBD Rating (0-99)', fontsize=12)
            plt.legend()
            plt.grid(True)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()

            # Save and send alert
            plt.savefig(plot_path)
            plt.close()  # Close figure to free memory

            # 6. Send Email Alert with attachment
            send_alert_email(ticker, predicted_rating, plot_path, smtp_config)

    return critical_tickers


def cleanup(critical_tickers):
    """Removes temporary plot files."""
    for ticker in critical_tickers:
        plot_path = TEMP_PLOT_FILE.format(ticker)
        if os.path.exists(plot_path):
            os.remove(plot_path)
            print(f"Cleaned up temporary file: {plot_path}")


# --- MAIN EXECUTION ---
if __name__ == '__main__':

    # 1. Read Configuration
    config = read_config(CONFIG_FILE)
    if config is None:
        exit()

    db_config = config.get('database')
    smtp_config = config.get('smtp')

    # 2. Fetch Data
    df_ratings = fetch_all_ratings(db_config)
    if df_ratings.empty:
        print("No data fetched from the database. Exiting.")
        exit()

    # 3. Analyze, Predict, and Alert
    print("\n--- Starting IBD Rating Trend Analysis ---")
    critical_tickers = analyze_and_plot(df_ratings, db_config, smtp_config)
    print("\n--- Analysis Complete ---")

    if not critical_tickers:
        print("No critical rating changes predicted.")

    # 4. Cleanup
    cleanup(critical_tickers)