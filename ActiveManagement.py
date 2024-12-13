# --------------- ACTIVE PORTFOLIO MANAGEMENT --------------
# Project Completed for APPM 4720 - Open Topics in Applied Math - Optim. in Finance
# Date: 12/12/24

# Library Install
import math
import yfinance as yf
import pandas as pd
import numpy as np
import csv
from sklearn.linear_model import LinearRegression
from qpsolvers import solve_qp
import matplotlib.pyplot as plt

def fetch_and_filter_data(tickers):
    selected_tickers = []
    historical_data = {}

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            market_cap = stock.info.get("marketCap", 0)
            avg_volume = stock.info.get("averageVolume", 0)
            current_price = stock.info.get("currentPrice", 0)

            if((market_cap >= 2e6) & (avg_volume*current_price >= 20e6)):
                data = stock.history(period="5y")
                print("\t" + ticker + " --> Successful")
                if(not data.empty):
                    selected_tickers.append(ticker)
                    historical_data[ticker] = data["Close"]

        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
    
    return selected_tickers, pd.DataFrame(historical_data)

def fetch_and_filter_benchmark():
    sp500 = yf.Ticker("^GSPC")
    try:
        sp500_data = sp500.history(period='5y')["Close"]
        return pd.DataFrame(sp500_data)
    except Exception as e:
        print(f"Error fetching S&P 500 data: {e}")
    return -1

def covariance_matrix_build(calibration_data):
    returns = calibration_data.pct_change().dropna()
    covariance_matrix = returns.cov()
    return covariance_matrix

def beta_estimator(spx500_calibration_data, calibration_data):
    temp_spx_returns = spx500_calibration_data.pct_change().dropna()
    temp_spx_returns = temp_spx_returns.to_numpy()
    returns = calibration_data.pct_change().dropna()
    betas = {}

    spx_returns = []
    for i in range(len(temp_spx_returns)):
        spx_returns.append(float(temp_spx_returns[i][0]))

    for stock in returns.columns:
        model = LinearRegression()
        model.fit(np.array(spx_returns).reshape(-1,1), returns[stock].values)
        betas[stock] = float(model.coef_[0])
    return betas

def momentum_calculator(calibration_data):
    returns = calibration_data.pct_change().dropna()
    alphas = {}

    momentum = returns[-90:].mean()
    momentum_rank = momentum.rank(ascending=False)
    alpha = momentum_rank/len(momentum_rank)
    alphas = alpha.to_dict()
    return alphas

def long_only_optimization(covariance_matrix, alphas, betas):
    P = covariance_matrix.values
    q = alphas.values
    A = np.vstack([np.ones(len(alphas)), list(betas.values)])
    b = np.array([1,1])
    G = -np.eye(len(alphas))
    h = np.zeros(len(alphas))
    lb = np.zeros(len(alphas))

    weights_long_only = solve_qp(P, q, G, h, A, b, lb, solver='osqp', max_iter=800)
    return weights_long_only

def long_short_optimization(covariance_matrix, alphas, betas):
    P = covariance_matrix.values
    q = alphas.values
    A = np.vstack([np.ones(len(alphas)), list(betas.values)])
    b = np.array([1,1])
    G = np.eye(len(alphas))
    h = np.ones(len(alphas))

    weights_long_short = solve_qp(P, q, G, h, A, b, solver='osqp', max_iter=500)
    return weights_long_short 

def mix_optimization(covariance_matrix, alphas, betas):
    P = covariance_matrix.values
    q = alphas.values
    A = np.vstack([np.ones(len(alphas)), list(betas.values)])
    b = np.array([1,1])
    G_long = np.eye(len(alphas))
    G_short = -np.eye(len(alphas))
    h_long = np.ones(len(alphas))*1.3
    h_short = np.ones(len(alphas))*0.3
    G_combined = np.vstack([G_long, G_short])  # Add long-short bounds
    h_combined = np.hstack([h_long, h_short])

    weights_mix = solve_qp(P, q, G_combined, h_combined, A, b, solver='osqp', max_iter=500)
    return weights_mix

def calculate_returns(test_data, sp500_test_data, weights):
    portfolio_returns = test_data.pct_change().dot(weights)
    sp500_returns = sp500_test_data.pct_change()

    portfolio_cum_returns = (1 + portfolio_returns).cumprod()
    sp500_cum_returns = (1 + sp500_returns).cumprod()
    return portfolio_cum_returns, sp500_cum_returns

def visualisation(portfolio_cum_returns, sp500_cum_returns, title):
    plt.plot(portfolio_cum_returns, label="Portfolio")
    plt.plot(sp500_cum_returns, label="S&P 500")
    plt.legend()
    plt.title("Out-of-Sample Performance")
    plt.savefig(title)
    plt.clf()
    return -1

def rolling_window(n_days, window_len, n_windows, price_data, sp500_data):
    l_portfolio_returns = []
    ls_portfolio_returns = []
    mix_portfolio_returns = []
    sp500_returns = []
    last_low = [] 
    last_lsw = []
    last_mw = []
    skip_counter = 0
    for i in range(n_windows - 1):
        # Define in-sample and out-sample periods
        start = i * window_len
        in_sample_market = price_data[start : start + window_len]
        out_sample_market = price_data[start + window_len : start + 2 * window_len]

        in_sample_sp500 = sp500_data[start : start + window_len]
        out_sample_sp500 = sp500_data[start + window_len : start + 2 * window_len]

        # Compute covariance, betas, and alphas
        covariance_matrix = covariance_matrix_build(in_sample_market)
        betas = pd.Series(beta_estimator(in_sample_sp500, in_sample_market))
        alphas = pd.Series(momentum_calculator(in_sample_market))

        # Optimize portfolios
        long_only_weights = long_only_optimization(covariance_matrix, alphas, betas) 
        long_short_weights = long_short_optimization(covariance_matrix, alphas, betas)
        mix_weights = mix_optimization(covariance_matrix, alphas, betas)

        # Store last valid weights
        #last_low, last_lsw, last_mw = long_only_weights, long_short_weights, mix_weights

        # Calculate and store periodic returns
        l_return, sp500_return = calculate_returns(out_sample_market, out_sample_sp500, long_only_weights)
        ls_return, _ = calculate_returns(out_sample_market, out_sample_sp500, long_short_weights)
        print(ls_return)
        mix_return, _ = calculate_returns(out_sample_market, out_sample_sp500, mix_weights)

        l_portfolio_returns.append(l_return.dropna())
        ls_portfolio_returns.append(ls_return.dropna())
        mix_portfolio_returns.append(mix_return.dropna())
        sp500_returns.append(sp500_return.dropna())

# Calculate cumulative returns
    l_portfolio_cum_returns = pd.concat(l_portfolio_returns)
    ls_portfolio_cum_returns = pd.concat(ls_portfolio_returns)
    mix_portfolio_cum_returns = pd.concat(mix_portfolio_returns)
    sp500_cum_returns = pd.concat(sp500_returns)

    print(l_portfolio_cum_returns)
    print(ls_portfolio_cum_returns)
    print(mix_portfolio_cum_returns)
    print(sp500_cum_returns)

    long_vis = visualisation(l_portfolio_cum_returns, sp500_cum_returns, "Rolling_Long_Only_Chart.pdf")
    long_short_vis = visualisation(ls_portfolio_cum_returns, sp500_cum_returns, "Rolling_Long_Short_Chart.pdf")
    mix_vis = visualisation(mix_portfolio_cum_returns, sp500_cum_returns, "Rolling_Mix_Chart.pdf")

    print(skip_counter)

    return -1
'''
    for i in range(n_windows-1):
        start = i*window_len
        in_sample_market = price_data[start : start+window_len]
        out_sample_market = price_data[start+window_len : start+(2*window_len)]

        in_sample_sp500 = sp500_data[start : start+window_len]
        out_sample_sp500 = sp500_data[start+window_len : start+(2*window_len)]

        covariance_matrix = covariance_matrix_build(in_sample_market) 

        betas = beta_estimator(in_sample_sp500, in_sample_market)
        betas = pd.Series(betas)

        alphas = momentum_calculator(in_sample_market)
        alphas = pd.Series(alphas)

        long_only_weights = long_only_optimization(covariance_matrix, alphas, betas)
        if(long_only_weights is not None):
            last_low = long_only_weights
        else:
            skip_counter += 1
            long_only_weights = last_low
        l_return, sp500_return = calculate_returns(out_sample_market, out_sample_sp500, long_only_weights)
        l_portfolio_returns.append(l_return.dropna().cumprod())
        sp500_returns.append(sp500_return.dropna().cumprod())
        print(l_return)
        print(sp500_return)
        
        long_short_weights = long_short_optimization(covariance_matrix, alphas, betas)
        if(long_short_weights is not None):
            last_lsw = long_short_weights
        else:
            skip_counter += 1
            long_short_weights = last_lsw
        ls_return, temp1 = calculate_returns(out_sample_market, out_sample_sp500, long_short_weights) 
        ls_portfolio_returns.append(ls_return.dropna().cumprod())
        print(ls_return)

        mix_weights = mix_optimization(covariance_matrix, alphas, betas)
        if(mix_weights is not None):
            last_mw = mix_weights
        else:
            skip_counter += 1
            mix_weights = last_mw
        mix_return, temp1 = calculate_returns(out_sample_market, out_sample_sp500, mix_weights) 
        mix_portfolio_returns.append(mix_return.dropna().cumprod())
        print(mix_return)

    l_portfolio_cum_returns = pd.concat(l_portfolio_returns)
    ls_portfolio_cum_returns = pd.concat(ls_portfolio_returns)
    mix_portfolio_cum_returns = pd.concat(mix_portfolio_returns)
    sp500_cum_returns = pd.concat(sp500_returns)
    '''


def main():
    candidate_tickers = []

    file_path = input("Filepath for Tickers: ")
    with open(file_path, 'r', encoding='utf-8-sig') as data:
        for line in csv.reader(data):
            candidate_tickers.append(line[0])

    print("* Loading Candidate Tickers...")
    print("* Candidate Tickers:")
    for i in range(len(candidate_tickers)):
        print("\t" + candidate_tickers[i])

    print("* Fetching and Filtering Historical Data...")
    selected_tickers, price_data = fetch_and_filter_data(candidate_tickers)

    print("* Selected Tickers:")
    for i in range(len(selected_tickers)):
        print("\t" + selected_tickers[i])

    print("* Validating Historical Data...")
    price_data.index = pd.to_datetime(price_data.index, format='%Y-%m-%d')
    price_data = price_data.dropna(axis=1)
    print("* Validation Complete")

    print("* Segregating Data into Calibration and Test Data...")
    n = len(price_data)
    calibration_data = price_data.iloc[:int(n*0.6)]
    test_data = price_data.iloc[int(n*0.6):]
    print("* Segregation Complete")

    print("* Saving Datasets...")
    price_data.to_csv("Price_Data.csv")
    calibration_data.to_csv("Calibration_Data.csv")
    test_data.to_csv("Test_Data.csv")
    print("* Datasets Saved")

    print("* Fetching Benchmark Data...")
    sp500_data = fetch_and_filter_benchmark()

    print("* Segregating Benchmark Data...")
    m = len(sp500_data)
    sp500_calibration_data = sp500_data.iloc[:int(m*0.6)]
    sp500_test_data = sp500_data.iloc[int(m*0.6):]
    print("* Segregation Complete")

    print("* Saving Benchmark Dataset...")
    sp500_data.to_csv("Benchmark_Data.csv")
    sp500_calibration_data.to_csv("Benchmark_Calibration_Data.csv")
    sp500_test_data.to_csv("Benchmark_Test_Data.csv")
    print("* Benchmark Data Saved")

    print("* Building Covariance Matrix From Calibration Data...")
    covariance_matrix = covariance_matrix_build(calibration_data)
    print(covariance_matrix.to_string())
    print("* Covariance Matrix Constructed")

    print("* Estimating Betas...")
    betas = beta_estimator(sp500_calibration_data, calibration_data)
    for key, value in betas.items():
        print("\t", key, ": ", value)
    betas = pd.Series(betas)
    print("* Beta Estimation Complete")

    print("* Calculating Alphas...")
    alphas = momentum_calculator(calibration_data)
    for key, value in alphas.items():
        print("\t", key, ": ", value)
    alphas = pd.Series(alphas)
    print("* Alpha Estimation Complete")

    print("* Building Long Only Optimization...")
    long_only_weights = long_only_optimization(covariance_matrix, alphas, betas)
    print(long_only_weights)
    print("* Long Only Optimization Successful")
    
    print("* Builing Long-Short Optimization...")
    long_short_weights = long_short_optimization(covariance_matrix, alphas, betas)
    print(long_short_weights)
    print("* Long-Short Optimization Complete")

    print("* Builing 130/30 Optimization...")
    mix_weights = mix_optimization(covariance_matrix, alphas, betas)
    print("* 130/30 Optimization Complete")

    print("* Calculating Portfolio Restults...")
    l_portfolio_cum_returns, sp500_cum_returns = calculate_returns(test_data, sp500_test_data, long_only_weights)
    ls_portfolio_cum_returns, sp500_cum_returns = calculate_returns(test_data, sp500_test_data, long_short_weights)
    mix_portfolio_cum_returns, sp500_cum_returns = calculate_returns(test_data, sp500_test_data, mix_weights)
    print("* Portfolio Results Calculated")

    print("* Visualizing Results...")
    long_vis = visualisation(l_portfolio_cum_returns, sp500_cum_returns, "NR_Long_Only_Chart.pdf")
    long_short_vis = visualisation(ls_portfolio_cum_returns, sp500_cum_returns, "NR_Long_Short_Chart.pdf")
    mix_vis = visualisation(mix_portfolio_cum_returns, sp500_cum_returns, "NR_Mix_Chart.pdf")
    print("* Visualizations Saved")

    print("* Performing Rolling-Window Calculations...")
    n_days = min(n,m)
    window_len = 90
    n_windows = n_days // window_len
    rolling = rolling_window(n_days, window_len, n_windows, price_data, sp500_data)
    print("* Rolling-Window Calculations Complete")

    print("------------------------- End of Program -------------------------")
    return -1

if __name__ == '__main__':
    main()










