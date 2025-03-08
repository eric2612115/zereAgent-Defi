from pprint import pprint
from typing import List

import aiohttp
import asyncio
from dotenv import load_dotenv, find_dotenv


class CaveClient:
    # https://interface.carv.io/ai-agent-backend/news
    BASE_URL = "https://interface.carv.io"
    AGENT_URL = "/ai-agent-backend"
    NEWS_URL = "/news"

    def __init__(self, api_key: str):
        self.session: aiohttp.ClientSession = None
        self.api_key = api_key
        self.header = {
            "Content-Type": "application/json",
            "Authorization": self.api_key
        }

    async def initialize(self):
        """Initializes the client."""
        self.session = aiohttp.ClientSession()

    async def close(self):
        """Closes the client session."""
        await self.session.close()

    async def fetch_news_data(self):
        """Fetches news data from the Cave API."""
        url = f"{self.BASE_URL}{self.AGENT_URL}{self.NEWS_URL}"
        async with self.session.get(url, headers=self.header) as response:
            return await response.json()

    async def fetch_token_info_price(self, token: str):
        """Fetches token info price from the Cave API."""
        """curl -X GET "https://interface.carv.io/ai-agent-backend/token_info?ticker=aave" \
      -H "Content-Type: application/json" \
      -H "Authorization: <YOUR_AUTH_TOKEN>"""
        url = f"{self.BASE_URL}{self.AGENT_URL}/token_info?ticker={token}"
        async with self.session.get(url, headers=self.header) as response:
            return await response.json()

    async def fetch_on_chain_data_by_llm(self, question_string: str):
        """
        curl -X POST https://interface.carv.io/ai-agent-backend/sql_query_by_llm \
     -H "Content-Type: application/json" \
     -H "Authorization: <YOUR_AUTH_TOKEN>" \
     -d '{"question":"What's the most active address on Ethereum during the last 24 hours?"}'
        :param token:
        :return:
        """
        url = f"{self.BASE_URL}{self.AGENT_URL}/sql_query_by_llm"
        data = {
            "question": question_string
        }
        async with self.session.post(url, headers=self.header, json=data) as response:
            return await response.json()

    async def fetch_on_chain_data_by_sql_query(self, sql_content: str):
        """
        curl -X POST https://interface.carv.io/ai-agent-backend/sql_query \
     -H "Content-Type: application/json" \
     -H "Authorization: <YOUR_AUTH_TOKEN>" \
     -d '{"question":"What's the most active address on Ethereum during the last 24 hours?"}'
        :param token:
        :return:
        """
        url = f"{self.BASE_URL}{self.AGENT_URL}/sql_query"
        data = {
            "sql_content": sql_content
        }
        async with self.session.post(url, headers=self.header, json=data) as response:
            return await response.json()

    def process_news_data(self, data: list[dict]):
        """Processes the news data."""
        """
        {'card_text': 'A US crypto reserve could offer “cover” to institutional '
              'investors, like pension funds, which have been hesitant to '
              'invest in crypto.',
 'title': 'Reaction to Trump’s crypto reserve: ‘Short-term optimism, long-term '
          'caution’',
 'url': 'https://cointelegraph.com/reaction-trump-crypto-reserve-short-optimism-long-caution'}
 """
        # correct url is: https://cointelegraph.com/news/el-salvador-20-how-kyrgyzstans-blockchain-strategy-stands-apart
        # print(data)
        if "code" in data:
            if data['code'] != 0:
                return data
            else:
                process_data = data['data']['infos']
        else:
            process_data = data
        news_data_set = []
        for d in process_data:
            # split https:// and split the 1st / will give the real url prefix
            real_url_prefix = d['url'].split("https://")[1].split("/")[0]
            # if the url is not from cointelegraph, skip

            if real_url_prefix != "cointelegraph.com":
                real_url = d['url']
                continue
            else:
                sub_url = d['url'].split("https://cointelegraph.com")[1]
                real_url = f"https://cointelegraph.com/news{sub_url}"
            news_data_set.append({
                "title": d['title'],
                "url": real_url,
                "content": d['card_text']
            })

        return news_data_set

async def get_hourly_trading_volume(client, addresses: List[str]):
    """
    查询指定地址列表在 Base 链上一小时内的交易量。

    Args:
        client: CaveClient 实例。
        addresses: 要查询的地址列表。

    Returns:
        一个字典，键为地址，值为该地址在一小时内的交易量（以 ETH 为单位，如果 value 字段的单位是 ETH）。
        如果查询出错或没有数据，返回空字典。
    """

    # 将地址列表转换为 SQL IN 子句的字符串
    addresses_str = "', '".join(addresses)
    addresses_str = f"'{addresses_str}'"

    sql_query = f"""
    SELECT
        to_address AS address,
        SUM(value) AS trading_volume
    FROM
        sonarx_base.transactions
    WHERE
        datetime >= NOW() - INTERVAL '1' HOUR
        AND (to_address IN ({addresses_str}) OR from_address IN ({addresses_str}))
    GROUP BY
        to_address
    UNION ALL
    SELECT
        from_address AS address,
        SUM(value) AS trading_volume
    FROM
        sonarx_base.transactions
    WHERE
        datetime >= NOW() - INTERVAL '1' HOUR
        AND (to_address IN ({addresses_str}) OR from_address IN ({addresses_str}))
    GROUP BY
        from_address;
    """

    response = await client.fetch_on_chain_data_by_sql_query(sql_query)

    if response and response.get("code") == 0:
        data = response.get("data")
        if data:
            column_infos = data.get("column_infos")
            rows = data.get("rows")
            trading_volumes = {}
            if column_infos and rows:
                address_index = column_infos.index("address")
                volume_index = column_infos.index("trading_volume")

                for row in rows:
                    items = row.get("items")
                    if items:
                        address = items[address_index]
                        volume = items[volume_index]
                        trading_volumes[address] = trading_volumes.get(address, 0) + volume
            return trading_volumes
        else:
            print("No data returned.")
            return {}
    else:
        print(f"Error fetching data: {response.get('error')}")
        return {}
async def main():
    mock_news = [

        {'card_text': 'A US crypto reserve could offer “cover” to institutional '
                      'investors, like pension funds, which have been hesitant to '
                      'invest in crypto.',
         'title': 'Reaction to Trump’s crypto reserve: ‘Short-term optimism, long-term '
                  'caution’',
         'url': 'https://cointelegraph.com/reaction-trump-crypto-reserve-short-optimism-long-caution'},
        {'card_text': 'The new crypto reserve could be a way for the US to hedge '
                      'against the rise of China’s digital yuan.',
         'title': 'US crypto reserve could be a hedge against China’s digital yuan',
         'url': 'https://cointelegraph.com/us-crypto-reserve-hedge-against-china-digital-yuan'},
    ]

    api_key = "22f918f4-1677-4db7-885d-ef657c2683b9"
    client = CaveClient(api_key)
    await client.initialize()
    # news_data = client.process_news_data(await client.fetch_news_data())
    # pprint(news_data)
    # print(await client.fetch_token_info_price("SKITTEN"))

    # q1="I want to buy ADA on ETH chain"
    # q2="What are the news on Base chain today?"
    # q3="What's the most active address on Ethereum during the last 24 hours?"
    # q4="what is the yield of AAVE?"
    # q5 = "What are the token name, contract address and trading volume on the Base chain in UNISWAP by trading volume in the last 24 hours?"
    # q5 = "what's the trading volume of 0x937a1cfaf0a3d9f5dc4d0927f72ee5e3e5f82a00 in last 1 hour?"
    # print(await client.fetch_on_chain_data_by_llm(q5))

    qqq = {"sql_content":"WITH address_activity AS (SELECT from_address AS address, COUNT(*) AS tx_count FROM eth.transactions WHERE date_parse(date, '\''%Y-%m-%d'\'') >= date_add('\''month'\'', -3, current_date) GROUP BY from_address UNION ALL SELECT to_address AS address, COUNT(*) AS tx_count FROM eth.transactions WHERE date_parse(date, '\''%Y-%m-%d'\'') >= date_add('\''month'\'', -3, current_date) GROUP BY to_address) SELECT address, SUM(tx_count) AS total_transactions FROM address_activity GROUP BY address ORDER BY total_transactions DESC LIMIT 1;"}
    # await client.close()

    print(await client.fetch_on_chain_data_by_sql_query(qqq['sql_content']))
    # addresses = [
    #     "0x937a1cfaf0a3d9f5dc4d0927f72ee5e3e5f82a00",
    #     "0x2531ec1720e5d1bc82052585271d4be3f43e392f",
    #     "0x937a1cfaf0a3d9f5dc4d0927f72ee5e3e5f82a00",  # 重复地址，测试去重
    #     "0x88144b9ea94ff714147573b98165d2aca90efb11",
    #     "0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b",
    # ]
    #
    # trading_volumes = await get_hourly_trading_volume(client, addresses)
    # await client.close()
    #
    # if trading_volumes:
    #     print("Hourly Trading Volumes (Base Chain):")
    #     for address, volume in trading_volumes.items():
    #         print(f"  - {address}: {volume}")
    # else:
    #     print("Could not retrieve trading volumes.")

if __name__ == "__main__":
    load_dotenv(find_dotenv())
    asyncio.run(main())
