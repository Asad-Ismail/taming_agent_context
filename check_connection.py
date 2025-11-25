import os
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv, find_dotenv
from pprint import pprint

# Load environment variables
load_dotenv(find_dotenv())

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
api_base = os.getenv("OPENAI_API_BASE")

client = AsyncOpenAI(api_key=api_key, base_url=api_base)

# Test the connection
completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "Who won the world series in 2020?"
        }
    ]
)

print("Connection successful!")
print(f"Model: {completion.model}")
print(f"Response: {completion.choices[0].message.content}")
