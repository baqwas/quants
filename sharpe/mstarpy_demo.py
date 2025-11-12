#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script calculates the annualized Sharpe ratio for mutual funds using the mstarpy library.
"""
import pandas as pd
import numpy as np
import mstarpy
from datetime import date, timedelta


def calculate_sharpe_ratio(security_id, country_code='us', start_date=None, end_date=None, risk_free_rate=0.03):
    """
    Calculates the annualized Sharpe ratio for a mutual fund using mstarpy.

    Args:
        security_id (str): The unique Morningstar ID (SecId) for the fund.
        Country_code (str): The country code for the fund's market.
        Start_date (datetime.date): The start date for the data.
        End_date (datetime.date): The end date for the data.
        Risk_free_rate (float): The annualized risk-free rate of return (e.g., 0.03 for 3%).

    Returns:
        tuple: A tuple containing the fund name and the annualized Sharpe ratio,
               or None if data is unavailable.
    """
    if start_date is None:
        end_date = date.today()
        start_date = end_date - timedelta(days=5 * 365)

    try:
        # Initialize the Funds object with the Morningstar security ID
        fund = mstarpy.Funds(term=security_id)

        # Get historical NAV data
        nav_history = fund.nav(start_date=start_date, end_date=end_date, frequency="daily")

        # Check if historical data was returned
        if not nav_history:
            print(f"Warning: No historical data found for ID {security_id}. Skipping.")
            return None

        # Convert the historical data to a DataFrame
        data = pd.DataFrame(nav_history)
        data['date'] = pd.to_datetime(data['date'])
        data.set_index('date', inplace=True)
        data = data.sort_index()

        # Check for sufficient data
        if data.empty or 'nav' not in data.columns:
            print(f"Warning: Insufficient data or 'nav' column not found for ID {security_id}. Skipping.")
            return None

        # Calculate daily returns
        returns = data['nav'].pct_change().dropna()

        # Annualization factor (252 trading days per year)
        annualization_factor = 252

        # Calculate mean daily return
        mean_return = returns.mean()

        # Calculate daily standard deviation (volatility)
        std_dev = returns.std()

        # Annualize the mean return and standard deviation
        annualized_mean_return = mean_return * annualization_factor
        annualized_std_dev = std_dev * np.sqrt(annualization_factor)

        # Calculate the Sharpe ratio
        sharpe_ratio = (annualized_mean_return - risk_free_rate) / annualized_std_dev

        return fund.name, sharpe_ratio

    except Exception as e:
        print(f"An error occurred for security ID {security_id}: {e}")
        return None, None


def main():
    """
    Main function to read security IDs from a file and calculate their Sharpe ratios.
    """
    # Define the time period for analysis (e.g., last 5 years)
    end_date = date.today()
    start_date = end_date - timedelta(days=5 * 365)

    # Define an assumed risk-free rate (e.g., 3%)
    risk_free_rate = 0.03

    # List to store the results
    results = []

    try:
        with open('../tickers/morningstar_funds.txt', 'r') as file:
            security_ids = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        print("Error: 'morningstar_funds.txt' not found. Please create the file with Morningstar security IDs.")
        return

    print(f"Calculating Sharpe Ratios for {len(security_ids)} funds over the last 5 years...")
    print("-" * 50)

    for security_id in security_ids:
        fund_name, sharpe_ratio = calculate_sharpe_ratio(security_id, start_date=start_date, end_date=end_date,
                                                         risk_free_rate=risk_free_rate)
        if sharpe_ratio is not None:
            results.append({'Fund Name': fund_name, 'Sharpe Ratio': sharpe_ratio})

    # Convert results to a DataFrame for clean formatting
    if results:
        results_df = pd.DataFrame(results).round(4)
        results_df = results_df.sort_values(by='Sharpe Ratio', ascending=False)

        print("\nSharpe Ratio Results (Sorted by Highest):")
        print(results_df)
    else:
        print("No valid Sharpe ratios were calculated.")


if __name__ == "__main__":
    main()