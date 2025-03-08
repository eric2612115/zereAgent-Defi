import time
from pprint import pprint

import aiohttp
from typing import List, Dict, Optional

class UniswapV2Client:
    BASE_URL = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2"

    def __init__(self):
        self.session = aiohttp.ClientSession()

    async def _send_request(self, query: str, variables: Dict = None) -> Dict:
        """ 发送 GraphQL 请求 """
        async with self.session.post(self.BASE_URL, json={"query": query, "variables": variables}) as response:
            return await response.json()

    async def get_all_tradable_tokens(self) -> List[str]:
        """ 获取所有 Uniswap V2 可交易代币 """
        query = '''
        query pairs($skip: Int!) {
          pairs(first: 1000, skip: $skip, orderBy: reserveUSD, orderDirection: desc) {
            token0 { id symbol }
            token1 { id symbol }
          }
        }
        '''

        all_tokens = set()
        skip = 0

        while True:
            result = await self._send_request(query, {"skip": skip})
            pairs = result.get("data", {}).get("pairs", [])

            if not pairs:
                break

            for pair in pairs:
                all_tokens.add(pair["token0"]["id"])
                all_tokens.add(pair["token1"]["id"])

            skip += 1000
            time.sleep(1)  # 避免请求过快

        return list(all_tokens)

    async def find_pairs_by_token(self, token_address: str) -> List[Dict]:
        """ 查询包含特定代币的所有交易对 """
        token_address = token_address.lower()
        query = '''
        query tokenPairs($token: String!) {
          pairs(where: { 
            or: [
              { token0: $token },
              { token1: $token }
            ] 
          }) {
            id
            token0 { id symbol }
            token1 { id symbol }
          }
        }
        '''

        result = await self._send_request(query, {"token": token_address})
        return result.get("data", {}).get("pairs", [])

    async def is_token_tradable(self, token_address: str) -> bool:
        """ 检查某个代币是否可以交易 """
        pairs = await self.find_pairs_by_token(token_address)
        return len(pairs) > 0

    async def close(self):
        """ 关闭 session 资源 """
        await self.session.close()

import asyncio

async def main():
    client = UniswapV2Client()

    # 1️⃣ 获取 Uniswap V2 上的所有可交易代币
    all_tokens = await client.get_all_tradable_tokens()
    print(f"✅ 找到 {len(all_tokens)} 个可交易代币，前 5 个：", all_tokens[:5])

    # 2️⃣ 查询特定代币的交易对（例如 DAI）
    token_address = "0x6b175474e89094c44da98b954eedeac495271d0f"  # DAI 合约地址
    pairs = await client.find_pairs_by_token(token_address)
    print(f"✅ DAI 参与的交易对数量: {len(pairs)}")

    # 3️⃣ 检查某个代币是否可以交易
    is_tradable = await client.is_token_tradable(token_address)
    print(f"✅ DAI 是否可交易: {'是' if is_tradable else '否'}")

    await client.close()  # 关闭 HTTP session

# asyncio.run(main())
result=  {'0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b': {'symbol': 'VIRTUAL', 'totalLiquidity': '26054744.597066904096188239', 'tradeVolumeUSD': '1347906956.382663872305170356923525', 'Price': '1.125061299479751985030091538967279', 'security': {'Risks': {'security_vulnerabilities': 'The token is mintable and has a hidden owner, which raises concerns about potential manipulation or rug pulls. The presence of a high number of holders (607,897) may indicate a risk of market volatility due to large sell-offs.', 'regulatory_concerns': 'As a cryptocurrency, it may face scrutiny from regulatory bodies, especially if it does not comply with local laws regarding securities and anti-money laundering.', 'market_volatility': 'The liquidity across various DEXs is relatively low, which can lead to significant price fluctuations and slippage during trading.'}, 'Potential Growth': {'future_adoption': 'The token has a large holder base, which could indicate potential for community-driven growth. However, the lack of clear partnerships or use cases may hinder broader adoption.', 'partnerships': 'No significant partnerships or collaborations have been reported, which could limit its growth potential in competitive markets.', 'competitive_positioning': 'The token operates in a crowded market with many alternatives, making it challenging to establish a unique value proposition.'}, 'Conclusion': {'Security Score': '4', 'Profit Potential': '5', 'Conclusion': 'In the short term, the token may experience volatility due to its liquidity and holder distribution. Long-term prospects are uncertain without clear use cases or partnerships, but community interest could drive some growth.'}}}, '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913': {'symbol': 'USDC', 'totalLiquidity': '8937465.471616', 'tradeVolumeUSD': '938525832.5478507830583625910779652', 'Price': '0.8888404573710050141909697719841803'}}
pprint(result)
securitry_text = ""
for key, value in result.items():
    securitry_text += f"Token: {key}\n"
    for k, v in value.items():
        if k == "security":
            securitry_text += f"Security:\n"
            for k1, v1 in v.items():
                if k1 == "Risks":
                    securitry_text += " - Risks:\n"
                    for k2, v2 in v1.items():
                        securitry_text += f"   - {k2}: {v2}\n"
                elif k1 == "Potential Growth":
                    securitry_text += " - Potential Growth:\n"
                    for k2, v2 in v1.items():
                        securitry_text += f"   - {k2}: {v2}\n"
                elif k1 == "Conclusion":
                    securitry_text += " - Conclusion:\n"
                    for k2, v2 in v1.items():
                        securitry_text += f"   - {k2}: {v2}\n"

        else:
            # if v is int or float, round to 8 decimal places
            try:
                v = float(v)
            except:
                pass
            if isinstance(v, (int, float)):
                v = round(v, 8)
            securitry_text += f"{k}: {v}\n"

print(securitry_text)