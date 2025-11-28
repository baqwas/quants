CREATE TABLE stock_signals (
    -- Unique internal identifier
    signal_id INT UNSIGNED NOT NULL AUTO_INCREMENT,

    -- Stock ticker that generated the signal
    ticker_symbol VARCHAR(10) NOT NULL,

    -- The date the crossover event occurred (Used for idempotency)
    signal_date DATE NOT NULL,

    -- Type of signal (e.g., 'MACD BULLISH', 'MACD BEARISH')
    signal_type VARCHAR(50) NOT NULL,

    -- Detailed description of the event
    description VARCHAR(255),

    -- Stock's closing price on the signal date
    price_at_signal DECIMAL(18, 4),

    -- Key indicator values for analysis
    macd_value DECIMAL(18, 6),
    signal_value DECIMAL(18, 6),
    rsi_value DECIMAL(18, 4),

    -- Timestamp of when the record was inserted
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (signal_id),

    -- UNIQUE KEY constraint ensures only ONE entry per stock per day for a signal
    UNIQUE KEY ux_ticker_date (ticker_symbol, signal_date)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COMMENT='MACD Crossover Signals for Monitored Stocks';