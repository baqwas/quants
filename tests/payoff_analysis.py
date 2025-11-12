#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yfinance as yf
import json


# --- PayoffStrategy Class (Core Logic) ---
class PayoffStrategy:
    """
    A class to create and analyze custom financial strategies by combining
    different instruments like options and stocks.
    """

    def __init__(self, name="Custom Strategy"):
        self.name = name
        self.instruments = []
        self.total_cost = 0.0

    def add_long_call(self, strike_price, premium, quantity=1):
        self.instruments.append({
            'type': 'long_call',
            'strike': strike_price,
            'premium': premium,
            'quantity': quantity
        })
        self.total_cost += premium * quantity * 100

    def add_short_call(self, strike_price, premium, quantity=1):
        self.instruments.append({
            'type': 'short_call',
            'strike': strike_price,
            'premium': premium,
            'quantity': quantity
        })
        self.total_cost -= premium * quantity * 100

    def add_long_put(self, strike_price, premium, quantity=1):
        self.instruments.append({
            'type': 'long_put',
            'strike': strike_price,
            'premium': premium,
            'quantity': quantity
        })
        self.total_cost += premium * quantity * 100

    def add_short_put(self, strike_price, premium, quantity=1):
        self.instruments.append({
            'type': 'short_put',
            'strike': strike_price,
            'premium': premium,
            'quantity': quantity
        })
        self.total_cost -= premium * quantity * 100

    def add_long_stock(self, entry_price, quantity=100):
        self.instruments.append({
            'type': 'long_stock',
            'entry_price': entry_price,
            'quantity': quantity
        })
        self.total_cost += entry_price * quantity

    def add_short_stock(self, entry_price, quantity=100):
        self.instruments.append({
            'type': 'short_stock',
            'entry_price': entry_price,
            'quantity': quantity
        })
        self.total_cost -= entry_price * quantity

    def calculate_payoff(self, stock_prices):
        total_payoff = np.zeros_like(stock_prices)
        for instr in self.instruments:
            qty = instr['quantity']
            if 'call' in instr['type']:
                payoff = np.maximum(stock_prices - instr['strike'], 0) - instr['premium']
                if 'short' in instr['type']:
                    payoff *= -1
                total_payoff += payoff * qty * 100
            elif 'put' in instr['type']:
                payoff = np.maximum(instr['strike'] - stock_prices, 0) - instr['premium']
                if 'short' in instr['type']:
                    payoff *= -1
                total_payoff += payoff * qty * 100
            elif 'stock' in instr['type']:
                payoff = stock_prices - instr['entry_price']
                if 'short' in instr['type']:
                    payoff *= -1
                total_payoff += payoff * qty
        return total_payoff

    def get_max_profit(self):
        # A more robust calculation would involve finding critical points, but for this simplified
        # version, we will check for unlimited potential and then find the max on a large range.
        for instr in self.instruments:
            if instr['type'] == 'long_call' or instr['type'] == 'long_stock':
                short_call_strikes = [i['strike'] for i in self.instruments if i['type'] == 'short_call']
                if not short_call_strikes or instr['strike'] > max(short_call_strikes):
                    return "Unlimited"
        stock_prices = np.linspace(0, 500, 1000)
        payoff = self.calculate_payoff(stock_prices)
        max_payoff = np.max(payoff)
        return f"${max_payoff:.2f}"

    def get_max_loss(self):
        for instr in self.instruments:
            if instr['type'] == 'short_call' or instr['type'] == 'short_stock':
                return "Unlimited"
        stock_prices = np.linspace(0, 500, 1000)
        payoff = self.calculate_payoff(stock_prices)
        min_payoff = np.min(payoff)
        return f"${min_payoff:.2f}"

    def get_live_stock_price(self, ticker):
        """Fetches the current live stock price using yfinance."""
        try:
            stock = yf.Ticker(ticker)
            price = stock.info['currentPrice']
            return price
        except Exception as e:
            messagebox.showerror("YFinance Error", f"Could not fetch data for ticker '{ticker}'. Error: {e}")
            return None

    def plot_payoff(self, stock_prices_range, current_stock_price, ticker=""):
        stock_prices = np.linspace(stock_prices_range[0], stock_prices_range[1], 400)
        payoff = self.calculate_payoff(stock_prices)

        plt.style.use('fivethirtyeight')
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(stock_prices, payoff, label=self.name, color='dodgerblue', linewidth=2)
        ax.axhline(0, color='black', linestyle='--', linewidth=1)

        breakevens = stock_prices[np.isclose(payoff, 0)]
        if len(breakevens) > 0:
            ax.plot(breakevens, np.zeros_like(breakevens), 'go', markersize=8, label='Break-Even Point(s)')
            for be_point in breakevens:
                ax.annotate(f'${be_point:.2f}', (be_point, 0), textcoords="offset points", xytext=(0, 10), ha='center',
                            color='green')

        ax.axvline(current_stock_price, color='purple', linestyle=':',
                   label=f'Current Price (${current_stock_price:.2f})', linewidth=1)

        plot_title = f'Payoff Diagram for {self.name}'
        if ticker:
            plot_title += f' ({ticker.upper()})'

        ax.set_title(plot_title, fontsize=16, fontweight='bold')
        ax.set_xlabel('Stock Price at Expiration', fontsize=12)
        ax.set_ylabel('Profit/Loss ($)', fontsize=12)
        ax.grid(True)
        ax.legend()
        plt.tight_layout()
        plt.show()


# --- GUI Application Class ---
class PayoffApp:
    def __init__(self, master):
        self.master = master
        master.title("Interactive Payoff Strategy Builder")

        self.strategy = PayoffStrategy()

        self.create_widgets()
        self.update_summary()

    def create_widgets(self):
        # Main frames
        self.input_frame = ttk.Frame(self.master, padding="10")
        self.input_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.summary_frame = ttk.Frame(self.master, padding="10", relief=tk.GROOVE, borderwidth=2)
        self.summary_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Strategy Name
        ttk.Label(self.input_frame, text="Strategy Name:").pack(pady=(0, 5), anchor='w')
        self.strategy_name_entry = ttk.Entry(self.input_frame)
        self.strategy_name_entry.insert(0, "My Custom Strategy")
        self.strategy_name_entry.pack(fill=tk.X, pady=(0, 10))

        # --- Option/Stock Input Frame ---
        option_frame = ttk.LabelFrame(self.input_frame, text="Add Instrument", padding="10")
        option_frame.pack(fill=tk.X, pady=10)

        # Labels and Entry fields for common inputs
        ttk.Label(option_frame, text="Strike/Entry Price:").grid(row=0, column=0, sticky='w', pady=2)
        self.strike_entry = ttk.Entry(option_frame)
        self.strike_entry.grid(row=0, column=1, sticky='ew', padx=5, pady=2)

        ttk.Label(option_frame, text="Premium:").grid(row=1, column=0, sticky='w', pady=2)
        self.premium_entry = ttk.Entry(option_frame)
        self.premium_entry.grid(row=1, column=1, sticky='ew', padx=5, pady=2)

        ttk.Label(option_frame, text="Quantity (Contracts/Shares):").grid(row=2, column=0, sticky='w', pady=2)
        self.quantity_entry = ttk.Entry(option_frame)
        self.quantity_entry.insert(0, "1")
        self.quantity_entry.grid(row=2, column=1, sticky='ew', padx=5, pady=2)

        # Buttons to add instruments
        button_frame = ttk.Frame(option_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="Long Call", command=lambda: self.add_instrument('long_call')).pack(side=tk.LEFT,
                                                                                                          padx=2)
        ttk.Button(button_frame, text="Short Call", command=lambda: self.add_instrument('short_call')).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Long Put", command=lambda: self.add_instrument('long_put')).pack(side=tk.LEFT,
                                                                                                        padx=2)
        ttk.Button(button_frame, text="Short Put", command=lambda: self.add_instrument('short_put')).pack(side=tk.LEFT,
                                                                                                          padx=2)
        ttk.Button(button_frame, text="Long Stock", command=lambda: self.add_instrument('long_stock')).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Short Stock", command=lambda: self.add_instrument('short_stock')).pack(
            side=tk.LEFT, padx=2)

        # --- Plotting Frame ---
        plot_frame = ttk.LabelFrame(self.input_frame, text="Plot Settings", padding="10")
        plot_frame.pack(fill=tk.X, pady=10)

        # New Ticker input and live price button
        ttk.Label(plot_frame, text="Ticker Symbol:").grid(row=0, column=0, sticky='w', pady=2)
        self.ticker_entry = ttk.Entry(plot_frame)
        self.ticker_entry.grid(row=0, column=1, sticky='ew', padx=5, pady=2)
        ttk.Button(plot_frame, text="Get Live Price", command=self.get_live_price_action).grid(row=0, column=2, padx=5)

        ttk.Label(plot_frame, text="Current Stock Price:").grid(row=1, column=0, sticky='w', pady=2)
        self.current_price_entry = ttk.Entry(plot_frame)
        self.current_price_entry.grid(row=1, column=1, sticky='ew', padx=5, pady=2)

        ttk.Label(plot_frame, text="Price Range (Min):").grid(row=2, column=0, sticky='w', pady=2)
        self.min_price_entry = ttk.Entry(plot_frame)
        self.min_price_entry.grid(row=2, column=1, sticky='ew', padx=5, pady=2)

        ttk.Label(plot_frame, text="Price Range (Max):").grid(row=3, column=0, sticky='w', pady=2)
        self.max_price_entry = ttk.Entry(plot_frame)
        self.max_price_entry.grid(row=3, column=1, sticky='ew', padx=5, pady=2)

        self.plot_button = ttk.Button(plot_frame, text="Generate Payoff Chart", command=self.plot_strategy_action)
        self.plot_button.grid(row=4, column=0, columnspan=3, pady=10)

        # --- Save/Load Frame ---
        save_load_frame = ttk.Frame(self.input_frame, padding="10")
        save_load_frame.pack(fill=tk.X, pady=10)
        ttk.Button(save_load_frame, text="Save Strategy", command=self.save_strategy_action).pack(side=tk.LEFT, padx=5,
                                                                                                  expand=True,
                                                                                                  fill=tk.X)
        ttk.Button(save_load_frame, text="Load Strategy", command=self.load_strategy_action).pack(side=tk.LEFT, padx=5,
                                                                                                  expand=True,
                                                                                                  fill=tk.X)

        # --- Summary Frame ---
        self.summary_label = ttk.Label(self.summary_frame, text="Strategy Summary", font=("Helvetica", 14, "bold"))
        self.summary_label.pack(pady=(0, 10), anchor='w')

        self.summary_text = tk.Text(self.summary_frame, height=15, width=40)
        self.summary_text.pack(fill=tk.BOTH, expand=True)

        self.cost_label = ttk.Label(self.summary_frame, text="Total Cost: $0.00", font=("Helvetica", 12, "bold"))
        self.cost_label.pack(pady=(10, 5), anchor='w')

        self.profit_label = ttk.Label(self.summary_frame, text="Max Profit: N/A", font=("Helvetica", 12, "bold"))
        self.profit_label.pack(pady=5, anchor='w')

        self.loss_label = ttk.Label(self.summary_frame, text="Max Loss: N/A", font=("Helvetica", 12, "bold"))
        self.loss_label.pack(pady=5, anchor='w')

    def save_strategy_action(self):
        """Saves the current strategy to a JSON file."""
        file_path = filedialog.asksaveasfilename(defaultextension=".json",
                                                 filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not file_path:
            return  # User canceled the dialog

        data_to_save = {
            'name': self.strategy.name,
            'instruments': self.strategy.instruments
        }

        try:
            with open(file_path, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            messagebox.showinfo("Success", f"Strategy saved to {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save strategy. Error: {e}")

    def load_strategy_action(self):
        """Loads a strategy from a JSON file."""
        file_path = filedialog.askopenfilename(defaultextension=".json",
                                               filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not file_path:
            return  # User canceled the dialog

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Clear current strategy and load new one
            self.strategy = PayoffStrategy(name=data['name'])
            self.strategy.instruments = data['instruments']

            # Recalculate total cost
            self.strategy.total_cost = 0.0
            for instr in self.strategy.instruments:
                if 'call' in instr['type'] or 'put' in instr['type']:
                    premium = instr['premium'] if 'long' in instr['type'] else -instr['premium']
                    self.strategy.total_cost += premium * instr['quantity'] * 100
                elif 'stock' in instr['type']:
                    entry_price = instr['entry_price'] if 'long' in instr['type'] else -instr['entry_price']
                    self.strategy.total_cost += entry_price * instr['quantity']

            # Update GUI fields
            self.strategy_name_entry.delete(0, tk.END)
            self.strategy_name_entry.insert(0, self.strategy.name)
            self.update_summary()

            messagebox.showinfo("Success", f"Strategy loaded from {file_path}")

        except Exception as e:
            messagebox.showerror("Error", f"Could not load strategy. Error: {e}")
            self.strategy = PayoffStrategy()  # Reset to a clean state

    def add_instrument(self, type):
        try:
            strike_price = float(self.strike_entry.get())
            premium = float(self.premium_entry.get()) if 'stock' not in type else 0.0
            quantity = int(self.quantity_entry.get())

            if type == 'long_call':
                self.strategy.add_long_call(strike_price, premium, quantity)
            elif type == 'short_call':
                self.strategy.add_short_call(strike_price, premium, quantity)
            elif type == 'long_put':
                self.strategy.add_long_put(strike_price, premium, quantity)
            elif type == 'short_put':
                self.strategy.add_short_put(strike_price, premium, quantity)
            elif type == 'long_stock':
                self.strategy.add_long_stock(strike_price, quantity)
            elif type == 'short_stock':
                self.strategy.add_short_stock(strike_price, quantity)

            self.update_summary()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers for Strike/Price, Premium, and Quantity.")

    def get_live_price_action(self):
        ticker = self.ticker_entry.get().strip().upper()
        if ticker:
            price = self.strategy.get_live_stock_price(ticker)
            if price:
                self.current_price_entry.delete(0, tk.END)
                self.current_price_entry.insert(0, str(price))

    def plot_strategy_action(self):
        try:
            current_price = float(self.current_price_entry.get())
            min_price = float(self.min_price_entry.get())
            max_price = float(self.max_price_entry.get())
            ticker = self.ticker_entry.get().strip().upper()

            self.strategy.name = self.strategy_name_entry.get()
            self.strategy.plot_payoff((min_price, max_price), current_price, ticker)
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers for plotting parameters.")

    def update_summary(self):
        self.summary_text.delete(1.0, tk.END)
        for instr in self.strategy.instruments:
            if 'call' in instr['type'] or 'put' in instr['type']:
                self.summary_text.insert(tk.END,
                                         f"{instr['quantity']}x {instr['type'].replace('_', ' ').title()} @ Strike ${instr['strike']:.2f} (Premium: ${instr['premium']:.2f})\n")
            elif 'stock' in instr['type']:
                self.summary_text.insert(tk.END,
                                         f"{instr['quantity']}x {instr['type'].replace('_', ' ').title()} @ Entry ${instr['entry_price']:.2f}\n")

        self.cost_label.config(text=f"Total Cost: ${self.strategy.total_cost:.2f}")
        self.profit_label.config(text=f"Max Profit: {self.strategy.get_max_profit()}")
        self.loss_label.config(text=f"Max Loss: {self.strategy.get_max_loss()}")


if __name__ == "__main__":
    root = tk.Tk()
    app = PayoffApp(root)
    root.mainloop()

