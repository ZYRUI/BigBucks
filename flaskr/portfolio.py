import pandas as pd
import numpy as np
from pandas_datareader import data as pdr
import yfinance as yf
from scipy.optimize import minimize
import matplotlib.pyplot as plt
from datetime import datetime, timedelta


def eff(symbol_ls):
    # Set start and end dates for historical price data
    start_date = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')

    # Define list of symbols and corresponding shares
    #symbol_ls = ['AAPL', 'GOOG', 'AMZN']
    #share_ls = [100, 50, 75]

    # Download historical price data
    yf.pdr_override()
    data = pd.DataFrame()
    for symbol in symbol_ls:
        df = pdr.get_data_yahoo(symbol, start=start_date, end=end_date)['Adj Close'].rename(symbol)
        data = pd.concat([data, df], axis=1)

    # Calculate daily returns
    returns = data.pct_change().dropna()

    # Calculate expected returns and covariance matrix
    mu = returns.mean()
    Sigma = returns.cov()

    # Set number of simulations
    num_ports = 1000

    # Generate random portfolio weights
    weights = np.random.dirichlet(np.ones(len(symbol_ls)), size=num_ports)

    # Calculate portfolio expected returns and volatilities
    port_returns = np.dot(weights, mu)
    port_volatilities = []
    for w in weights:
        port_volatilities.append(np.sqrt(np.dot(w.T, np.dot(Sigma, w))))

    def portfolio_volatility(w):
        return np.sqrt(np.dot(w.T, np.dot(Sigma, w)))

    def portfolio_return(w):
        return np.dot(w.T, mu)

    cons = ({'type': 'eq', 'fun': lambda w: sum(w) - 1})

    frontier_returns = np.linspace(min(port_returns), max(port_returns), num_ports)
    frontier_volatilities = []
    for r in frontier_returns:
        guess = [1.0 / len(symbol_ls)] * len(symbol_ls)
        bounds = tuple((0,1) for i in range(len(symbol_ls)))
        cons = ({'type': 'eq', 'fun': lambda w: portfolio_return(w) - r}, {'type': 'eq', 'fun': lambda w: sum(w) - 1})
        result = minimize(portfolio_volatility, guess, method='SLSQP', bounds=bounds, constraints=cons)
        if not result.success:
            continue
        frontier_volatilities.append(result.fun)

    annualized_frontier_returns = (frontier_returns)*252
    annualized_frontier_volatilities = np.array(frontier_volatilities) * np.sqrt(252)

    return annualized_frontier_returns, annualized_frontier_volatilities

def sharp_ratio(symbol_ls, share_ls):
    start_date = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')

    data = yf.download(symbol_ls, start=start_date, end=end_date)['Adj Close']
    returns = data.pct_change()
    portfolio_returns = (returns * share_ls).sum(axis=1)

    #US Treasury 10 year bond yield
    risk_free_rate = 0.013
    excess_returns = portfolio_returns - risk_free_rate

    sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std()

    return sharpe_ratio


def current_eff(symbols, shares):
    # get historical data for each symbol
    df_list = []
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period='5y')['Close']
        df_list.append(df)

    # merge the historical data for each symbol into a single dataframe
    df = pd.concat(df_list, axis=1)
    df.columns = symbols

    # calculate the daily returns for each stock in the dataframe
    daily_returns = df.pct_change()

    # calculate the weighted average daily return for the portfolio
    portfolio_return = (daily_returns.mean() * shares).sum() / sum(shares)

    # calculate the covariance matrix of the daily returns
    cov_matrix = daily_returns.cov()

    # calculate the portfolio volatility using the weighted average daily return and the covariance matrix
    portfolio_volatility = np.sqrt(np.dot(shares, np.dot(cov_matrix, shares))) / sum(shares)

    portfolio_return = (portfolio_return)*252
    portfolio_volatility = float(portfolio_volatility) * np.sqrt(252)

    return portfolio_return, portfolio_volatility

def optimize_portfolio(desired_risk, desired_return, symbols):
    # Download historical price data using Yahoo Finance API
    historical_price_data = get_historical_price_data(symbols)

    # Calculate the log returns
    log_returns = np.log(historical_price_data / historical_price_data.shift(1))

    # Objective function to minimize
    def objective(weights):
        portfolio_std_dev = calculate_annualized_portfolio_volatility(weights, log_returns)
        portfolio_return = calculate_annualized_portfolio_return(weights, log_returns)
        return (portfolio_std_dev - desired_risk)**2 + (portfolio_return - desired_return)**2

    # Constraints for the optimization
    constraints = (
        {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},  # The sum of weights must be 1
    )

    # Bounds for the optimization (weights must be between 0 and 1)
    bounds = [(0, 1) for _ in range(len(symbols))]

    # Initialize equal weights for the optimization
    initial_weights = np.array(len(symbols) * [1 / len(symbols)])

    # Perform the optimization
    optimized_result = minimize(
        objective, initial_weights, method='SLSQP', bounds=bounds, constraints=constraints
    )

    return optimized_result.x

def get_historical_price_data(symbols, start_date='2020-01-01', end_date='2022-01-01'):
    data = yf.download(symbols, start=start_date, end=end_date)['Adj Close']
    return data

def calculate_annualized_portfolio_return(weights, log_returns):
    return np.sum(log_returns.mean() * weights) * 252

def calculate_annualized_portfolio_volatility(weights, log_returns):
    return np.sqrt(np.dot(weights.T, np.dot(log_returns.cov() * 252, weights)))

