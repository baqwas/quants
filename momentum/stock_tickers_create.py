import argparse
import re
import mariadb
import toml  # Requires: pip install toml
import sys
from typing import List, Dict, Optional


# --- Parsing Logic ---

def load_config(config_file: str) -> Dict:
    """Loads and returns the configuration dictionary from the TOML file."""
    print(f"Loading configuration from: {config_file}")
    with open(config_file, 'r') as f:
        config = toml.load(f)
    return config


def load_tickers_data(
        filename: str,
        thematic_focus: str,
        default_exchange: str
) -> List[Dict[str, str]]:
    """
    Reads the tickers file and parses it into structured data records
    that match the 'stock_tickers' schema, using values from the config.
    """

    records = []
    current_category = "UNCATEGORIZED"  # Default category

    try:
        with open(filename, 'r') as f:
            file_content = f.read()
    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        return []

    for line in file_content.strip().split('\n'):
        clean_line = line.strip()

        if not clean_line or clean_line.startswith(';'):  # Skip empty lines and TOML comments
            continue

        # 1. Check for Category Header (lines starting with #)
        if clean_line.startswith('#'):
            current_category = clean_line.lstrip('#').strip()
            continue

        # 2. Extract Ticker and Description
        try:
            # Ticker is the first token, followed by optional description
            parts = clean_line.split(maxsplit=1)
            ticker = parts[0].upper()
            description = parts[1] if len(parts) > 1 else ""

            # Regex to capture the content inside the parentheses: (CompanyName - Specialization)
            match = re.search(r'\((.*?)\)', description)
            if not match:
                continue

            content = match.group(1).strip()

            # 3. Extract Company Name and Specialization
            if ' - ' in content:
                company_name, specialization_details = content.rsplit(' - ', 1)
            else:
                company_name = content
                specialization_details = ""

            company_name = company_name.strip()
            specialization_details = specialization_details.strip()

            # 4. Compile Record
            record = {
                "ticker_symbol": ticker,
                "exchange_mic_code": default_exchange,  # Value from config.toml
                "classification_category": current_category,
                "company_name": company_name,
                "specialization_details": specialization_details,
                "thematic_focus": thematic_focus,  # Value from config.toml
                "is_listed": 1,
                "delisting_date": None
            }
            records.append(record)

        except Exception as e:
            print(f"An error occurred while parsing line: '{line.strip()}'. Error: {e}")
            continue

    return records


# --- Database Logic ---

def insert_records_idempotently(records: List[Dict[str, str]], db_config: Dict):
    """
    Inserts records into the stock_tickers table using INSERT ... ON DUPLICATE KEY UPDATE
    for idempotency.
    """

    sql = """
    INSERT INTO stock_tickers 
    (ticker_symbol, exchange_mic_code, classification_category, company_name, 
     specialization_details, thematic_focus, is_listed, delisting_date) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        classification_category = VALUES(classification_category),
        company_name = VALUES(company_name),
        specialization_details = VALUES(specialization_details),
        thematic_focus = VALUES(thematic_focus),
        is_listed = VALUES(is_listed),
        delisting_date = VALUES(delisting_date)
    """

    conn = None
    try:
        # 1. Establish Database Connection using credentials from the loaded config
        conn = mariadb.connect(**db_config)
        cursor = conn.cursor()

        print(f"Connected to MariaDB successfully. Inserting {len(records)} records...")

        # 2. Prepare Data for Insertion
        data_to_insert = [
            (
                record['ticker_symbol'],
                record['exchange_mic_code'],
                record['classification_category'],
                record['company_name'],
                record['specialization_details'],
                record['thematic_focus'],
                record['is_listed'],
                record['delisting_date']
            )
            for record in records
        ]

        # 3. Execute Insertion
        cursor.executemany(sql, data_to_insert)
        conn.commit()

        print(f"Successfully inserted/updated {cursor.rowcount} records.")

    except mariadb.Error as err:
        print(f"MariaDB Error: {err}")
        if conn:
            conn.rollback()

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    finally:
        # 4. Close Connection
        if conn and conn.is_connected():
            conn.close()
            print("Database connection closed.")


# --- Main Execution ---

if __name__ == "__main__":
    # 1. Setup Command Line Parser (standard Python package)
    parser = argparse.ArgumentParser(
        description="Idempotently load stock ticker data into MariaDB."
    )
    # Define the --config or -c option
    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config.toml',
        help="Path to the TOML configuration file (default: config.toml)"
    )
    args = parser.parse_args()

    # 2. Load Configuration
    try:
        config = load_config(args.config)

        # Validate essential configuration keys
        required_sections = ['database', 'static']
        if not all(section in config for section in required_sections):
            print("Configuration file missing required sections: [database] or [static].")
            sys.exit(1)

    except FileNotFoundError:
        print(f"Error: Configuration file '{args.config}' not found. Exiting.")
        sys.exit(1)
    except toml.TomlDecodeError as e:
        print(f"Error decoding TOML file '{args.config}': {e}. Check TOML syntax.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while loading config: {e}")
        sys.exit(1)

    # 3. Extract parameters from configuration
    db_config = config['database']
    static_config = config['static']

    tickers_file = static_config.get('tickers_file', 'tickers.txt')
    thematic_focus = static_config.get('default_thematic_focus', 'AI')
    default_exchange = static_config.get('default_exchange', 'XNAS')

    # 4. Parse Data
    stock_records = load_tickers_data(tickers_file, thematic_focus, default_exchange)
    if not stock_records:
        print("No stock records were successfully parsed. Exiting.")
    else:
        # 5. Insert Idempotently
        insert_records_idempotently(stock_records, db_config)
