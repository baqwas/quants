#!/usr/bin/env python3
from get_all_tickers import get_tickers as gt
from get_all_tickers.get_tickers import Region

def __exchange2df(exchange):
    r = requests.get('https://api.nasdaq.com/api/screener/stocks', headers=headers, params=params)
    data = r.json()['data']
    df = pd.DataFrame(data['rows'], columns=data['headers'])
    return df