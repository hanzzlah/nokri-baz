import os
import time
import cohere
from dotenv import load_dotenv

load_dotenv()

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Fetches 1024-dimensional embeddings using Cohere's free Trial API.
    """
    if not texts:
        return []

    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        raise ValueError("COHERE_API_KEY is missing from environment variables.")

    co = cohere.Client(api_key)
    
    batch_size = 50
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = co.embed(
                    texts=batch,
                    model="embed-english-v3.0",
                    input_type="search_document"
                )
                
                all_embeddings.extend(response.embeddings)
                
                time.sleep(1)
                break
                
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "rate limit" in error_msg:
                    wait_time = 2 ** attempt + 2
                    print(f"[Cohere API] Rate limited. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"[ERROR] Failed to fetch embeddings: {e}")
                    raise e
        else:
            raise Exception("Failed to fetch embeddings from Cohere after maximum retries.")

    return all_embeddings