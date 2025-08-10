import sys
import os

redis_project_path = os.path.join(os.path.dirname(__file__), '..', 'mcp-redis')
sys.path.append(os.path.abspath(redis_project_path))

from src.common.connection import RedisConnectionManager
from src.common.config import REDIS_CFG, set_redis_config_from_cli
from src.tools.redis_query_engine import create_vector_index_hash, vector_search_hash, get_index_info
from src.tools.hash import hset, hgetall, set_vector_in_hash
from src.tools.misc import scan_all_keys
from redis_function_mappings import function_mappings
from src.tools.hash import hset, hgetall, hget, hdel, hexists, set_vector_in_hash, get_vector_from_hash
from src.tools.json import json_set, json_get, json_del
from src.tools.list import lpush, rpush, lpop, rpop, lrange, llen
from src.tools.misc import scan_all_keys, scan_keys, delete, type, expire, rename
from src.tools.server_management import dbsize, info, client_list
from src.tools.pub_sub import publish, subscribe, unsubscribe
from src.tools.redis_query_engine import create_vector_index_hash, vector_search_hash, get_index_info, get_indexes, get_indexed_keys_number
from src.tools.set import sadd, srem, smembers
from src.tools.sorted_set import zadd, zrange, zrem
from src.tools.stream import xadd, xrange, xdel
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
import json
import numpy as np
import os
import io
import uuid
import openai
from redis.exceptions import RedisError
import httpx # A modern, async-friendly HTTP client for Python
from dotenv import load_dotenv
import asyncio # New import for handling synchronous functions

# --- Load environment variables from a .env file ---
load_dotenv()

# --- Mocking the Redis MCP tools based on user's provided code ---
from src.common.connection import RedisConnectionManager
from src.common.config import set_redis_config_from_cli
from src.tools.redis_query_engine import create_vector_index_hash

# --- OpenAI Client Initialization ---
class OpenAIClientManager:
    """Manages the OpenAI client and API calls."""
    def __init__(self):
        self.openai_client = None
        self.use_azure = False
        self.embedding_deployment = "text-embedding-ada-002"
        self.dimension = 1536
        
        if os.getenv("AZURE_OPENAI_API_KEY"):
            self.openai_client = openai.AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            )
            self.use_azure = True
            self.embedding_deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
        elif os.getenv("OPENAI_API_KEY"):
            self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.use_azure = False
            self.embedding_deployment = "text-embedding-ada-002"
        else:
            raise ValueError("No OpenAI or Azure OpenAI API key found in environment variables.")

    def create_embedding(self, text: str) -> List[float]:
        """Generate a single embedding for a given text."""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_deployment,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error creating embedding: {str(e)}")
            return []

# --- FastAPI App Initialization ---
app = FastAPI(
    title="JSON Embedding Service",
    description="An API to embed JSON bodies and store them in a Redis Vector Database."
)

# --- Redis Connection Setup (using the user's provided MCP style) ---
def setup_redis_connection():
    try:
        redis_config = {}
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            from src.common.config import parse_redis_uri
            redis_config = parse_redis_uri(redis_url)
        else:
            redis_config = {
                'host': os.getenv('REDIS_HOST', 'localhost'),
                'port': int(os.getenv('REDIS_PORT', 6379)),
                'password': os.getenv('REDIS_PASSWORD', None),
                'username': os.getenv('REDIS_USERNAME'),
                'ssl': os.getenv('REDIS_SSL', 'false').lower() == 'true',
                'db': int(os.getenv('REDIS_DB', 0))
            }
        set_redis_config_from_cli(redis_config)
        conn = RedisConnectionManager.get_connection()
        conn.ping()
        return conn
    except Exception as e:
        print(f"Error connecting to Redis: {str(e)}")
        return None

# Perform the connection setup at startup
redis_conn = setup_redis_connection()

# --- FastAPI Endpoint ---
@app.post("/upload_json/")
async def upload_json_and_embed(json_data: Dict[str, Any]):
    """
    Accepts a raw JSON body, generates a vector embedding, and stores it in Redis using MCP tools.
    """
    if redis_conn is None:
        raise HTTPException(status_code=503, detail="Redis connection not established.")

    if not isinstance(json_data, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON format. Expected a JSON object.")
    
    # Instantiate the OpenAI client
    try:
        openai_manager = OpenAIClientManager()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Redis configuration
    INDEX_NAME = 'vector_index'
    KEY_PREFIX = 'doc:'
    VECTOR_FIELD = "vector"

    # Create index if it doesn't exist using the MCP tool
    result = await create_vector_index_hash(
        index_name=INDEX_NAME,
        prefix=KEY_PREFIX,
        vector_field=VECTOR_FIELD,
        dim=openai_manager.dimension,
        distance_metric="COSINE"
    )
    print(f"Index creation status: {result}")

    # Use the entire JSON as a single chunk
    # doc_id = json_data.get("product_id", str(uuid.uuid4()))
    metadata = {}
    doc_id = metadata.get("doc_id", str(uuid.uuid4()))
    
    chunk = json.dumps(json_data)
    print(f"Processing JSON object with doc_id: {doc_id}")
    
    # Correctly call the synchronous embedding function in an async context
    embedding = await asyncio.to_thread(openai_manager.create_embedding, chunk)
    
    if not embedding:
        raise HTTPException(status_code=500, detail="Failed to create embedding for the JSON object.")
    
    # Create the doc_key for the single chunk (chunk_id = 0)
    try:
     doc_key = f"doc:{doc_id}:chunk:0"
     chunk_metadata = {**metadata, "doc_id": doc_id, "chunk_id": 0, "content": chunk}
    # try:
    #     # Store the metadata and content of the chunk in the Redis hash
    #     chunk_metadata = {
    #         "doc_id": doc_id,
    #         "chunk_id": "0",
    #         "content": chunk
    #     }

        # Store each key-value pair of the metadata in the Redis hash
     for key, value in chunk_metadata.items():
        await hset(doc_key, key, str(value))
        
        # Store the vector using the set_vector_in_hash function
        vector_stored = await set_vector_in_hash(doc_key, embedding, VECTOR_FIELD)
        if not vector_stored:
            raise HTTPException(status_code=500, detail="Failed to store vector in Redis.")
        
        print(f"Successfully stored JSON object with key: {doc_key}")
        
    except RedisError as e:
        print(f"Error storing JSON object: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to store JSON data in Redis.")

    return JSONResponse(content={"message": f"Successfully processed and stored product {doc_id}"})



           
            
            
            
          