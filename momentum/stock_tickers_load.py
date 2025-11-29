#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_tickers_load.py

================================================================================
PROJECT: Stock Market Data Loader (MariaDB)
AUTHOR: Matha Goram
DATE: 2025-11-28
VERSION: 2.3.0 (Fix: Corrected Sector/Sub-Sector name split from header line)
================================================================================

PURPOSE & METHODOLOGY:
----------------------
This script is responsible for parsing raw text files (e.g., 'tickers_xlb.txt')
containing categorized stock data and efficiently loading the information into
the 'stock_tickers' table in a MariaDB database.

It now implements enhanced parsing logic for header lines to:
1. Split the sub-sector header text (e.g., 'AI Infrastructure (Hardware, Chip)')
   at the first '(' character:
   - 'AI Infrastructure' goes into the 'sector_name' column (more specific sector).
   - 'Hardware, Chip' (content inside parentheses) goes into the 'sub_sector_name' column.
2. Separate the Company Name from the specialization details using the hyphen
   delimiter on ticker lines (e.g., 'Nvidia' from 'GPUs, Ecosystem').

It then performs a batch INSERT using `executemany` with `ON DUPLICATE KEY UPDATE`
to ensure data is either inserted or gracefully updated if the ticker already exists.

REQUIRED EXTERNAL FILES:
------------------------
1. config.toml: MUST contain valid credentials in the [database] section.
2. Ticker Files: Any text files listed in `INPUT_FILES` (e.g., 'tickers_xlb.txt').

================================================================================
MIT License

Copyright (c) 2025 ParkCircus Productions

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OROTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
================================================================================
"""
import mariadb
import toml
import re
import sys
from typing import List, Dict

# --- Configuration & Constants ---
CONFIG_FILE = 'config.toml'

# List of all ticker files to process
INPUT_FILES = [
    'tickers_ai.txt', 'tickers_xlb.txt', 'tickers_xlc.txt', 'tickers_xle.txt',
    'tickers_xlf.txt', 'tickers_xlp.txt', 'tickers_xlre.txt', 'tickers_xlu.txt',
    'tickers_xlv.txt', 'tickers_xly.txt', 'tickers_translog.txt'
]

# Regex Patterns
# Matches lines like: # Key Market Sector: MATERIALS (Used to set a top-level sector)
TOP_LEVEL_SECTOR_PATTERN = re.compile(r'#\s*Key Market Sector:\s*([^#\n]+)')
# Matches lines like: # 1. Chemicals & Industrial Gases (sub-sector header)
# Captures the ID (Group 1) and the full category string (Group 2)
SUB_SECTOR_HEADER_PATTERN = re.compile(r'^#\s*(\S+)\.\s*(.*)$')
# Matches lines like: # ETF Example: $XLB (Materials Select Sector SPDR Fund)
ETF_PATTERN = re.compile(r'#\s*ETF Example:\s*(\$[\w\.]+)')
# Matches lines like: NVDA (Nvidia - GPUs, Ecosystem)
TICKER_PATTERN = re.compile(r'^([A-Z]+(?:\.[A-Z])?)\s*\((.*?)\)$')


# --- Utility Functions ---

def load_config(config_file: str) -> Dict:
    """Loads and returns the database configuration from the TOML file."""
    try:
        with open(config_file, 'r') as f:
            config = toml.load(f)
        return config.get('database', {})
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_file}' not found. Exiting.")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config.toml: {e}")
        sys.exit(1)


# --- Core Logic ---

def parse_ticker_file(filename: str, default_exchange: str = 'XNAS') -> List[Dict[str, str]]:
    """
    Reads the tickers file and parses it into structured data records,
    extracting sector, sub-sector, ticker, company name, and description.
    """
    records = []
    # These now track the most recently seen header values
    current_market_sector_name = "UNCATEGORIZED"
    current_sector_etf = None
    current_sub_sector_id = "0"
    current_sub_sector_name = "MISCELLANEOUS"

    # This variable will hold the specific sector derived from the sub-sector header line
    # (e.g., 'AI Infrastructure' from '# 1. AI Infrastructure (Hardware, Chip)')
    # It will override the TOP_LEVEL_SECTOR_PATTERN value for the records that follow.
    current_specific_sector_name = "UNCATEGORIZED"

    try:
        with open(filename, 'r') as f:
            file_content = f.read()
    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        return []

    for line in file_content.strip().split('\n'):
        clean_line = line.strip()

        if not clean_line or clean_line.startswith('#'):
            # 1. Check for Top-Level Sector Header (e.g., # Key Market Sector: MATERIALS)
            sector_match = TOP_LEVEL_SECTOR_PATTERN.search(clean_line)
            if sector_match:
                current_market_sector_name = sector_match.group(1).strip()
                # Reset specific sector name to the top-level one until a sub-sector header is hit
                current_specific_sector_name = current_market_sector_name
                continue

            # 2. Check for ETF Header (e.g., # ETF Example: $XLB)
            etf_match = ETF_PATTERN.search(clean_line)
            if etf_match:
                current_sector_etf = etf_match.group(1).strip()
                continue

            # 3. Check for Sub-Sector Header (e.g., # 1. AI Infrastructure (Hardware, Chip, Data Center))
            sub_sector_match = SUB_SECTOR_HEADER_PATTERN.match(clean_line)
            if sub_sector_match:
                current_sub_sector_id = sub_sector_match.group(1).strip()
                full_sub_sector_string = sub_sector_match.group(2).strip()

                # Split the full sub-sector string based on the first '('
                if '(' in full_sub_sector_string:
                    # The string before the first '(' is the specific sector name
                    new_sector_name_part, sub_sector_name_part = full_sub_sector_string.split('(', 1)

                    # Set the new, more specific sector name
                    current_specific_sector_name = new_sector_name_part.strip()

                    # The content inside the parentheses is the sub-sector name
                    # rstrip(')') handles the closing parenthesis
                    current_sub_sector_name = sub_sector_name_part.rstrip(')').strip()

                    # Fallback check for empty sub-sector name if parentheses were empty
                    if not current_sub_sector_name:
                        current_sub_sector_name = "UNCATEGORIZED"

                else:
                    # Fallback: No parentheses found. The entire string is the specific sector name.
                    current_specific_sector_name = full_sub_sector_string
                    current_sub_sector_name = "UNCATEGORIZED"  # As requested

                continue

            # Skip any other comment lines
            continue

        # 4. Extract Ticker, Company Name, and Description
        ticker_match = TICKER_PATTERN.match(clean_line)
        if ticker_match:
            ticker_symbol = ticker_match.group(1).strip()
            # The full description is the text inside the outermost parentheses
            full_description_with_company = ticker_match.group(2).strip()

            # Split the full description into Company Name and Description using the first hyphen
            if '-' in full_description_with_company:
                # The split function will split on the FIRST hyphen only
                company_name_part, description_part = full_description_with_company.split('-', 1)

                # Company Name: string up to the first "-", with trailing spaces trimmed
                company_name = company_name_part.strip()

                # Description: the rest of the string, with leading/trailing spaces trimmed
                description = description_part.strip()
            else:
                # If no hyphen, the entire string is the company name, description is empty
                company_name = full_description_with_company.strip()
                description = ""

            # Record the data using the latest specific sector and sub-sector names
            record = {
                'ticker_symbol': ticker_symbol,
                'company_name': company_name,
                'description': description,
                'sector_name': current_specific_sector_name,  # Use the most specific sector name
                'sub_sector_id': current_sub_sector_id,
                'sub_sector_name': current_sub_sector_name,
                'exchange': default_exchange,
                'sector_etf_example': current_sector_etf,
                'source_file': filename
            }
            records.append(record)

    return records


def load_data_to_db(db_config: Dict, records: List[Dict[str, str]]) -> int:
    """Inserts or updates stock ticker records into the MariaDB database."""
    conn = None
    inserted_count = 0
    TICKERS_TABLE = 'stock_tickers'  # Hardcoded as it's not a function parameter

    # The order of columns in the parameter list is crucial for executemany
    columns = [
        'ticker_symbol', 'company_name', 'sector_name', 'sub_sector_id',
        'sub_sector_name', 'exchange', 'description',
        'sector_etf_example', 'source_file'
    ]

    # Prepare data for executemany: a list of tuples
    data_to_insert = [
        (
            r['ticker_symbol'], r['company_name'], r['sector_name'],
            r['sub_sector_id'], r['sub_sector_name'], r['exchange'],
            r['description'], r['sector_etf_example'], r['source_file']
        )
        for r in records
    ]

    try:
        # 1. Establish Connection
        conn = mariadb.connect(**db_config)
        cursor = conn.cursor()

        # 2. Construct INSERT statement with ON DUPLICATE KEY UPDATE
        insert_query = f"""
            INSERT INTO {TICKERS_TABLE} ({', '.join(columns)})
            VALUES ({', '.join(['%s'] * len(columns))})
            ON DUPLICATE KEY UPDATE 
                company_name=VALUES(company_name), 
                sector_name=VALUES(sector_name), 
                sub_sector_id=VALUES(sub_sector_id), 
                sub_sector_name=VALUES(sub_sector_name), 
                exchange=VALUES(exchange), 
                description=VALUES(description),
                sector_etf_example=VALUES(sector_etf_example),
                source_file=VALUES(source_file); 
        """

        cursor.executemany(insert_query, data_to_insert)
        inserted_count = cursor.rowcount

        conn.commit()

    except mariadb.Error as e:
        print(f"❌ MariaDB Error during data load: {e}")
        print("   -> Ensure the 'stock_tickers' table schema includes the new 'company_name' column.")

    finally:
        if conn is not None:
            try:
                # Only close if the connection was successfully established
                if hasattr(conn, 'close'):
                    conn.close()
            except Exception:
                pass

    return inserted_count


if __name__ == "__main__":
    db_config = load_config(CONFIG_FILE)

    total_records = 0
    total_affected_rows = 0

    print("==================================================")
    for file_name in INPUT_FILES:
        print(f"▶️ Processing file: {file_name}")

        records = parse_ticker_file(file_name, default_exchange='XNAS')
        total_records += len(records)

        if records:
            affected_rows = load_data_to_db(db_config, records)
            total_affected_rows += affected_rows
            print(f"   -> Parsed {len(records)} records. Inserted/Updated {affected_rows} rows.")
        else:
            print("   -> No valid ticker records found in file.")

    print("==================================================")
    print(f"Summary: Total records parsed: {total_records}")
    print(f"Summary: Total rows affected (Inserted/Updated): {total_affected_rows}")
    print("==================================================")