import pandas as pd
import mstarpy
from datetime import date, timedelta
import matplotlib.pyplot as plt
import json
import paho.mqtt.client as mqtt
import configparser
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import io
import os


def read_mqtt_config(config_file):
    """
    Reads MQTT configuration from a specified INI file.
    """
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
        mqtt_config = {
            "broker": config["source"]["broker"],
            "port": int(config["source"]["port"]),
            "topic": config["source"]["topic"].strip('"'),
            "username": config["source"]["username"],
            "password": config["source"]["password"],
            "clientId": config["source"]["clientId"]
        }
        return mqtt_config
    except (FileNotFoundError, KeyError) as e:
        print(f"Error reading configuration file: {e}. Please ensure 'config.ini' is present and correctly formatted.")
        return None


def read_smtp_config(config_file):
    """
    Reads SMTP configuration from the same INI file.
    """
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
        smtp_config = {
            "server": config["email"]["smtp_server"],
            "port": int(config["email"]["smtp_port"]),
            "username": config["email"]["smtp_username"],
            "password": config["email"]["smtp_password"],
            "sender": config["email"]["sender_email"],
            "recipient": config["email"]["recipient_email"]
        }
        return smtp_config
    except (FileNotFoundError, KeyError) as e:
        print(f"Error reading SMTP configuration file: {e}. Please ensure the 'email' section is present and correct.")
        return None


# Callback function to handle successful connection
def on_connect(client, userdata, flags, rc, properties):
    if rc == 0:
        print("Connected successfully to MQTT broker")
    else:
        print(f"Failed to connect to MQTT broker, return code {rc}")
    print(f"Connection properties: {properties}")


# Callback function to handle message publishing confirmation
def on_publish(client, userdata, mid, reason_code, properties):
    print(f"Message published successfully (mid={mid})")
    print(f"Reason Code: {reason_code}, Properties: {properties}")


def get_historical_performance_data(ticker, start_date, end_date):
    """
    Fetches historical performance data for a given ticker.
    """
    print(f"Fetching data for {ticker}...")
    try:
        fund = mstarpy.Fund(ticker, country="us")
        df = fund.get_historical_prices(start_date=start_date, end_date=end_date)
        if df.empty:
            print(f"Warning: No data returned for {ticker}. Check ticker symbol.")
            return None
        df.rename(columns={'Close': 'price'}, inplace=True)
        return df
    except Exception as e:
        print(f"An error occurred while fetching data for {ticker}: {e}")
        return None


def find_and_publish_crossovers(data, ticker, client, topic):
    """
    Calculates moving averages and checks for recent crossovers.
    Publishes crossover events to the MQTT broker.
    """
    # Calculate 50-day and 100-day Simple Moving Averages (SMA)
    data['SMA_50'] = data['price'].rolling(window=50).mean()
    data['SMA_100'] = data['price'].rolling(window=100).mean()

    # Check for recent crossovers in the last 5 days
    crossovers = data.tail(5)
    for i in range(1, len(crossovers)):
        # Bullish crossover: 50-day SMA crosses above 100-day SMA
        if crossovers['SMA_50'].iloc[i - 1] <= crossovers['SMA_100'].iloc[i - 1] and \
                crossovers['SMA_50'].iloc[i] > crossovers['SMA_100'].iloc[i]:
            message = {
                "ticker": ticker,
                "event": "bullish_crossover",
                "date": crossovers.index[i].strftime('%Y-%m-%d'),
                "message": f"Bullish Crossover: 50-day SMA crossed above 100-day SMA for {ticker}."
            }
            client.publish(topic, json.dumps(message))
            print(f"Published: {json.dumps(message)}")

        # Bearish crossover: 50-day SMA crosses below 100-day SMA
        elif crossovers['SMA_50'].iloc[i - 1] >= crossovers['SMA_100'].iloc[i - 1] and \
                crossovers['SMA_50'].iloc[i] < crossovers['SMA_100'].iloc[i]:
            message = {
                "ticker": ticker,
                "event": "bearish_crossover",
                "date": crossovers.index[i].strftime('%Y-%m-%d'),
                "message": f"Bearish Crossover: 50-day SMA crossed below 100-day SMA for {ticker}."
            }
            client.publish(topic, json.dumps(message))
            print(f"Published: {json.dumps(message)}")


def plot_fund_vs_benchmark(fund_data, benchmark_data, comparison_days, fund_ticker):
    """
    Plots the performance of a fund against a benchmark and returns the plot data in memory.
    Returns a tuple of (filename, BytesIO buffer) or None.
    """
    # Align data for plotting
    aligned_data = pd.concat([fund_data, benchmark_data], axis=1, join='inner')

    # Calculate the start date for the plot
    end_date = aligned_data.index.max()
    start_date = end_date - timedelta(days=comparison_days)

    # Filter data for the plotting period
    plot_data = aligned_data.loc[start_date:end_date]

    if plot_data.empty:
        print(f"Warning: Not enough data to plot for {fund_ticker}. Skipping plot.")
        return None

    fund_name = fund_data.columns[0]
    benchmark_name = benchmark_data.columns[0]

    # Normalize data to start at 100 for easy comparison
    fund_normalized = (plot_data[fund_name] / plot_data[fund_name].iloc[0]) * 100
    benchmark_normalized = (plot_data[benchmark_name] / plot_data[benchmark_name].iloc[0]) * 100

    plt.figure(figsize=(12, 6))
    plt.plot(fund_normalized, label=fund_name)
    plt.plot(benchmark_normalized, label=benchmark_name)
    plt.title(f"{fund_name} vs {benchmark_name} Performance over {comparison_days} days")
    plt.xlabel("Date")
    plt.ylabel("Normalized Performance (Base 100)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    # Save the plot to an in-memory buffer
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close()  # Close the plot to free up memory
    buffer.seek(0)  # Rewind the buffer to the beginning

    filename = f"performance_{fund_ticker}.png"
    print(f"Plot for {fund_ticker} generated in memory.")
    return (filename, buffer)


def send_email_with_plots(smtp_config, plot_data_list, subject):
    """
    Sends an email with the generated plots from memory as attachments.
    """
    if not plot_data_list:
        print("No plots were generated. Skipping email.")
        return

    msg = MIMEMultipart()
    msg['From'] = smtp_config["sender"]
    msg['To'] = smtp_config["recipient"]
    msg['Subject'] = subject

    body = f"Please find the attached performance plots for the tickers in the file: {subject.split(' ')[0]}.\n\n"
    msg.attach(MIMEText(body, 'plain'))

    for filename, buffer in plot_data_list:
        try:
            img = MIMEImage(buffer.getvalue(), name=filename)
            msg.attach(img)
            print(f"Attached {filename} to email.")
        except Exception as e:
            print(f"Error attaching image to email: {e}")

    try:
        with smtplib.SMTP(smtp_config["server"], smtp_config["port"]) as server:
            server.starttls()
            server.login(smtp_config["username"], smtp_config["password"])
            server.send_message(msg)
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")


def process_ticker_file(client, mqtt_config, smtp_config, file_path, comparison_days, benchmark_ticker, end_date,
                        start_date):
    """
    Processes a single ticker file, fetches data, generates plots, and sends an email.
    """
    filename = os.path.basename(file_path)
    print(f"Processing file: {filename}")

    try:
        with open(file_path, 'r') as f:
            tickers = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found. Skipping.")
        return

    benchmark_data = get_historical_performance_data(benchmark_ticker, start_date=start_date, end_date=end_date)
    if benchmark_data is None:
        print("Failed to retrieve benchmark data. Cannot perform comparison. Skipping file.")
        return

    plot_data_list = []
    for ticker in tickers:
        fund_data = get_historical_performance_data(ticker, start_date=start_date, end_date=end_date)

        if fund_data is not None and not fund_data.empty:
            find_and_publish_crossovers(fund_data, ticker, client, mqtt_config["topic"])
            plot_data = plot_fund_vs_benchmark(fund_data, benchmark_data, comparison_days, ticker)
            if plot_data:
                plot_data_list.append(plot_data)
        else:
            print(f"Failed to retrieve historical data for {ticker}. Skipping plot.")
            print("-" * 30)

    if plot_data_list:
        subject = f"[{os.path.splitext(filename)[0]}] Fund Performance Report - {date.today().strftime('%Y-%m-%d')}"
        send_email_with_plots(smtp_config, plot_data_list, subject)
    else:
        print(f"No plots were generated for file '{filename}'. No email will be sent.")


def main():
    """
    Main function to run the fund analysis and publishing process for all ticker files.
    """
    comparison_days = 252
    benchmark_ticker = "VTSAX"
    config_file = "config.ini"
    tickers_folder = "tickers_folder"

    # Read configuration
    mqtt_config = read_mqtt_config(config_file)
    smtp_config = read_smtp_config(config_file)

    if not mqtt_config or not smtp_config:
        print("Required configuration is missing. Exiting.")
        return

    # --- Paho-MQTT 2.0 Change ---
    client = mqtt.Client(
        client_id=mqtt_config["clientId"],
        protocol=mqtt.MQTTv5,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.on_publish = on_publish

    if mqtt_config["username"] and mqtt_config["password"]:
        client.username_pw_set(mqtt_config["username"], mqtt_config["password"])

    try:
        client.connect(mqtt_config["broker"], mqtt_config["port"], 60)
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return

    client.loop_start()

    end_date = date.today()
    start_date = end_date - timedelta(days=5 * 365)

    try:
        if not os.path.exists(tickers_folder):
            os.makedirs(tickers_folder)
            print(f"Created folder: {tickers_folder}. Please place your ticker .txt files inside.")
            return

        ticker_files = [f for f in os.listdir(tickers_folder) if f.endswith('.txt')]
        if not ticker_files:
            print(f"No .txt files found in the '{tickers_folder}' folder. Please add files with ticker symbols.")
            return

        print(f"Found {len(ticker_files)} ticker files to process.")
        print("-" * 50)

        for ticker_file in ticker_files:
            file_path = os.path.join(tickers_folder, ticker_file)
            process_ticker_file(client, mqtt_config, smtp_config, file_path, comparison_days, benchmark_ticker,
                                end_date, start_date)
            print("-" * 50)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()