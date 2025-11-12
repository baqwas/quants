# User Manual: Interactive Payoff Strategy Builder 

This document provides a guide on how to use the payoff_analysis.py script, an interactive tool for building and visualizing financial strategies. 
## Overview

The Interactive Payoff Strategy Builder is a graphical user interface (GUI) application that allows you to:

-    Build a custom financial strategy using various instruments (long/short calls, long/short puts, long/short stock). 
-    Dynamically fetch live stock prices from YFinance. 
-    Visualize the payoff diagram for your strategy. 
-    View a summary of your strategy, including total cost, maximum profit, and maximum loss. 

## Prerequisites

Before running the application, you must have Python installed. The script also requires two external libraries: `yfinance` and `matplotlib`. 

To install the necessary libraries, open your terminal or command prompt and run the following command:
``` 
pip install yfinance matplotlib
``` 
The `tkinter` library is a standard part of Python installations, so no additional setup is required for the GUI. 
## How to Run the Application 
- Save the provided code into a file named payoff_analysis.py. 
- Open your terminal or command prompt. 
- Navigate to the directory where you saved the file. 
- Run the script using the following command: 
``` 
    python payoff_analysis.py
``` 
A new window titled "Interactive Payoff Strategy Builder" will appear. 
## The Graphical User Interface (GUI)

The GUI is divided into two main sections: 

-    Input Controls (Left Side): This is where you will define your strategy and its plotting parameters. 

-    Strategy Summary (Right Side): This section provides a real-time overview of your current strategy. 

### 1. Building Your Strategy 
#### Strategy Name 
- `Strategy Name`: Enter a descriptive name for your strategy. This name will be used as the title of the generated payoff chart.

#### Add Instrument 

This section is for adding individual components (options or stocks) to your strategy.

    Strike/Entry Price: Enter the strike price for an option or the entry price for a stock position.

    Premium: Enter the premium paid or received for an option. This field should be left at 0 for stock positions.

    Quantity (Contracts/Shares): Enter the number of contracts (for options) or shares (for stocks).

    Click one of the six buttons to add the instrument to your strategy:

        Long Call

        Short Call

        Long Put

        Short Put

        Long Stock

        Short Stock

Each time you add an instrument, the "Strategy Summary" on the right will update automatically.
2. Plotting the Payoff Diagram
Plot Settings

This section is for configuring the parameters for your payoff diagram.

    Ticker Symbol: Enter the stock ticker (e.g., AAPL, MSFT, SPY).

    Get Live Price: Click this button to automatically fetch the current price for the entered ticker from YFinance. This will populate the "Current Stock Price" field.

    Current Stock Price: This field displays the live price after clicking "Get Live Price." You can also manually enter a price. This value is used to mark the current position on the payoff chart.

    Price Range (Min): The minimum stock price to be displayed on the x-axis of the chart.

    Price Range (Max): The maximum stock price to be displayed on the x-axis of the chart.

    Generate Payoff Chart: Click this button to create and display the payoff diagram in a new window.

3. Strategy Summary

This section, located on the right side of the GUI, updates in real-time as you add instruments.

    Strategy Summary: A text box listing all the instruments in your strategy, including their type, strike price, premium, and quantity.

    Total Cost: The total cost of entering the strategy. A negative value indicates a net credit.

    Max Profit: The maximum possible profit for the strategy. This may be "Unlimited" for certain strategies.

    Max Loss: The maximum possible loss for the strategy. This may be "Unlimited" for certain strategies.

Troubleshooting

    "YFinance Error": This error typically occurs if the ticker symbol you entered is invalid or if there is an issue with your internet connection.

    "Invalid Input": This error appears if you enter non-numeric characters into the input fields for price, premium, or quantity. Ensure all fields contain valid numbers.

    No Plot Appears: If you click "Generate Payoff Chart" and no plot window appears, check your terminal for any error messages. This might happen if the plotting parameters (e.g., Min and Max Price) are not valid numbers.

"Could not save/load strategy. Error:...": This error may appear if there are permission issues with the directory you are trying to save to, or if the file you are trying to load is not a valid JSON file.


If you encounter any issues, try restarting the application and verifying all your inputs.