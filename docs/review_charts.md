# Stock Screener & Chart Viewer Streamlit App
## User Manual

This manual provides a comprehensive guide for users to set up, run, and effectively use the review_charts.py Streamlit application for daily stock analysis.

1. Introduction

The **Stock Screener & Chart Viewer** is a Streamlit web application designed to help users visualize technical analysis charts for selected S&P 500 stocks. It fetches historical financial data, calculates key metrics, and displays interactive charts, providing insights into stock performance and potential trends.

2. Features

    Interactive Stock Selection: Easily choose a stock from a sorted list of S&P 500 companies via a sidebar dropdown.

    Customizable Date Range: Select specific start and end dates to view historical data and charts.

    Technical Analysis Charts: Visualize various popular technical indicators, including:

        Price and Moving Averages: Displaying closing prices along with 50-day and 200-day Simple Moving Averages (SMA).

        Relative Strength Index (RSI): An oscillator that measures the speed and change of price movements.

        Moving Average Convergence Divergence (MACD): A trend-following momentum indicator that shows the relationship between two moving averages of a security’s price. Includes crossover signals.

        Rate of Change (ROC): Measures the percentage change between the current price and a price n periods ago.

        Chande Momentum Oscillator (CMO): A momentum indicator that measures overbought/oversold conditions.

3. Prerequisites

Before running the application, ensure you have the following installed on your system:

    Python 3.7+: Download from Python's Official Website.

    Required Python Libraries:

        streamlit

        yfinance

        pandas

        matplotlib

You can install these libraries using pip:
Bash

pip install streamlit yfinance pandas matplotlib

4. Application Setup

To run the review_charts.py app, you need three files in the same directory:

    review_charts.py (the main application script)

    config.ini (configuration file for settings)

    screener2.csv (CSV file containing stock ticker data)

4.1. config.ini Configuration

The config.ini file stores essential settings, including email configurations (though not directly used by the Streamlit UI, they are part of the script) and screening criteria.

Example config.ini structure:
Ini, TOML

```
[source]
broker=broker.parkcircus.org
port=1883
topic="/quants/xover"
username=mqtt_client
password=password
clientId=moi

[email]
smtp_server = smtp.parkcircus.org
smtp_port = 587
smtp_username = worker@parkcircus.org
smtp_password = TopSecret
sender_email = assistant@parkcircus.org
recipient_email = boss@parkcircus.org

[mariadb]
host = dbms.parkcircus.org
port = 3306
user = worker
password = TopSecret
database = ha

[criteria]
screener_file = screener2.csv
EPS_GROWTH_ANNUAL_THRESHOLD = 0.25
SALES_GROWTH_ANNUAL_THRESHOLD = 0.20
ROE_THRESHOLD = 0.15
PRICE_NEAR_52W_HIGH_PERCENTAGE = 0.95
AVG_VOLUME_MINIMUM = 500000
```

Important Note for config.ini:
The previous error invalid literal for int() with base 10: 'Tapuria#1' occurred because smtp_password was incorrectly read as an integer. While the provided review_charts.py has been updated to correctly read it as a string, ensure that smtp_password in your config.ini file is treated as a string value by the application. This is typically handled by using config.get() instead of config.getint() in the Python script.

4.2. screener2.csv File

This CSV file contains the list of stocks that will be available for selection in the Streamlit app's sidebar. It should have at least the following columns (order matters as per the script's load_stock_list_for_sidebar function):

    Column 1 (index 0): Sequence Number (can be ignored by the script)

    Column 2 (index 1): Company Name

    Column 3 (index 2): Ticker Symbol

    Column 4 (index 3): Sector

Example screener2.csv content:
Code snippet

```csv
1,Apple Inc,AAPL,Information Technology
2,Microsoft Corp,MSFT,Information Technology
3,Amazon Com Inc,AMZN,Consumer Discretionary
...
```

5. How to Run the App

    Navigate to the directory where you have saved review_charts.py, config.ini, and screener2.csv using your terminal or command prompt.
    Bash

`cd /path/to/your/app`

Run the Streamlit application using the command:
Bash

    `streamlit run review_charts.py`

    Your web browser should automatically open to a new tab displaying the Streamlit app (usually at http://localhost:8501). If it doesn't, copy and paste the URL provided in your terminal into your browser.

6. Usage Guide

Once the app is running in your browser, follow these steps:

6.1. Select a Stock

    On the left sidebar, you will see a section titled "Select a Stock to View Charts".

    Use the dropdown menu to select a company. The list is displayed as "Company Name (Ticker)".

6.2. Select Date Range

    Below the stock selection, you'll find the "Select Date Range for Charts" section.

    Choose your desired Start Date and End Date using the date pickers. The charts will update to reflect the data within this chosen range.

6.3. Review Charts

The main area of the application will display the following charts for your selected stock and date range:

    1. Price and Moving Averages: Shows the stock's closing price and its 50-day and 200-day Simple Moving Averages. This helps identify trends and potential support/resistance levels.

    2. Relative Strength Index (RSI): Indicates whether a stock is overbought or oversold. Values typically range from 0 to 100, with 70 often considered overbought and 30 oversold.

    3. Moving Average Convergence Divergence (MACD): Displays a MACD line, a Signal line, and a Histogram. Crossovers between the MACD and Signal lines are marked with green (buy) or red (sell) signals.

    4. Rate of Change (ROC): Measures the percentage price change over a specified period, indicating momentum.

    5. Chande Momentum Oscillator (CMO): Similar to RSI, it measures momentum and overbought/oversold conditions, typically ranging from -100 to +100.

7. Troubleshooting

    "An unexpected error occurred while reading the config file: invalid literal for int() with base 10: 'Tapuria#1'. Using default values."

        Reason: This specific error occurs when the smtp_password in config.ini is being interpreted as a number instead of a string in an older version of the script.

        Solution: Ensure your review_charts.py script is updated to correctly read smtp_password as a string using config['email'].get('smtp_password', fallback="your_email_password"). The provided script in the context addresses this.

    "Error reading config.ini: Missing section or key." / "config.ini not found."

        Reason: The config.ini file is either missing, incorrectly named, or essential sections/keys defined in the script are absent.

        Solution: Verify that config.ini is present in the same directory as review_charts.py and that it contains all the necessary sections ([email], [criteria], etc.) and keys as per the example in Section 4.1.

    "screener2.csv not found." / "Error reading screener2.csv."

        Reason: The screener2.csv file is missing or corrupted.

        Solution: Ensure screener2.csv is in the same directory and is properly formatted with the expected columns.

    "Could not fetch historical data for [TICKER]."

        Reason: This could be due to an invalid ticker symbol, an incorrect date range (e.g., trying to fetch data before the stock existed), or temporary issues with the yfinance data source.

        Solution: Double-check the ticker symbol, adjust the date range, or try again later.

    Charts not showing or displaying "insufficient data" warnings:

        Reason: Some technical indicators (like SMAs, RSI, MACD) require a certain amount of historical data to be calculated. If your selected date range is too short, these indicators cannot be computed.

        Solution: Extend the "Start Date" in the sidebar to include more historical data.