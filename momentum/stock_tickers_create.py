#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_tickers_create.py

================================================================================
PROJECT: Stock Market Data Loader (MariaDB)
AUTHOR: [Your Name/Company Name]
DATE: 2025-11-28
VERSION: 2.3.0 (Fix: Added company_name field, refined sub_sector_name DDL)
================================================================================

PURPOSE & METHODOLOGY:
----------------------
This script connects to a MariaDB database and defines the Data Definition
Language (DDL) for the application's two primary tables: 'stock_tickers'
(for company fundamentals/categorization) and 'stock_signals'.

The 'stock_tickers' schema has been updated to include a dedicated 'company_name'
column, extracted from the ticker files' description string, separating it from
the remaining 'description' (specialization) data.

REQUIRED EXTERNAL FILES:
------------------------
1. config.toml: MUST contain valid credentials in the [database] section.

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
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
================================================================================
"""

import argparse
import mariadb
import toml
import sys
from typing import Dict

# --- Configuration Constants ---
CONFIG_FILE = 'config.toml'
TICKERS_TABLE = 'stock_tickers'
SIGNALS_TABLE = 'stock_signals'


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


def create_tables(db_config: Dict):
    """
    Connects to MariaDB and ensures the existence of the required tables,
    applying the full schema including new company_name field.
    """
    conn = None
    try:
        # 1. Establish Connection
        conn = mariadb.connect(**db_config)
        cursor = conn.cursor()

        # 2. DDL for stock_tickers (REVISED)
        tickers_ddl = f"""
        CREATE TABLE {TICKERS_TABLE} (
            -- Primary Key
            ticker_id INT UNSIGNED NOT NULL AUTO_INCREMENT,

            -- External Unique Identifier
            ticker_symbol VARCHAR(10) NOT NULL UNIQUE,

            -- Company Information (NEW FIELD)
            company_name VARCHAR(100) NOT NULL 
                COMMENT 'The primary company name (before the first hyphen)',

            -- Sector Classification Data
            sector_name VARCHAR(255) NOT NULL 
                COMMENT 'The main sector (e.g., FINANCIALS, HEALTH CARE)',
            sector_etf_example VARCHAR(50) 
                COMMENT 'ETF proxy for the sector (e.g., $XLF)',
            sub_sector_id VARCHAR(10) NOT NULL DEFAULT '0' 
                COMMENT 'Numerical or Roman ID for the sub-sector',
            sub_sector_name VARCHAR(255) NOT NULL 
                COMMENT 'The specific sub-sector (e.g., Banks, Biotechnology)',

            -- Ticker Metadata
            exchange VARCHAR(10) NOT NULL DEFAULT 'XNAS'
                COMMENT 'Market Identifier Code (e.g., XNYS, XNAS)',
            description VARCHAR(255)
                COMMENT 'Specialization details and brief description (after the first hyphen)',
            source_file VARCHAR(255) NOT NULL
                COMMENT 'Original file the record was loaded from',

            -- Status & Lifecycle Data
            is_listed TINYINT(1) NOT NULL DEFAULT 1
                COMMENT '1=Listed/Active, 0=Delisted/Inactive',
            delisting_date DATE NULL
                COMMENT 'Date the stock was delisted or last traded',

            PRIMARY KEY (ticker_id),
            UNIQUE INDEX ux_ticker_exchange (ticker_symbol, exchange)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """

        # 3. DDL for stock_signals (Kept for completeness)
        signals_ddl = f"""
        CREATE TABLE {SIGNALS_TABLE} (
            signal_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            ticker_symbol VARCHAR(10) NOT NULL,
            signal_date DATE NOT NULL,
            signal_type VARCHAR(50) NOT NULL,
            description VARCHAR(255),
            price_at_signal DECIMAL(18, 4),
            macd_value DECIMAL(18, 6),
            signal_value DECIMAL(18, 6),
            rsi_value DECIMAL(18, 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (signal_id),
            UNIQUE KEY ux_ticker_date_type (ticker_symbol, signal_date, signal_type), 

            FOREIGN KEY (ticker_symbol) REFERENCES {TICKERS_TABLE}(ticker_symbol)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """

        # Drop tables first to apply schema changes cleanly (if they exist)
        cursor.execute(f"DROP TABLE IF EXISTS {SIGNALS_TABLE};")
        cursor.execute(f"DROP TABLE IF EXISTS {TICKERS_TABLE};")
        print("Dropped existing tables (if present) to apply new schema.")

        cursor.execute(tickers_ddl)
        print(f"✅ Successfully created table: '{TICKERS_TABLE}'.")

        cursor.execute(signals_ddl)
        print(f"✅ Successfully created table: '{SIGNALS_TABLE}'.")

        conn.commit()

    except mariadb.Error as e:
        print(f"❌ MariaDB Error: {e}")
        print("Please ensure your MariaDB server is running and credentials/database exist.")

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Creates the core database tables for the stock tracking application.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-c', '--config',
        default=CONFIG_FILE,
        help="Path to the TOML configuration file (default: config.toml)"
    )
    args = parser.parse_args()

    db_config = load_config(args.config)
    create_tables(db_config)
