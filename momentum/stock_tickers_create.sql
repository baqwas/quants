CREATE TABLE stock_tickers (
    -- Internal Unique Identifier (User Request)
    ticker_id INT UNSIGNED NOT NULL AUTO_INCREMENT,

    -- External Unique Identifier (User Request)
    ticker_symbol VARCHAR(10) NOT NULL UNIQUE,

    -- New Column: The Stock Exchange (Highly Recommended)
    exchange_mic_code VARCHAR(10) NOT NULL DEFAULT 'XNYS'
        COMMENT 'Market Identifier Code (e.g., XNYS, XNAS, XTSE)',

    -- Classification Category (From tickers.txt)
    classification_category VARCHAR(255) NOT NULL,

    -- Company Name (Parsed from parenthesis)
    company_name VARCHAR(100) NOT NULL,

    -- Specialization Details (Parsed after the hyphen)
    specialization_details VARCHAR(255),

    -- Thematic Focus (User Request: 'AI' by default)
    thematic_focus VARCHAR(50) NOT NULL DEFAULT 'AI',

    -- New Column: Boolean Status (User Request)
    is_listed TINYINT(1) NOT NULL DEFAULT 1
        COMMENT '1=Listed/Active, 0=Delisted/Inactive',

    -- New Column: Delisting Date (User Request)
    delisting_date DATE NULL
        COMMENT 'Date the stock was delisted or last traded',

    -- Primary Key Definition
    PRIMARY KEY (ticker_id),

    -- Combined Unique Index for Ticker and Exchange (Best Practice)
    UNIQUE INDEX ux_ticker_exchange (ticker_symbol, exchange_mic_code)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COMMENT='AI/Quantum Tech Stock Tickers with Status and Exchange Info';