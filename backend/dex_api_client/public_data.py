import aiohttp
import asyncio
import json

async def fetch_ticker_data(session, symbol, exchange_url):
    """Fetches ticker data for a single symbol from the exchange API."""
    try:
        async with session.get(f"{exchange_url}{symbol}") as response:
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            data = await response.json()
            return symbol, data
    except aiohttp.ClientError as e:
        print(f"Error fetching data for {symbol}: {e}")
        return symbol, None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON for {symbol}: {e} - Response: {await response.text()}")
        return symbol, None
    except Exception as e:
        print(f"Unexpected error fetching ticker for {symbol}: {e}")
        return symbol, None



async def get_binance_tickers(symbols):
    """Fetches ticker data for multiple symbols from the Binance API."""
    exchange_url = "https://api.binance.com/api/v3/ticker/24hr?symbol="
    results = {}

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_ticker_data(session, symbol, exchange_url) for symbol in symbols]
        tickers_data = await asyncio.gather(*tasks)

        for symbol, data in tickers_data:
            if data:
                try:
                    price_change_percent = float(data['priceChangePercent'])
                    last_price = float(data['lastPrice'])
                    results[symbol] = {
                        'price': last_price,
                        'change_24h': price_change_percent
                    }
                except (KeyError, ValueError) as e:
                    print(f"Error parsing data for {symbol}: {e} - Data: {data}")
                    results[symbol] = None  # Store None for failed parsing
            else:
                results[symbol] = None   #Store none for failed request.

    return results


async def get_kucoin_tickers(symbols):
    """Fetches ticker data for multiple symbols from the KuCoin API."""
    exchange_url = "https://api.kucoin.com/api/v1/market/stats?symbol="
    results = {}
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_ticker_data(session, symbol, exchange_url) for symbol in symbols]
        tickers_data = await asyncio.gather(*tasks)
    for symbol, data in tickers_data:
        if data and data.get("code") == "200000" and data.get("data"): #kucoin api return code
            try:
                price_change_percent = float(data['data']['changeRate']) * 100
                last_price = float(data['data']['last'])
                results[symbol] = {
                    'price': last_price,
                    'change_24h': price_change_percent
                }
            except (KeyError, ValueError) as e:
                 print(f"Error parsing data for {symbol}: {e} - Data: {data}")
                 results[symbol] = None
        else:
             results[symbol] = None
    return results




async def get_okx_tickers(symbols):
    """Fetches ticker data from the OKX exchange."""
    exchange_url = "https://www.okx.com/api/v5/market/ticker?instId="
    results = {}
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_ticker_data(session, symbol.replace("USDT", "-USDT"), exchange_url) for symbol in symbols] #need to convert symbol to the format OKX uses
        tickers_data = await asyncio.gather(*tasks)

        for symbol, data in tickers_data:
            original_symbol = symbol.replace("-USDT", "USDT")  # Convert back to original symbol
            if data and data.get("code") == "0" and data.get("data"): #okx return "0" as success
                try:
                    ticker_data = data["data"][0]  # OKX returns data in a list
                    price_change_percent = float(ticker_data['sodUtc8'])
                    last_price = float(ticker_data['last'])
                    results[original_symbol] = {
                        'price': last_price,
                        'change_24h': price_change_percent
                    }
                except (KeyError, ValueError) as e:
                    print(f"Error parsing data for {original_symbol}: {e} - Data: {data}")
                    results[original_symbol] = None  # Store None for failed parsing
            else:
                 results[original_symbol] = None   #Store none for failed request.
    return results




async def main():
    """Main function to fetch and print ticker data."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    binance_tickers = await get_binance_tickers(symbols)
    print("Binance Tickers:", binance_tickers)
    # kucoin_tickers = await get_kucoin_tickers(symbols)
    # print("KuCoin Tickers:", kucoin_tickers)
    # okx_tickers = await get_okx_tickers(symbols)
    # print("OKX Tickers", okx_tickers)


if __name__ == "__main__":
    asyncio.run(main())