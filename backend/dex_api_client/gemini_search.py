"""

curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=GEMINI_API_KEY" \
-H 'Content-Type: application/json' \
-X POST \
-d '{
  "contents": [{
    "parts":[{"text": "Explain how AI works"}]
    }]
   }'
"""
import asyncio

from dotenv import load_dotenv, find_dotenv
import aiohttp

from google import genai
from google.genai import types
import os

load_dotenv(find_dotenv())


# build a function for the API call
async def generate_content(text):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + os.getenv(
        "GEMINI_API_KEY")
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "contents": [{
            "parts": [{"text": text}]
        }]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            return await response.json()


def google_ai_search(input_text: str):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=input_text,
        config=types.GenerateContentConfig(
            tools=[types.Tool(
                google_search=types.GoogleSearchRetrieval(
                    dynamic_retrieval_config=types.DynamicRetrievalConfig(
                        dynamic_threshold=0.1))
            )]
        )
    )
    # use ai again to understand the response and give a concise answer
    res_1 = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=str(response),
        # config=types.GenerateContentConfig(
        #     tools=[types.Tool(
        #         google_search=types.GoogleSearchRetrieval(
        #             dynamic_retrieval_config=types.DynamicRetrievalConfig(
        #                 dynamic_threshold=0.1))
        #     )]
        # )
    )
    """
    candidates=[Candidate(content=Content(parts=[Part(video_metadata=None, thought=None, code_execution_result=None, executable_code=None, file_data=None, function_call=None, function_response=None, inline_data=None, text="The model's response indicates that it cannot access or interact with content from URLs. Therefore, it cannot fulfill the request to identify the top 5 tokens from the provided link.\n")], role='model'), citation_metadata=None, finish_message=None, token_count=None, avg_logprobs=-0.2322765556541649, finish_reason='STOP', grounding_metadata=None, index=None, logprobs_result=None, safety_ratings=None)] model_version='gemini-2.0-flash' prompt_feedback=None usage_metadata=GenerateContentResponseUsageMetadata(cached_content_token_count=None, candidates_token_count=37, prompt_token_count=276, total_token_count=313) automatic_function_calling_history=[] parsed=None
    """
    # make the response readable in the console like a human
    res_1 = str(res_1).replace("candidates", "\nCandidates").replace("model_version", "\nModel Version").replace(
        "prompt_feedback", "\nPrompt Feedback").replace("usage_metadata", "\nUsage Metadata").replace(
        "automatic_function_calling_history", "\nAutomatic Function Calling History").replace("parsed", "\nParsed")

    print(res_1)
    return res_1


# call the function


async def main():
    response = await generate_content("search 'https://gmgn.ai/?chain=base' and give me top 5 of token")
    print(response)


google_ai_search("search for top 5 hottest token on base chain, give me their contract address and go to "
                 "'https://tokensniffer.com/token/eth/0x2726ba1eacdeebeb328f0cfbccf895193bea29cf?__cf_chl_tk=aK7zJ_m24Adoj6g3iOQaE6969V6phpB9DBGfrvTO1G4-1741111775-1.0.1.1-uy0Qk3n2Oj_n0wamdV9Ut_BFaBzuaf8I_YQPA9n7lxs' this url just a sample, you should use real chain id and contract address and search for the security of the contract, and give me their price against usd")
# asyncio.run(main())
