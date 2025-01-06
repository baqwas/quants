#!/usr/bin/env python3
"""
List of tickers, set an exchange to False to exclude
get_tickers(NYSE=True, NASDAQ=True, AMEX=True)

Returns a list of top_n biggest tickers by market cap
get_tickers_filtered(mktcap_min=None, mktcap_max=None, sectors=None)

Region.DESIRED_REGION_HERE
Region constants include: AFRICA, EUROPE, ASIA, AUSTRALIA_SOUTH_PACIFIC, CARIBBEAN, SOUTH_AMERICA, MIDDLE_EAST, NORTH_AMERICA.

@sa https://github.com/shilewenuw/get_all_tickers
"""
from get_all_tickers import get_tickers as gt
from get_all_tickers.get_tickers import Region

# tickers of all exchanges
tickers = gt.get_tickers()
print(tickers[:5])

# tickers from NYSE and NASDAQ only
tickers = gt.get_tickers(AMEX=False)

# default filename is tickers.csv, to specify, add argument filename='your filename.csv'
gt.save_tickers()

# save tickers from NYSE and AMEX only
gt.save_tickers(NASDAQ=False)

# get tickers from Asia
tickers_asia = gt.get_tickers_by_region(Region.ASIA)
print(tickers_asia[:5])

# save tickers from Europe
gt.save_tickers_by_region(Region.EUROPE, filename='EU_tickers.csv')

# get tickers filtered by market cap (in millions)
filtered_tickers = gt.get_tickers_filtered(mktcap_min=500, mktcap_max=2000)
print(filtered_tickers[:5])

# not setting max will get stocks with $2000 million market cap and up.
filtered_tickers = gt.get_tickers_filtered(mktcap_min=2000)
print(filtered_tickers[:5])

# get tickers filtered by sector
#filtered_by_sector = gt.get_tickers_filtered(mktcap_min=200e3, sectors=SectorConstants.FINANCE)
#print(filtered_by_sector[:5])

# get tickers of 5 largest companies by market cap (specify sectors=SECTOR)
top_5 = gt.get_biggest_n_tickers(5)
print(top_5)