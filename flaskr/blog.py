import requests
import os
import pandas as pd
import numpy as np
import config
import functools
from flask import Blueprint
from flask import flash
from flask import Flask
from flask import g
from flask import redirect
from flask import render_template
from flask import request, jsonify
from flask import session
from flask import url_for
from flask import abort
import base64
from io import BytesIO
import plotly.graph_objects as go
import plotly.express as px
import plotly
import pytz

import yfinance as yf

from werkzeug.exceptions import abort

from flaskr.auth import login_required
from flaskr.db import get_db
import json

from datetime import datetime, timedelta, date

from .portfolio import eff, sharp_ratio, current_eff, optimize_portfolio

API_KEY = config.API_KEY

bp = Blueprint("blog", __name__)

def get_close_price(symbol, date):
    url1 = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=full&apikey={API_KEY}'
    r1 = requests.get(url1)
    data1 = r1.json()
    error=None

    if 'Time Series (Daily)' not in data1:
        close_price=get_historical_data(symbol, date)
        return close_price

    date_list = list(data1['Time Series (Daily)'].keys())
    
    try:
        close_price = data1['Time Series (Daily)'][date]['5. adjusted close']
    except KeyError:
        return -1
    return round(float(close_price), 2)

def get_historical_data(symbol, date):
    endpoint = 'https://min-api.cryptocompare.com/data/v2/histoday'
    currency = 'USD'
    limit = 1500
    params = {
        'fsym': symbol,
        'tsym': currency,
        'limit': limit
    }
    r = requests.get(endpoint, params=params)
    data = r.json()
    if 'Data' not in data or 'Data' in data and not data['Data']:
        print(f"No data found for symbol {symbol}")
        return -1
    data = r.json()['Data']['Data']
    df = pd.DataFrame(data)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df = df[['open', 'high', 'low', 'close', 'volumefrom', 'volumeto']]
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'Market Cap']
    df = df.astype(float)
    #df = df.astype(float)

    try:
        p=df.loc[date, 'Close']
    except KeyError:
        return -1

    return round(float(p),2)



@bp.route("/")
def index():
    # news = get_news()
    # return render_template('blog/index.html', news=news)
    return redirect(url_for("auth.login"))

# def get_news():
#     response = requests.get(f'https://www.alphavantage.co/query?function=NEWS_SENTIMENT&symbol=AAPL&apikey={API_KEY}')
#     data = response.json()['feed'][:10]
#     news = []
#     for item in data:
#         news.append({
#             "title": item["title"],
#             "url": item["url"],
#         })
#     return news

@bp.route("/dashboard")
def dashboard():
    return render_template("blog/index.html")

@bp.route("/adm_dashboard")
def adm_dashboard():
    return render_template("blog/adm_index.html")

@bp.route("/stock_operation", methods=("GET", "POST"))
@login_required
def buy_stock():
    """Buy or sell a stock for the current user."""
    date_str=0
    if request.method == "POST":
        error = None
        db = get_db()
        cursor = db.cursor()
        operation = request.form["operation"]
        symbol = (request.form["symbol"]).upper()
        # price = request.form["price"]
        shares = request.form["shares"]
        date = datetime.strptime(request.form["date"], '%Y-%m-%d')
        date_str=request.form["date"]
        close_price = get_close_price(symbol, date_str)

        if close_price==-1:
            error="No stock info for this date"
            flash(error)
            return redirect(url_for("blog.buy_stock"))
        date_to_check = get_date_to_check()
        today_close_price = get_close_price(symbol, date_to_check)

        if today_close_price==-1:
            today = date.today()
            yesterday = today - timedelta(days=1)
            today_close_price=get_close_price(symbol, yesterday.strftime("%Y-%m-%d"))
            if today_close_price==-1:
                today=yesterday
                yesterday=today - timedelta(days=1)
                today_close_price=get_close_price(symbol, yesterday.strftime("%Y-%m-%d"))
                if today_close_price==-1:
                    today=yesterday
                    yesterday=today - timedelta(days=1)
                    today_close_price=get_close_price(symbol, yesterday.strftime("%Y-%m-%d"))

        

        if close_price==-1:
            error="No such symbol"
            flash(error)
            return redirect(url_for("blog.buy_stock"))
        amount = round(float(shares) * float(close_price),3)

        # change = (float(close_price)/float(price) - 1) * 100

        if '.' in shares:
            error = "Cannot operate non integer share of stock"
            flash(error)
            return redirect(url_for("blog.buy_stock"))
        elif float(shares)<=0:
            error = "Cannot operate negative or 0 share of stock"
            flash(error)
            return redirect(url_for("blog.buy_stock"))

        cursor.execute("SELECT shares FROM holdings WHERE stockid=? AND u_id=?", (symbol, g.user["userid"]))# retrive old shares from table
        fetch=cursor.fetchone()
        if fetch is None:
            pre_shares=0
        else:
            pre_shares=fetch[0]

        cursor.execute("SELECT worth FROM holdings WHERE stockid=? AND u_id=?", (symbol,g.user["userid"]))# retirve old worth from table
        fetch=cursor.fetchone()
        if fetch is None:
            pre_amount=0
        else:
            pre_amount=fetch[0]
        cursor.execute("SELECT account_balance from user where userid=?", (g.user["userid"],))
        balance = cursor.fetchone()[0]
        if operation=='Buy':
            if float(balance)>=float(shares)*float(close_price):
                db.execute(
                    "INSERT INTO history (stockid, created_time, price, shares, u_id, worth) VALUES (?, ?, ?, ?, ?, ?)",
                    (symbol, date, close_price, float(shares), g.user["userid"], amount),
                    )
                db.commit()
                newbalance = float(balance)-float(shares)*float(close_price)
                db.execute(
                    "UPDATE user SET account_balance=? WHERE userid=?",
                    (newbalance,g.user["userid"])
                )
                db.commit()
                new_shares=float(shares)+float(pre_shares)
                new_amount=round(float(amount)+float(pre_amount), 2)
                new_price=round(new_amount/(float(pre_shares)+float(shares)),2)
                if pre_shares==0:
                    db.execute(
                    "INSERT INTO holdings (stockid, price, shares, u_id, new_price, worth) VALUES (?, ?, ?, ?, ?, ?)",
                    (symbol, close_price, new_shares, g.user["userid"], today_close_price, new_amount),
                    )
                    db.commit()
                    return redirect(url_for("blog.buy_stock"))
                else:
                    db.execute("UPDATE holdings SET shares=?, price=?, new_price=?, worth=? WHERE stockid = ?", 
                        (new_shares, new_price, today_close_price, new_amount, symbol ))
                    db.commit()
                    return redirect(url_for("blog.buy_stock"))
            else:
                error = "You don't have enough balance in your account"
                flash(error)

        else:
            if float(pre_shares)<float(shares):
                error = "You don't have enough stock in your account"
                flash(error)
            else:
                new_shares=float(pre_shares)-float(shares)
                new_amount=round(float(pre_amount)-float(amount), 2)
                #new_price=round(new_amount/new_shares,2)
                if new_shares==0:
                    db.execute("DELETE FROM holdings WHERE stockid = ?", (symbol,))
                    db.commit()
                    db.execute("INSERT INTO history (stockid, created_time, price, shares, u_id, worth) VALUES (?, ?, ?, ?, ?, ?)",
                    (symbol, date, close_price, -1*float(shares), g.user["userid"], -1*amount),)
                    db.commit()
                    newbalance=float(balance)+amount
                    db.execute(
                        "UPDATE user SET account_balance=? WHERE userid=?",
                        (newbalance,g.user['userid'])
                    )
                    db.commit()
                elif new_shares<0:# corner case
                    error = "Cannot sell more shares than you own"
                    flash(error)
                else:
                    new_price=round(new_amount/new_shares,2)
                    db.execute(
                    "INSERT INTO history (stockid, created_time, price, shares, u_id, worth) VALUES (?, ?, ?, ?, ?, ?)",
                    (symbol, date, close_price, -1*float(shares), g.user["userid"], -1*amount),
                    )
                    db.commit()
                    newbalance=float(balance)+amount
                    db.execute(
                        "UPDATE user SET account_balance=? WHERE userid=?",
                        (newbalance,g.user['userid'])
                    )
                    db.commit()
                    db.execute("UPDATE holdings SET shares=?, worth=?, price=?, new_price=? WHERE stockid = ?", 
                            (new_shares, new_amount, new_price, today_close_price, symbol ))
                    db.commit()
                return redirect(url_for("blog.buy_stock"))
        

    db = get_db()
    user_id = session.get('user_id')
    holdings = db.execute(
        "SELECT * FROM holdings h where h.u_id = ?", (user_id,)
    ).fetchall()   

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT SUM(worth) FROM holdings WHERE u_id= ?", (user_id,))
    fetch=cursor.fetchone()
    total_worth=0

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT stockid FROM holdings WHERE u_id=?", (user_id,))
    fetch=cursor.fetchall()

    if fetch is not None and len(fetch) != 0:
        total_worth=-1
        stock_ls=[row[0] for row in fetch]

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT shares FROM holdings WHERE u_id=?", (user_id,))
    fetch=cursor.fetchall()

    if fetch is not None and len(fetch) != 0:
        total_worth=-1
        share_ls=[row[0] for row in fetch]

    if total_worth==-1:
        total_worth=get_total_worth(stock_ls, share_ls)
    # if fetch is not None and fetch[0] is not None:
    #     total_worth=round(float(fetch[0]), 2)
    cursor.execute("SELECT account_balance from user where userid=?", (g.user["userid"],))
    finalbalance = round(cursor.fetchone()[0],2)
    return render_template("blog/stock_operation.html", holdings=holdings, total_worth=total_worth, finalbalance=finalbalance)

def is_market_closed():
    now = datetime.now(pytz.timezone('US/Eastern'))
    if now.weekday() >= 5:  # If it's weekend, the market is closed.
        return True
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return not market_open <= now <= market_close

def get_date_to_check():
    today = date.today()
    if is_market_closed():
        return today.strftime("%Y-%m-%d")
    else:
        yesterday = today - timedelta(days=1)
        return yesterday.strftime("%Y-%m-%d")

def get_total_worth(stock_ls, share_ls):
    total_worth=0
    date1=get_date_to_check()
    for i in range(len(stock_ls)):
        # db = get_db()
        # cursor = db.cursor()
        # cursor.execute("SELECT created_time FROM holdings WHERE u_id= ?", (u_id,))
        # fetch=cursor.fetchone()
        price=get_close_price(stock_ls[i], date1)
        if price==-1:
            today = date.today()
            yesterday = today - timedelta(days=1)
            price=get_close_price(stock_ls[i], yesterday.strftime("%Y-%m-%d"))
            if price==-1:
                today=yesterday
                yesterday=today - timedelta(days=1)
                price=get_close_price(stock_ls[i], yesterday.strftime("%Y-%m-%d"))
                if price==-1:
                    today=yesterday
                    yesterday=today - timedelta(days=1)
                    price=get_close_price(stock_ls[i], yesterday.strftime("%Y-%m-%d"))
        total_worth=total_worth + float(price)*float(share_ls[i])
    return round(total_worth, 2)

@bp.route('/history')
@login_required
def history():
    db = get_db()
    user_id = session.get('user_id')
    history = db.execute(
        "SELECT * FROM history h where h.u_id = ?", (user_id,)# add current date createtime==current datetime
    ).fetchall()

    return render_template("blog/history.html", history=history)

@bp.route('/adm_history')
def adm_history():
    db = get_db()
    # user_id = session.get('user_id')
    cursor=db.cursor()
    cursor.execute("SELECT * FROM history ")
    history_list=cursor.fetchall()

    return render_template("blog/adm_history.html", history_list=history_list)

@bp.route('/adm_holding')
def adm_holding():
    db = get_db()
    # user_id = session.get('user_id')
    cursor=db.cursor()
    cursor.execute("SELECT * FROM holdings GROUP BY u_id,stockid ")
    holding_list=cursor.fetchall()

    return render_template("blog/adm_holding.html", holding_list=holding_list)

@bp.route('/stock_history',methods=("GET","POST"))
@login_required
def stock_history():
    db = get_db()
    user_id = session.get('user_id')
    symbols = db.execute(
        "SELECT stockid FROM holdings where u_id = ?", (user_id,)
    ).fetchall()
    if symbols is None:
        return redirect(url_for("blog.stock_history"))
    return render_template("blog/stock_history.html", symbols=symbols)

@bp.route('/find_stock_info')
def find_stock_info():
    """Return 5 year stock data"""
    symbol = request.args.get('stock_name')
    url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=full&apikey={API_KEY}'
    response = requests.get(url)
    data = response.json().get('Time Series (Daily)', {})

    if not data:
        endpoint = 'https://min-api.cryptocompare.com/data/v2/histoday'
        currency = 'USD'
        limit = 1500
        params = {
            'fsym': symbol,
            'tsym': currency,
            'limit': limit
        }
        r = requests.get(endpoint, params=params)
        data = r.json()
        if 'Data' not in data or 'Data' in data and not data['Data']:
            print(f"No data found for symbol {symbol}")
            return -1
        data = r.json()['Data']['Data']
        df = pd.DataFrame(data)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volumefrom', 'volumeto']]
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'Market Cap']
        df = df.astype(float)
        dates=df.index.tolist()
        for i in range(len(dates)):
            dates[i]=dates[i].strftime('%Y-%m-%d')
        close_prices=df['Close'].tolist()

    # Extract the closing price data for the last 5 years
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        five_years_ago = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d')
        dates = [date for date in data.keys() if five_years_ago <= date <= today]
        dates.sort()
        close_prices = [float(data[date]['4. close']) for date in dates]

    # Define the ticker symbol
    tickerSymbol = 'SPY'

    # Get data for the specified ticker symbol
    tickerData = yf.Ticker(tickerSymbol)

    # Calculate the date 5 years ago from today
    fiveYearsAgo = (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d')

    # Get the historical prices for the specified ticker symbol for the last 5 years
    tickerDf = tickerData.history(period='1d', start=fiveYearsAgo, end=datetime.now().strftime('%Y-%m-%d'))

    # Extract the 'Close' column as a list
    spyPrices = tickerDf['Close'].tolist()

    for i in range(len(spyPrices)):
        spyPrices[i]=round(float(spyPrices[i]), 2)

    # Return the data in JSON format
    result = {'dates': dates, 'close_prices': close_prices, 'spyPrices': spyPrices}
    return jsonify(result)
    


@bp.route("/mnmanage", methods=("GET", "POST"))
@login_required
def recharge_withdraw():
    if request.method == "POST":
        db = get_db()
        userid = g.user["userid"]
        cursor = db.cursor()
        decision = request.form["mnmanage"]
        amount = request.form["amount"]
        error = None
        if float(amount)<=0:
            error = "Cannot recharge/withdraw 0 or negative values."
            flash(error)
        
        cursor.execute("SELECT account_balance FROM user WHERE userid=?", (userid,))# retrive old account balance from table
        fetch=cursor.fetchone()
        if fetch is None:
            pre_balance=0
        else:
            pre_balance=fetch[0]
        if decision=='Recharge':
            newBalance = float(pre_balance) + float(amount)
            db.execute("UPDATE user SET account_balance=? WHERE userid = ?", 
                       (newBalance, userid))
            db.commit()
            return redirect(url_for("blog.recharge_withdraw"))
        else:
            newBalance = float(pre_balance) - float(amount)
            if newBalance < 0:
                error = "Cannot withdraw more money than you own"
                flash(error)
            else:
                db.execute("UPDATE user SET account_balance=? WHERE userid = ?", 
                           (newBalance, userid))
                db.commit()
        return redirect(url_for("blog.recharge_withdraw"))
    db = get_db()
    user_id = session.get('user_id')
    aBalance = db.execute(
        "SELECT account_balance FROM user where userid = ?", (user_id,)
    ).fetchone()[0]   
    return render_template("blog/recharge&withdraw.html",aBalance=float(aBalance))



@bp.route('/portfolio', methods=['GET','POST'])
@login_required
def efficient_frontier():
    user_id=user_id = session.get('user_id')
    
    db=get_db()
    symbols=db.execute("SELECT stockid FROM holdings WHERE u_id = ?", (user_id,)).fetchall()
    symbol_ls = [item[0] for item in symbols]
    shares=db.execute("SELECT shares FROM holdings WHERE u_id = ?", (user_id,)).fetchall()
    share_ls = [item[0] for item in shares]
    symbol_ls = [str(symbol) for symbol in symbol_ls]
    worth = db.execute("SELECT new_price*shares AS worth FROM holdings WHERE u_id = ?", (user_id,)).fetchall()
    worth_ls = [item[0] for item in worth]
    if request.method == 'POST':
        desired_return = request.form['desired_return']
        desired_risk = request.form['desired_risk']
        
        if not desired_return or not desired_risk:
            error='You need to provide both risk and return to get a suggestion!'
            flash(error)
            return redirect(url_for("blog.efficient_frontier"))

        desired_return = float(desired_return)
        desired_risk = float(desired_risk)
        optimized_weights = optimize_portfolio(desired_risk, desired_return, symbol_ls)
        optimized_weights = dict(zip(symbol_ls, optimized_weights))
    else:
        optimized_weights = {}
    pie_plot = go.Figure(data=[go.Pie(labels=symbol_ls, values=worth_ls)])
    # port_returns, port_vol = eff(symbol_ls)
    # port_returns=np.array(port_returns).tolist()
    # port_vol=np.array(port_vol).tolist()

    # curr_return, curr_vol = current_eff(symbol_ls, share_ls)
    # curr_return=float(curr_return)
    # curr_vol=float(curr_vol)


    # Create a Plotly scatter graph
    if len(symbol_ls) > 1:
        port_returns, port_vol = eff(symbol_ls)
        port_returns=np.array(port_returns).tolist()
        port_vol=np.array(port_vol).tolist()

        curr_return, curr_vol = current_eff(symbol_ls, share_ls)
        curr_return=float(curr_return)
        curr_vol=float(curr_vol)

        sharp = round(sharp_ratio(symbol_ls, share_ls), 4)
        data = [{
            'x': port_vol,
            'y': port_returns,
            'type': 'line',
            'mode': 'lines',
            'marker': {
                'color': 'blue',
                'size': 8,
                'opacity': 0.5
            }
        },
        {
        'x': [curr_vol],
        'y': [curr_return],
        'type': 'scatter',
        'mode': 'markers',
        'marker': {
            'color': 'red',
            'size': 10,
            'opacity': 1.0
        },
        'name': 'Current Portfolio'
        }]
    
    elif len(symbol_ls) == 1:
        curr_return, curr_vol = current_eff(symbol_ls, share_ls)
        curr_return=float(curr_return)
        curr_vol=float(curr_vol)

        sharp = 0

        data = [
        {
        'x': [curr_vol],
        'y': [curr_return],
        'type': 'scatter',
        'mode': 'markers',
        'marker': {
            'color': 'red',
            'size': 10,
            'opacity': 1.0
        },
        'name': 'Current Portfolio'
        }]
    
    else:
        data=[]
        sharp=0

    layout = {
        'title': 'Efficient Frontier',
        'xaxis': {'title': 'Portfolio Volatility'},
        'yaxis': {'title': 'Portfolio Returns'}
    }
    graphJSON = json.dumps({'data': data, 'layout': layout})

    #sharp = round(sharp_ratio(symbol_ls, share_ls), 4)
    return render_template("blog/efficient_frontier.html", graphJSON=graphJSON, sharp_ratio=sharp,pie_plot=pie_plot.to_html(full_html=False),optimized_weights=optimized_weights)


@bp.route('/adm_efficient_frontier')
def adm_efficient_frontier():
    db=get_db()
    symbols=db.execute("SELECT stockid FROM holdings ").fetchall()
    symbol_ls = [item[0] for item in symbols]
    shares=db.execute("SELECT shares FROM holdings ").fetchall()
    share_ls = [item[0] for item in shares]

    sy, sh=[], []
    pie_plot = go.Figure(data=[go.Pie(labels=symbol_ls, values=share_ls)])
    for i in range(len(symbol_ls)):
        if symbol_ls[i] not in sy:
            sy.append(symbol_ls[i])
            sh.append(float(share_ls[i]))
        else:
            index=sy.index(symbol_ls[i])
            sh[index]=sh[index]+ float(share_ls[i])
    
    if len(sy)>1:
        port_returns, port_vol = eff(sy)
        port_returns=np.array(port_returns).tolist()
        port_vol=np.array(port_vol).tolist()

        curr_return, curr_vol = current_eff(sy, sh)
        curr_return=float(curr_return)
        curr_vol=float(curr_vol)

        sharp = round(sharp_ratio(sy, sh), 4)
        # Create a Plotly scatter graph
        data = [{
            'x': port_vol,
            'y': port_returns,
            'type': 'scatter',
            'mode': 'markers',
            'marker': {
                'color': 'blue',
                'size': 8,
                'opacity': 0.5
            }
        },
        {
        'x': [curr_vol],
        'y': [curr_return],
        'type': 'scatter',
        'mode': 'markers',
        'marker': {
            'color': 'red',
            'size': 10,
            'opacity': 1.0
        },
        'name': 'Current Portfolio'
        }]

        layout = {
            'title': 'Efficient Frontier',
            'xaxis': {'title': 'Portfolio Volatility'},
            'yaxis': {'title': 'Portfolio Returns'}
        }
    
    elif len(sy)==1:
        curr_return, curr_vol = current_eff(sy, sh)
        curr_return=float(curr_return)
        curr_vol=float(curr_vol)

        sharp = 0
        # Create a Plotly scatter graph
        data = [{
        'x': [curr_vol],
        'y': [curr_return],
        'type': 'scatter',
        'mode': 'markers',
        'marker': {
            'color': 'red',
            'size': 10,
            'opacity': 1.0
        },
        'name': 'Current Portfolio'
        }]
        layout = {
            'title': 'Efficient Frontier',
            'xaxis': {'title': 'Portfolio Volatility'},
            'yaxis': {'title': 'Portfolio Returns'}
        }
    
    else:
        data=[]
        sharp=0

    graphJSON = json.dumps({'data': data, 'layout': layout})

    #sharp = round(sharp_ratio(sy, sh), 4)

    return render_template("blog/adm_efficient_frontier.html", graphJSON=graphJSON, sharp_ratio=sharp,pie_plot=pie_plot.to_html(full_html=False))   


@bp.route('/stock_charts',methods=("GET","POST"))
@login_required
def stock_charts():
    if request.method == "POST":
    # db = get_db()
    # user_id = session.get('user_id')
        stock = (request.form["stock_symbol"]).upper()
        index = (request.form["index_symbol"]).upper()
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
        today = date.today()
        error=None
        if start_date>today or end_date>today:
            error='Ohh, your input dates has not come yet, please change'
            flash(error)
            return redirect(url_for("blog.stock_charts"))
        if start_date>=end_date:
            error='Ohh, your start date is later than or equal to end date, please change'
            flash(error)
            return redirect(url_for("blog.stock_charts"))
        url1 = f"https://finance.yahoo.com/quote/{stock}"
        response = requests.get(url1)
        if response.status_code == 404:
            error=f"{stock} is not a valid stock symbol"
            flash(error)
            return redirect(url_for("blog.stock_charts"))
        url2 = f"https://finance.yahoo.com/quote/{index}"
        response = requests.get(url2)
        if response.status_code == 404:
            error=f"{index} is not a valid symbol"
            flash(error)
            return redirect(url_for("blog.stock_charts"))
        data = yf.download(stock+' '+index, start=start_date, end=end_date)['Adj Close']
        # url1 = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={stock}&apikey={API_KEY}'
        # r1 = requests.get(url1)
        # data1 = r1.json()
        # url2 = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={index}&apikey={API_KEY}'
        # r2 = requests.get(url2)
        # data2 = r2.json()
        price_plot = px.line(x=data.index,y=data[stock])
        price_plot = price_plot.update_layout(
            xaxis=dict(
            title='Date',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            yaxis=dict(
            title='Price',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            title=stock+' Price Chart',
            plot_bgcolor='white'
        )
        simple_rtn = data[stock].pct_change().dropna()
        rtn_sct = px.scatter(x=simple_rtn.index, y=simple_rtn.values)
        rtn_sct = rtn_sct.update_layout(
            xaxis=dict(
            title='Date',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            yaxis=dict(
            title='Daily Return (%)',
            tickformat='.0%',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            title='Simple return of '+stock,
            plot_bgcolor='white'
        )
        t_vs_y = px.scatter(x=simple_rtn.values[:-1], y=simple_rtn.values[1:])
        t_vs_y = t_vs_y.update_layout(
            xaxis=dict(
            title='Simple return (-1)',
            tickformat='.0%',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            yaxis=dict(
            title='Simple return',
            tickformat='.0%',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            title=stock+' Today vs Yesterday Return',
            plot_bgcolor='white'
        )
        histogram = px.histogram(simple_rtn.values,nbins=25)
        histogram.update_layout(
            xaxis=dict(
            title='Daily Return',
            tickformat='.0%',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            yaxis=dict(
            title='Frequency',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            title='Daily Returns Frequency of '+stock,
            showlegend=False,
            bargap=0.2,
            plot_bgcolor='white'
        )
        index_rtn = data[index].pct_change().dropna()
        simple_rtn = data[stock].pct_change().dropna()
        index_rtn = pd.DataFrame(index_rtn)
        index_rtn.columns = ['Value']
        index_rtn['type'] = index
        simple_rtn = pd.DataFrame(simple_rtn)
        simple_rtn.columns = ['Value']
        simple_rtn['type'] = stock
        m = pd.concat([simple_rtn,index_rtn])
        m = m.reset_index()
        stk_idx_rtn = px.line(m,x='Date',y='Value',color='type')
        stk_idx_rtn.update_layout(
            xaxis=dict(
            title='Date',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            yaxis=dict(
            title='Daily returns (%)',
            tickformat='.0%',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            plot_bgcolor='white',
            title='Daily percentage change in price for '+stock+' and '+index
        )
        stock_index_scatter = px.scatter(x=m['Value'][m['type']==index],y=m['Value'][m['type']==stock],trendline='ols')
        stock_index_scatter.update_layout(
            xaxis=dict(
            title=index+' returns',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            yaxis=dict(
            title=stock+' returns',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            plot_bgcolor='white',
            title='Scatter graph of '+stock+' and '+index +' return, with trendline'
        )
        data['stock relative price'] = data[stock]/data.iloc[0][0]
        data['index relative price'] = data[index]/data.iloc[0][1]
        data = data.reset_index()
        relative_price_chart = px.line(data,x='Date',y=['stock relative price','index relative price'])
        relative_price_chart.update_layout(
            xaxis=dict(
            title='Date',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            yaxis=dict(
            title='Relative price',
            showgrid=True,
            gridcolor='lightgrey',
            zeroline=True,  # Show the line at x=0
            zerolinecolor='black',
            ),
            title='Daily price movements of '+stock+' and '+index,
            plot_bgcolor='white'
        )
        # priceJSON = json.dumps(price_plot, cls=plotly.utils.PlotlyJSONEncoder)
        # returnJSON = json.dumps(rtn_sct, cls=plotly.utils.PlotlyJSONEncoder)
        # tvyJSON = json.dumps(t_vs_y, cls=plotly.utils.PlotlyJSONEncoder)
        # hisJSON = json.dumps(histogram, cls=plotly.utils.PlotlyJSONEncoder)
        return render_template("blog/stock_charts.html", 
                            price_plot=price_plot.to_html(full_html=False),
                            rtn_sct=rtn_sct.to_html(full_html=False),
                            t_vs_y=t_vs_y.to_html(full_html=False),
                            histogram=histogram.to_html(full_html=False),
                            relative_price_chart=relative_price_chart.to_html(full_html=False),
                            stk_idx_rtn=stk_idx_rtn.to_html(full_html=False),
                            stock_index_scatter=stock_index_scatter.to_html(full_html=False))
    return render_template("blog/stock_charts.html")






