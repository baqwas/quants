import streamlit as st
import pandas as pd
import mariadb
import toml
import yfinance as yf
import mplfinance as mpf
import io
from datetime import datetime
from dateutil.relativedelta import relativedelta


# --- Configuration and Utility Functions ---

# Helper function to load configuration
@st.cache_resource
def load_config():
    """Loads the database configuration from config.toml."""
    try:
        config = toml.load("config.toml")
        return config.get('database', {}), config.get('analysis', {})
    except FileNotFoundError:
        st.error("Error: config.toml not found. Please ensure it is in the same directory.")
        st.stop()
    except Exception as e:
        st.error(f"Error loading config.toml: {e}")
        st.stop()


# Helper function to establish MariaDB connection
@st.cache_resource(ttl=3600)  # Cache connection for 1 hour
def get_db_connection(db_config):
    """Establishes a connection to the MariaDB database."""
    try:
        conn = mariadb.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database']
        )
        return conn
    except mariadb.Error as e:
        st.error(f"Error connecting to MariaDB: {e}")
        st.stop()


# --- Data Fetching Functions ---

def fetch_signals_from_db(conn):
    """Retrieves all logged stock signals from the database."""
    st.subheader("Recent MACD Signals (from `stock_signals` table)")
    try:
        cursor = conn.cursor(dictionary=True)
        # Assuming the 'stock_signals' table structure based on your log_signal_to_db usage:
        # ticker, signal_date, signal_type, signal_description, close, macd, signal_line, rsi
        query = """
            SELECT 
                ticker, 
                signal_date, 
                signal_type, 
                signal_description,
                close,
                macd,
                signal_line,
                rsi
            FROM stock_signals
            ORDER BY signal_date DESC, ticker ASC
            LIMIT 100
        """
        cursor.execute(query)
        signals = cursor.fetchall()
        cursor.close()

        if signals:
            df = pd.DataFrame(signals)
            df['signal_date'] = pd.to_datetime(df['signal_date']).dt.date

            # Format display table
            st.dataframe(
                df[['signal_date', 'ticker', 'signal_type', 'close', 'signal_description']],
                use_container_width=True,
                column_config={
                    "signal_date": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
                    "ticker": st.column_config.TextColumn("Ticker"),
                    "signal_type": st.column_config.TextColumn("Signal Type"),
                    "close": st.column_config.NumberColumn("Close Price", format="$%.2f"),
                    "signal_description": st.column_config.TextColumn("Description"),
                },
                hide_index=True
            )
            return df['ticker'].unique().tolist()
        else:
            st.info("No recent signals found in the `stock_signals` table.")
            return []

    except mariadb.Error as e:
        st.error(f"Error fetching signals from database: {e}")
        return []


# --- Charting Functions (Adapted from signal_generator.py) ---

def calculate_indicators(df, short_w, long_w, signal_w):
    """Calculates MACD and RSI."""
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
    RS = gain / loss
    df['RSI'] = 100 - (100 / (1 + RS))

    return df


def fetch_and_process_data(ticker, analysis_config):
    """Fetches data and calculates indicators for a single ticker."""
    period_months = analysis_config['period_months']
    short_w = analysis_config['short_window']
    long_w = analysis_config['long_window']
    signal_w = analysis_config['signal_window']

    end_date = datetime.now().date()
    start_date = end_date - relativedelta(months=period_months)

    try:
        # Fetch data using yfinance
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        if data.empty:
            st.warning(f"Could not retrieve data for {ticker}. Check ticker name.")
            return None

        # Clean column names (mplfinance expects 'Open', 'High', etc.)
        data.columns = [col.capitalize() for col in data.columns]

        # Calculate indicators
        processed_df = calculate_indicators(data, short_w, long_w, signal_w)

        return processed_df
    except Exception as e:
        st.error(f"Error fetching or processing data for {ticker}: {e}")
        return None


def generate_mplfinance_chart(processed_df, ticker):
    """Generates the mplfinance chart as a Streamlit image."""

    # 1. Define custom MACD and RSI plots
    macd_colors = ['#1f77b4' if processed_df['MACD_Hist'][i] >= 0 else '#ff7f0e' for i in range(len(processed_df))]

    # MACD Plot
    apds = [
        mpf.make_addplot(processed_df['MACD'], panel=2, color='blue', secondary_y=False, ylabel='MACD'),
        mpf.make_addplot(processed_df['Signal_Line'], panel=2, color='red', secondary_y=False),
        mpf.make_addplot(processed_df['MACD_Hist'], type='bar', panel=2, color=macd_colors, alpha=0.5,
                         secondary_y=False),

        # RSI Plot
        mpf.make_addplot(processed_df['RSI'], panel=3, color='purple', ylabel='RSI (14)', secondary_y=False),
        mpf.make_addplot([70] * len(processed_df), panel=3, color='gray', linestyle='--'),
        mpf.make_addplot([30] * len(processed_df), panel=3, color='gray', linestyle='--'),
    ]

    # 2. Define style and plot parameters
    s = mpf.make_marketcolors(up='green', down='red', inherit=True)
    custom_style = mpf.make_mpf_style(base_mpf_style='yahoo', marketcolors=s,
                                      rc={'figure.titlesize': 'x-large', 'figure.titleweight': 'semibold'})

    # 3. Create chart title
    latest_signal = "Live Chart"

    # Use io.BytesIO to capture the image in memory instead of saving to a file
    buf = io.BytesIO()

    mpf.plot(
        processed_df,
        type='candle',
        style=custom_style,
        title=f"{ticker} - {latest_signal}",
        ylabel='Price ($)',
        volume=True,
        addplot=apds,
        figsize=(12, 8),
        # Save to buffer instead of file
        savefig=dict(fname=buf, dpi=100, format='png')
    )

    # Set the buffer position to the start and return it
    buf.seek(0)
    return buf


# --- Streamlit App Layout ---

def main():
    st.set_page_config(layout="wide", page_title="AI/Quantum Momentum Tracker Dashboard")

    st.title("📈 AI/Quantum Momentum Tracker")
    st.markdown("---")

    db_config, analysis_config = load_config()
    conn = get_db_connection(db_config)

    # 1. Sidebar for Information
    st.sidebar.header("System Status")
    st.sidebar.markdown(f"**Database Host:** `{db_config['host']}`")
    st.sidebar.markdown(f"**Database Name:** `{db_config['database']}`")
    st.sidebar.markdown("---")
    st.sidebar.header("Analysis Parameters")
    st.sidebar.markdown(f"**Data Period:** {analysis_config['period_months']} months")
    st.sidebar.markdown(
        f"**MACD Windows:** Short={analysis_config['short_window']}, Long={analysis_config['long_window']}, Signal={analysis_config['signal_window']}")

    # 2. Main Content: Signals Table and Ticker Selection

    # Fetch signals and get unique tickers
    unique_tickers = fetch_signals_from_db(conn)

    if unique_tickers:
        # Create a select box for the ticker
        selected_ticker = st.selectbox(
            'Select a Ticker to View the Live Chart:',
            options=unique_tickers,
            index=0,
            help='Select one of the tickers that has recently generated a signal.'
        )

        st.markdown("---")
        st.header(f"Live Chart for {selected_ticker}")

        # 3. Chart Generation and Display
        with st.spinner(f"Fetching live data and generating chart for {selected_ticker}..."):
            df_data = fetch_and_process_data(selected_ticker, analysis_config)

        if df_data is not None:
            # Only use the last 120 days for a cleaner, focused chart display
            df_display = df_data.tail(120)
            chart_buffer = generate_mplfinance_chart(df_display, selected_ticker)
            st.image(chart_buffer, caption=f"Last 120 Days of {selected_ticker} (Candlestick, Volume, MACD, RSI)")

        # Display underlying data (optional)
        with st.expander("View Raw Processed Data"):
            st.dataframe(df_data.tail(10))  # Show last 10 rows of calculated data

    # 4. Cleanup (optional but good practice)
    # The get_db_connection is decorated with @st.cache_resource,
    # so we shouldn't explicitly close the connection here.


if __name__ == "__main__":
    main()