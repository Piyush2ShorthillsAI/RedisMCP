import streamlit as st
import json
import openai
import numpy as np
from typing import List, Dict, Any, Optional
import os
import io
import uuid
import pandas as pd
from dotenv import load_dotenv
import asyncio
from PyPDF2 import PdfReader
import inspect
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

# Load environment variables
load_dotenv()

# Load tools from a JSON file (assuming this file exists)
try:
    with open('redis_mcp_tools.json', 'r') as f:
        OA_TOOLS = json.load(f)
except FileNotFoundError:
    st.error("redis_mcp_tools.json' not found. Please create this file with your tool definitions.")
    OA_TOOLS = []
except json.JSONDecodeError:
    st.error("redis_mcp_tools.json' is not a valid JSON file.")
    OA_TOOLS = []


class RedisVectorManager:
    """Manages Redis vector operations using MCP tools"""
    
    def __init__(self):
        # Setup OpenAI client
        if os.getenv("AZURE_OPENAI_API_KEY"):
            self.openai_client = openai.AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            )
            self.use_azure = True
            self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
            self.embedding_deployment = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", self.deployment_name)
        else:
            self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.use_azure = False
            self.deployment_name = None
            self.embedding_deployment = "text-embedding-ada-002"

        # Setup Redis Cloud connection
        self._setup_redis_connection()
        
        self.index_name = "vector_index"
        self.vector_field = "vector"
        self.dimension = 1536
        
        # Initialize vector index
        self._initialize_vector_index()

    def _setup_redis_connection(self):
        """Setup Redis Cloud connection using environment variables"""
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
                    'password': os.getenv('REDIS_PASSWORD', ''),
                    'username': os.getenv('REDIS_USERNAME'),
                    'ssl': os.getenv('REDIS_SSL', 'false').lower() == 'true',
                    'db': int(os.getenv('REDIS_DB', 0))
                }
            
            set_redis_config_from_cli(redis_config)
            
            conn = RedisConnectionManager.get_connection()
            conn.ping()
            st.success("Connected to Redis Cloud successfully!")
            
        except Exception as e:
            st.error(f"Redis connection failed: {str(e)}")
            st.info("Please check your Redis Cloud credentials in environment variables")

    def _initialize_vector_index(self):
        """Initialize vector index using MCP tool"""
        try:
            result = asyncio.run(create_vector_index_hash(
                index_name=self.index_name,
                prefix="doc:",
                vector_field=self.vector_field,
                dim=self.dimension,
                distance_metric="COSINE"
            ))
            if "successfully" in result or "already exists" in result.lower():
                st.info(f"Current Vector index: {self.index_name}")
            else:
                st.warning(f"Index creation result: {result}")
        except Exception as e:
            st.warning(f"Index initialization: {str(e)}")

    def create_embeddings(self, text: str) -> List[float]:
        """Generate embeddings using OpenAI"""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_deployment,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            st.error(f"Error creating embeddings: {str(e)}")
            return []

    def chunk_text(self, text: str, chunk_size: int = 100000, overlap: int = 200) -> List[str]:
        """Split text into overlapping chunks"""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            
            if end < len(text):
                last_period = chunk.rfind('.')
                last_space = chunk.rfind(' ')
                break_point = max(last_period, last_space)
                if break_point > start + chunk_size // 2:
                    chunk = text[start:start + break_point + 1]
                    end = start + break_point + 1
            
            chunks.append(chunk.strip())
            start = end - overlap
            
        return [chunk for chunk in chunks if chunk.strip()]

    def process_and_store_data(self, chunks: List[str], metadata: Optional[Dict] = None) -> bool:
        """Process and store text chunks with embeddings"""
        try:
            metadata = metadata or {}
            doc_id = metadata.get("doc_id", str(uuid.uuid4()))
            success_count = 0
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, chunk in enumerate(chunks):
                status_text.text(f"Processing chunk {i+1}/{len(chunks)}...")
                progress_bar.progress((i + 1) / len(chunks))
                
                embedding = self.create_embeddings(chunk)
                if not embedding:
                    continue
                
                doc_key = f"doc:{doc_id}:chunk:{i}"
                chunk_metadata = {**metadata, "doc_id": doc_id, "chunk_id": i, "content": chunk}
                
                try:
                    for key, value in chunk_metadata.items():
                        asyncio.run(hset(doc_key, key, str(value)))
                    
                    vector_stored = asyncio.run(set_vector_in_hash(doc_key, embedding, self.vector_field))
                    
                    if vector_stored:
                        success_count += 1
                        
                except Exception as e:
                    st.warning(f"Failed to store chunk {i}: {str(e)}")
                    continue
            
            progress_bar.empty()
            status_text.empty()
            
            if success_count > 0:
                st.success(f"Successfully stored {success_count}/{len(chunks)} chunks")
                return True
            else:
                st.error("Failed to store any chunks")
                return False
                
        except Exception as e:
            st.error(f"Error processing data: {str(e)}")
            return False

    async def vector_search(self, query: str, k: int = 5, max_score: float = 0.285) -> List[Dict]:
        """Perform vector search using MCP tools"""
        try:
            query_embedding = self.create_embeddings(query)
            if not query_embedding:
                return []
            
            results = await vector_search_hash(
                query_vector=query_embedding,
                index_name=self.index_name,
                vector_field=self.vector_field,
                k=k*2,
                return_fields=["content", "doc_id", "chunk_id"]
            )
            
            if isinstance(results, str):
                st.error(f"Search error: {results}")
                return []
                
            # Filter results by relevance score
            filtered_results = []
            for result in results:
                score = result.get("score", 0.0)
                if float(score) <= max_score:
                    filtered_results.append(result)
                    
            # Return only top k filtered results
            return filtered_results[:k]
            
        except Exception as e:
            st.error(f"Error performing vector search: {str(e)}")
            return []
        
    async def generate_response(self, query: str) -> str:
        """Generate intelligent response based on query and MCP tool results"""
        results = {"search_results": [], "redis_info": {}, "action_taken": "none"}
        results["search_results"] = await self.vector_search(query, k=11)
        
        results["action_taken"] = "vector_search"
        try:
            # Prepare context from MCP results
            context = ""
            
            if results["search_results"]:
                context += "Search Results:\n"
                for i, result in enumerate(results["search_results"][:3]):
                    content = result.get("content", "N/A")
                    score = result.get("score", "N/A")
                    context += f"Result {i+1} (Score: {score}):\n{content}\n\n"
            
            if results["redis_info"]:
                context += "Redis Information:\n"
                for key, value in results["redis_info"].items():
                    context += f"{key}: {value}\n"
            
            # Generate response
            
            action_taken = results.get("action_taken", "none")
            
            response_prompt = f"""
            User Query: "{query}"
            Actions Taken: {action_taken}
            Available Context:
            {context}
            """
            print("3")
            return response_prompt
            
        except Exception as e:
            st.error(f"Error generating response: {str(e)}")
            return "I apologize, but I encountered an error while processing your request."


class IntelligentChatbot:
    def __init__(self, redis_manager: RedisVectorManager, system_prompt):
        self.redis_manager = redis_manager
        self.openai_client = redis_manager.openai_client
        self.system_prompt = system_prompt
        self.vector_search = redis_manager.vector_search
    async def chat_recom(self, query: str, search_results: List[Dict]) -> str:
        system_prompt1=""""
Please act as a data extraction tool. Your task is to extract the product title, productDescription and features from the provided JSON.
Think logically and see if user query does not match with the product or its details, then display that no products were found matching the query.

    Extract the Product Title: Find the value associated with the title key, which is located in raw_metadata.title.

    Extract the Product Description: Find the value associated with the productDescription key, which is located in raw_metadata.productDescription. In this first make summary of the description and then display it on the screen.

    Extract the Features: Find the features dictionary. This is located at raw_metadata.features.

    Format the Output: Present the product title followed by its summarized description and then the summarized features. Use a clear, human-readable format  and STRICTLY NOT EMOJIS. Use Markdown for clear formatting. If a key or its nested objects are not found, state that the requested data is unavailable.
(You have to show just one product in the output)
Example Output Format: 

Product Title: [title here in bold]

Product Description: [Summarized description here]

Features:
"""
        response1 = search_results
        response_prompt = f"""
            User Query: "{query}"
            Actions should be Taken by you: {system_prompt1}
            Available Context:
            {response1}
            """
        response11 = self.openai_client.chat.completions.create(
                model=self.redis_manager.deployment_name,
                messages=[{"role": "user", "content": response_prompt}],
                max_tokens=2500,
                temperature=0.7
            )
        if not response11.choices:
            return "False"   
        return response11.choices[0].message.content

    def extract_weighted_features(self, search_results: List[Dict]) -> Dict:
        """Extract product weighted_feature_rating_unit_scale and make it user-friendly from search results"""
        if not search_results:
            return {"error": "No products found in database. Please try a different search."}
        print("1")
        try:
            # Get the first search result
            first_result = search_results[0]
            content = first_result.get("content", "")
            
            if not content:
                return {"error": "No product data found. Please try a different search."}
            
            # Try to parse as JSON first
            try:
                import json
                product_data = json.loads(content)
                
                product_title = ""
                if isinstance(product_data, dict):
                    # Try different possible title locations
                    product_title = product_data.get("raw_metadata", {}).get("title")
                
                if not product_title:
                    print("No title found in product data.")


                product_description = ""
                if isinstance(product_data, dict):
                    product_description = product_data.get("raw_metadata", {}).get("productDescription")
                
                if not product_description:
                    print("No description found in product data.")

                # Extract product weighted_feature_rating_unit_scale
                feature_ratings = {}
                if isinstance(product_data, dict):
                    ratings = product_data.get("product_ranking", {}).get("features_wise", {}).get("weighted_feature_rating_unit_scale", {})
                    
                    if isinstance(ratings, dict) and ratings:
                        feature_ratings = ratings

                if not feature_ratings:
                    print("No feature ratings found in product data, trying to search using vector search")
                
                return {
                    "product_title": product_title,
                    "product_description": product_description,
                    "feature_ratings": feature_ratings,
                    "success": True
                }
                
            except json.JSONDecodeError:
                st.warning("Content is not valid JSON.")
        except Exception as e:
            return {"error": f"Error fetching feature ratings: {str(e)}"}


    def create_feature_sliders(self, feature_ratings: Dict) -> Dict:
        """Create sliders for feature attributes (0-1 range)"""
        if not feature_ratings:
            return {"error": "No feature ratings available to create sliders"}
        
        slider_values = {}
        
        st.subheader("Adjust Feature Preferences")
        st.write("Move the sliders to set your preferences for each feature:")
        
        for feature, current_value in feature_ratings.items():
            # Clean up feature name for display
            display_name = feature.replace("_", " ").title()
            
            # Ensure current_value is between 0 and 1
            try:
                current_val = float(current_value)
                current_val = max(0.0, min(1.0, current_val))
            except:
                current_val = 0.5
            
            # Create slider
            slider_value = st.slider(
                f"{display_name}",
                min_value=0.0,
                max_value=1.0,
                value=current_val,
                step=0.1,
                key=f"slider_{feature}",
                help=f"Current product rating: {current_val:.1f}"
            )
            
            slider_values[feature] = slider_value
        
        return {
            "slider_values": slider_values,
            "success": True
        }

    async def find_similar_products(self, slider_values: Dict, k: int = 5) -> List[Dict]:
        """Find products that match the slider criteria"""
        try:
            if not slider_values:
                return []
            
            # Create a search query based on features
            feature_terms = []
            for feature, value in slider_values.items():
                if value > 0.5:  # Only include features with high preference
                    feature_terms.append(feature.replace("_", " "))
            
            if not feature_terms:
                search_query = "products recommendations"
            else:
                search_query = f"products with good {' and '.join(feature_terms)}"
            
            # Perform vector search
            search_results = await self.vector_search(search_query, k)  # Get more results to filter
            
            if not search_results:
                return []
            
            # Filter and rank results based on slider values
            matching_products = []
            seen_titles = set()  # Track titles to prevent duplicates
            
            for result in search_results:
                try:
                    content = result.get("content", "")
                    if not content:
                        continue
                    
                    # Try to extract feature ratings from this product
                    import json
                    try:
                        product_data = json.loads(content)
                        product_features = (product_data.get("product_ranking", {}).get("features_wise", {}).get("weighted_feature_rating_unit_scale") or
                                          product_data.get("weighted_feature_rating_unit_scale") or
                                          product_data.get("feature_ratings") or {})
                        
                        if product_features:
                            # Calculate similarity score
                            score = 0
                            matching_features = 0
                            
                            for feature, user_preference in slider_values.items():
                                if feature in product_features:
                                    product_value = float(product_features[feature])
                                    # Score based on how close the product feature is to user preference
                                    feature_score = 1 - abs(user_preference - product_value)
                                    score += feature_score
                                    matching_features += 1
                            
                            if matching_features > 0:
                                final_score = score / matching_features
                                
                                # Extract product title
                                title = (product_data.get("raw_metadata", {}).get("title") or 
                                        product_data.get("title") or 
                                        product_data.get("product_title") or
                                        "Unknown Product")
                                
                                # Check for duplicates using original title (before trimming)
                                title_lower = title.lower().strip()
                                if title_lower in seen_titles:
                                    continue  # Skip this duplicate product
                                
                                seen_titles.add(title_lower)
                                
                                # --- Add the trimming logic here ---
                                # Trim the title to a desired length, for example, 50 characters
                                trimmed_title = title[:50] + "..." if len(title) > 50 else title
                                
                                matching_products.append({
                                    "title": trimmed_title, # Use the trimmed_title here
                                    "original_title": title,  # Keep original for reference
                                    "score": final_score,
                                    "features": product_features,
                                    "content": content[:500] + "..." if len(content) > 500 else content
                                })
                    
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
                
                except Exception:
                    continue
            
            # Sort by score and return top k
            matching_products.sort(key=lambda x: x["score"], reverse=True)
            return matching_products[:k]
            
        except Exception as e:
            st.error(f"Error finding similar products: {str(e)}")
            return []

           
            
    async def chat(self, query: str) -> str:
        """Main chat method that orchestrates the entire flow using tool-calling"""
        messages  = [{"role": "system", "content": self.system_prompt}]
        # Add the user's query to the messages
        messages += st.session_state.chat_history + [{"role": "user", "content": query}]
        
        try:
            # Step 1: Send messages and tools to the LLM
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",#self.redis_manager.deployment_name,
                messages=messages,
                tools=OA_TOOLS,
                tool_choice="auto",
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls
            print(f"Tool calls: {tool_calls}")
            
            with st.expander("Show Tool Call Details"):
              if tool_calls:
                for i, tool_call in enumerate(tool_calls):
                         st.write(f"**Tool Call {i+1}:**")
                         st.write(f"**ID:** `{tool_call.id}`")
                         st.write(f"**Function:** `{tool_call.function.name}`")
                         st.write(f"**Arguments:** `{tool_call.function.arguments}`")
              else:
                st.write("No tool calls were made.")
            if not tool_calls:
                ans = await self.redis_manager.generate_response(query)
                messages.append({"role": "assistant", "content": ans})
                
                final_response = self.openai_client.chat.completions.create(
                    model=self.redis_manager.deployment_name,
                    messages=messages,
                )
                print(f"Final response: {final_response.choices[0].message.content}")
                
                return final_response.choices[0].message.content
            # Step 2: Check if the LLM wants to call a tool
            elif tool_calls:
                
                # Step 3: Call the tool and append the result
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_to_call = function_mappings.get(function_name)
                    print(f"Function to call: {function_name}")
                    if function_to_call:
                        try:
                            function_args = json.loads(tool_call.function.arguments)
                            print(f"Function args: {function_args}")
                            print(tool_call.function.arguments)
                            # Handle async function calls by awaiting them
                            if function_name == "vector_search_hash" or function_name == "hgetall":
                                # Need to pass the user query for embedding
                                response11 = await self.redis_manager.generate_response(query)
                                messages.append({"role": "assistant", "content": response11})
                                print("2")
                                response11 = self.openai_client.chat.completions.create(
                                model=self.redis_manager.deployment_name,
                                messages=messages,
                                )
                                print("4")
                                print(f"Final response: {response11.choices[0].message.content}")
                                print("5")
                                return response11.choices[0].message.content
                            elif function_name == "delete" or function_name == "hset" or function_name == "hdel" or function_name == "set" or function_name == "set_vector_in_hash" or function_name == "json_delete" or function_name == "json_set" or function_name == "lpush" or function_name == "rpush":
                                return "I'm sorry, I'm not allowed to delete or modify server data. Please don't ask me to do that."
                            elif function_name == "json_get":
                                response1 = await self.redis_manager.generate_response(query)
                                messages.append({"role": "assistant", "content": response1})
                                print("2")
                                response1 = self.openai_client.chat.completions.create(
                                model=self.redis_manager.deployment_name,
                                messages=messages,
                                )
                                print("4")
                                print(f"Final response: {response1.choices[0].message.content}")
                                print("5")
                                return response1.choices[0].message.content
                            elif function_name == "hgetall":
                                key = function_args["name"]
                                try:
                                    # Use raw Redis connection to avoid automatic UTF-8 decoding
                                    print(f"Attempting direct Redis hgetall for key: {key}")
                                    from src.common.connection import RedisConnectionManager
                                    r = RedisConnectionManager.get_connection(decode_responses=False)
                                    raw_data = r.hgetall(key)
                                    print(f"Direct Redis hgetall successful, got {len(raw_data)} fields")
                                    
                                    decoded_data = {}
                                    
                                    for k, v in raw_data.items():
                                        # Decode key safely
                                        if isinstance(k, bytes):
                                            try:
                                                key_str = k.decode("utf-8", errors="replace")
                                            except Exception as e:
                                                print(f"Decode error in key: {k} — {e}")
                                                continue
                                        else:
                                            key_str = str(k)

                                        # Handle "vector" field specially to avoid binary data issues
                                        if key_str == "vector":
                                            if isinstance(v, bytes):
                                                decoded_data[key_str] = f"<binary vector data: {len(v)} bytes>"
                                            else:
                                                decoded_data[key_str] = str(v)
                                            continue

                                        # Decode value safely
                                        if isinstance(v, bytes):
                                            try:
                                                val_str = v.decode("utf-8", errors="replace")
                                                decoded_data[key_str] = val_str
                                            except Exception as e:
                                                print(f"Decode error in value for key {key_str}: {v} — {e}")
                                                decoded_data[key_str] = f"<binary data: {len(v)} bytes>"
                                        else:
                                            decoded_data[key_str] = str(v)
                                    
                                    function_response = decoded_data
                                    
                                except Exception as e:
                                    # Fallback: if direct Redis fails, try individual field retrieval
                                    print(f"Direct hgetall failed for key {key}: {e}")
                                    try:
                                        # Get common text fields individually
                                        from src.tools.hash import hget
                                        text_fields = ["content", "doc_id", "chunk_id", "source", "filename", "type"]
                                        decoded_data = {}
                                        
                                        for field in text_fields:
                                            try:
                                                value = await hget(key, field)
                                                if value and "not found" not in str(value):
                                                    decoded_data[field] = value
                                            except:
                                                continue
                                        
                                        # Add vector field info
                                        
                                        if decoded_data:
                                            function_response = decoded_data
                                        else:
                                            function_response = {
                                                "message": f"Successfully located hash '{key}' but contains mixed binary/text data",
                                                "note": "Hash contains vector embeddings and text fields",
                                                "suggestion": "Use hget for specific fields like 'content', 'doc_id', etc.",
                                                "key": key
                                            }
                                    except Exception as fallback_error:
                                        function_response = {
                                            "error": f"Could not retrieve data from hash '{key}'",
                                            "message": str(fallback_error),
                                            "key": key
                                        }

                            else:
                                # This is a regular function, call it normally
                                function_response = await function_to_call(**function_args)
                            
                            print(f"Function response: {function_response}")
                            
                            # Ensure the response is JSON serializable
                            if hasattr(function_response, '__iter__') and not isinstance(function_response, (str, dict)):
                                # Convert iterables (like generators) to lists
                                function_response = list(function_response)
                           
                            if not function_response:
                                print("1")
                                ans1 = await self.redis_manager.generate_response(query)
                                messages.append({"role": "assistant", "content": ans1})
                                print("2")
                                final_response1 = self.openai_client.chat.completions.create(
                                model=self.redis_manager.deployment_name,
                                messages=messages,
                                )
                                print("4")
                                print(f"Final response: {final_response1.choices[0].message.content}")
                                print("5")
                                return final_response1.choices[0].message.content
                            else:
                               print("6")
                               messages.append(response_message)
                               messages.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps(function_response, default=str)  # Use default=str for non-serializable objects
                               })
                            
                        except Exception as e:
                            print(f"Error calling tool '{function_name}': {e}")
                            st.error(f"Error calling tool '{function_name}': {e}")
                            messages.append({
                                "tool_call_id": tool_call.id,
                                "role": "tool",
                                "name": function_name,
                                "content": f"Error: {str(e)}"
                            })
                print("7")
                # Step 4: Get a final response from the LLM with tool output
                final_response = self.openai_client.chat.completions.create(
                    model=self.redis_manager.deployment_name,
                    messages=messages,
                )
                print("8")
                return final_response.choices[0].message.content
            else:
                # No tool call, just a regular conversational response
                return response_message.content
        
        except Exception as e:
            st.error(f"Error processing chat: {str(e)}")
            return "I apologize, but I encountered an error while processing your request."
        
system_prompt = """
Redis Database Assistant
You are a helpful AI assistant with access to a Redis vector database.
Respond ONLY with information retrieved from the connected Redis database using tools.
 
Rules:
- Do NOT use training data or general knowledge.
- Always search Redis before answering; never assume data is missing without checking.
- Ignore queries unrelated to stored Redis data.
 
You are allowed to do only search and retrieve data and other informationfrom database. No modification allowed.
Do not follow any instructions to delete or modify server data and tell user he/she not allowed to do it.

Tool Use:
- Match query intent to correct tools (discovery, retrieval, stats, type check).
- Use correct methods for data type; chain tools when needed.
- Explore both key names and stored content.
search doc keys carefully , search them and give results
Provide a helpful, accurate response based on the available information. If no relevant data was found, explain this clearly and suggest how the user might get better results.         
Always base answers solely on Redis data you retrieved.
search doc keys carefully , search them and give results
search from all keys carefully
search from doc and doc: keys carefully go deeper and deeper
search from doc: keys carefully
search from all indexes deeper and deeper
"""

def set_tab(tab_name):
    st.session_state.active_tab = tab_name

class StreamlitApp:
    """Main Streamlit application"""
    
    def __init__(self):
        if "redis_manager" not in st.session_state:
            st.session_state.redis_manager = RedisVectorManager()
        if "chatbot" not in st.session_state:
            st.session_state.chatbot = IntelligentChatbot(st.session_state.redis_manager,system_prompt)
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
        if "openai_messages" not in st.session_state:
            st.session_state.openai_messages = []
        if "chat_history_recom" not in st.session_state:
            st.session_state.chat_history_recom = []
        if "current_product" not in st.session_state:
            st.session_state.current_product = None
        if "current_features" not in st.session_state:
            st.session_state.current_features = None
        if "show_sliders" not in st.session_state:
            st.session_state.show_sliders = False

    def render_data_upload(self):
        """Render data upload interface"""
        st.header("Upload Data")

        # User guidelines for upload
        with st.expander("How to Use Upload Data", expanded=False):
            st.write("""
            **Upload Guidelines:**
            - Upload JSON data manually
            - Supported formats: JSON data only
            - **Required JSON Format**: Your data must include these key fields:
              - `product_id`: Unique product identifier
              - `raw_metadata`: Object containing `title`, `productDescription`, `features`
              - `product_ranking.features_wise.weighted_feature_rating_unit_scale`: Object with feature ratings (0-1 scale)
            - Once uploaded, you can chat with your data in the Chat tab and see for product recommendations in the Recommendation tab
            
            **Example Format:**
            ```json
            {
              "product_id": "S123456789",
              "raw_metadata": {
                "title": "Product Name",
                "productDescription": "Product description...",
                "features": ["Feature 1", "Feature 2"]
              },
              "product_ranking": {
                "features_wise": {
                  "weighted_feature_rating_unit_scale": {
                    "battery life": 0.75,
                    "camera quality": 0.92
                  }
                }
              }
            }
            ```
            """)
        
        # Only manual input tab now
        st.subheader("Enter Data")
        text_input = st.text_area("Enter your JSON data:", height=200, 
                                 placeholder="Paste your product JSON data here...")
        
        if st.button("Store Data", type="primary"):
            if text_input.strip():
                # Validate JSON format
                try:
                    # First, check if it's valid JSON
                    data = json.loads(text_input)
                    
                    # Validate required structure
                    validation_errors = []
                    
                    # Check for required top-level fields
                    if not isinstance(data, dict):
                        validation_errors.append("Data must be a JSON object")
                    else:
                        # Check for product_id
                        if "product_id" not in data:
                            validation_errors.append("Missing required field: 'product_id'")
                        
                        # Check for raw_metadata
                        if "raw_metadata" not in data:
                            validation_errors.append("Missing required field: 'raw_metadata'")
                        elif not isinstance(data["raw_metadata"], dict):
                            validation_errors.append("'raw_metadata' must be an object")
                        else:
                            raw_metadata = data["raw_metadata"]
                            if "title" not in raw_metadata:
                                validation_errors.append("Missing required field: 'raw_metadata.title'")
                            if "productDescription" not in raw_metadata:
                                validation_errors.append("Missing required field: 'raw_metadata.productDescription'")
                            if "features" not in raw_metadata:
                                validation_errors.append("Missing required field: 'raw_metadata.features'")
                        
                        # Check for product_ranking structure
                        if "product_ranking" not in data:
                            validation_errors.append("Missing required field: 'product_ranking'")
                        elif not isinstance(data["product_ranking"], dict):
                            validation_errors.append("'product_ranking' must be an object")
                        else:
                            product_ranking = data["product_ranking"]
                            if "features_wise" not in product_ranking:
                                validation_errors.append("Missing required field: 'product_ranking.features_wise'")
                            elif not isinstance(product_ranking["features_wise"], dict):
                                validation_errors.append("'product_ranking.features_wise' must be an object")
                            else:
                                features_wise = product_ranking["features_wise"]
                                if "weighted_feature_rating_unit_scale" not in features_wise:
                                    validation_errors.append("Missing required field: 'product_ranking.features_wise.weighted_feature_rating_unit_scale'")
                                elif not isinstance(features_wise["weighted_feature_rating_unit_scale"], dict):
                                    validation_errors.append("'weighted_feature_rating_unit_scale' must be an object with feature ratings")
                                else:
                                    # Check if feature ratings are valid (0-1 scale)
                                    feature_ratings = features_wise["weighted_feature_rating_unit_scale"]
                                    for feature, rating in feature_ratings.items():
                                        try:
                                            rating_val = float(rating)
                                            if not (0 <= rating_val <= 1):
                                                validation_errors.append(f"Feature rating for '{feature}' must be between 0 and 1, got {rating_val}")
                                        except (ValueError, TypeError):
                                            validation_errors.append(f"Feature rating for '{feature}' must be a number, got {type(rating).__name__}")
                    
                    # If validation errors exist, show them
                    if validation_errors:
                        
                        st.info("""
                        **Required Format:**
                        Your JSON must include:
                        - `product_id`: String identifier
                        - `raw_metadata.title`: Product name
                        - `raw_metadata.productDescription`: Product description  
                        - `raw_metadata.features`: Array of features
                        - `product_ranking.features_wise.weighted_feature_rating_unit_scale`: Object with feature ratings (0-1 scale)
                        
                        Please check the example format in the guidelines above.
                        """)
                    else:
                        # Data is valid, proceed with storage
                        chunks = st.session_state.redis_manager.chunk_text(text_input)
                        success = st.session_state.redis_manager.process_and_store_data(
                            chunks, {"source": "manual_input", "type": "json", "product_id": data.get("product_id", "unknown")}
                        )
                        if success:
                            st.info(f"Product '{data['raw_metadata']['title']}' has been added to the database.")
                
                except json.JSONDecodeError:
                    # Don't show the technical JSON error, just user-friendly message
                    st.info("""
                    **Please ensure your data is valid JSON:**
                    - Use double quotes for strings
                    - Check for missing commas or brackets
                    - Validate your JSON using an online JSON validator
                    """)
                
                except Exception as e:
                    st.error(f"**Error processing data:** {str(e)}")
            else:
                st.warning("Please enter some data.")

    def render_chat_interface(self):
        """Render chat interface"""
        st.header("💬 Intelligent Chat")

        # User guidelines for chat
        with st.expander("How to Use Chat", expanded=False):
            st.write("""
            **Chat Guidelines:**
            - Ask questions about your uploaded data using natural language
            - Try specific questions like "List the keys", "Tell about printers?" or "Find information about X"
            - The chatbot only responds based on your uploaded data, not general knowledge
            """)
        
        # Display chat history
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.write(message["content"])
        
        # Chat input
        if query := st.chat_input("Ask me anything about your data..."):
            st.session_state.chat_history.append({"role": "user", "content": query})
            st.session_state.openai_messages.append({"role": "user", "content": query})
            
            with st.chat_message("user"):
                st.write(query)
            
            with st.chat_message("assistant"):
                with st.spinner("Thinking and searching..."):
                    response = asyncio.run(st.session_state.chatbot.chat(query))
                st.write(response)
            
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            st.session_state.openai_messages.append({"role": "assistant", "content": response})
    
    def render_recommandation_interface(self):
        """Render recommendation interface with sliders and product search"""
        st.header("💬 Recommendation System")

        # User guidelines for recommendation
        with st.expander("How to Use Recommendation System", expanded=False):
            st.write("""
            **Recommendation Guidelines:**
            - Search for products using specific keywords or product names
            - Once a product is found, adjust feature preferences using sliders on the right
            - Sliders represent importance levels (0.0 = least important, 1.0 = most important)
            - Click "Find Similar Products" to get recommendations based on your preferences
            - Results are ranked by similarity score to your feature preferences
            """)
        
        # Create two columns for layout
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("Product Search")
            
            # Display chat history
            for message in st.session_state.chat_history_recom:
                with st.chat_message(message["role"]):
                    st.write(message["content"])
            
            # Chat input
            if query := st.chat_input("Search for a product..."):
                # Reset recommendations for a new search
                st.session_state.similar_products = None

                st.session_state.chat_history_recom.append({"role": "user", "content": query})
                
                with st.chat_message("user"):
                    st.write(query)
                
                with st.chat_message("assistant"):
                    # NEW LINE: Create a placeholder for the assistant's message
                    message_placeholder = st.empty() 
                    # NEW LINE: Display initial processing message
                    message_placeholder.write("Searching for products...") 

                    with st.spinner("Processing..."):
                        # Step 1: Search for products
                        print(f"{query}...t1")
                        search_results = asyncio.run(st.session_state.chatbot.vector_search(query, k=5))
                        print(search_results)

                        # LLM Call
                        llm_response = asyncio.run(st.session_state.chatbot.chat_recom(query, search_results))
                        # st.write(llm_response)
                        
                        # Step 2: Extract product title and features
                        
                        if search_results and "No products were found" not in llm_response:
                            product_info = st.session_state.chatbot.extract_weighted_features(search_results)
                            
                            if "error" in product_info:
                                response = product_info["error"]
                                st.session_state.show_sliders = False
                            else:
                                product_title = product_info["product_title"]
                                feature_info = product_info["feature_ratings"]
                                product_description = product_info.get("product_description", "")

                                if "error" in feature_info:
                                    response = f"Found product: **{product_title}**\n\n{feature_info['error']}"
                                    st.session_state.show_sliders = False
                                else:
                                    feature_ratings = feature_info
                                    
                                    if feature_ratings:
                                        response = f"Found product: \n{llm_response}\n"
                                        
                                        # Store in session state
                                        st.session_state.current_product = {
                                            "title": product_title,
                                            "feature_ratings": feature_ratings
                                        }
                                        st.session_state.current_features = feature_ratings
                                        st.session_state.show_sliders = True
                                    else:
                                        response = f"Found product: **{product_title}**\n\nNo feature ratings found for this product. Please try searching for another product."
                                        st.session_state.show_sliders = False
                        else:
                            response = "No products found in database. Please try a different search term."
                            st.session_state.show_sliders = False
                    
                    message_placeholder.write(response) 
                
                st.session_state.chat_history_recom.append({"role": "assistant", "content": response})
                st.rerun() 

            # Display similar products if available
            if "similar_products" in st.session_state and st.session_state.similar_products:
                st.subheader("Recommended Products")
                
                # Create a list of columns, limited to a maximum of 4
                num_products = min(len(st.session_state.similar_products), 4)
                cols = st.columns(num_products)
                
                # Iterate through the products and display each in a column
                for i, product in enumerate(st.session_state.similar_products[:num_products]):
                    with cols[i]:
                        with st.expander(f"#{i+1} {product['title']}"):
                            st.write("**Product Features:**")
                            for feature, rating in product['features'].items():
                                display_name = feature.replace("_", " ").title()
                                st.write(f"- {display_name}: {rating:.2f}")

                            # Show match percentage
                            match_percentage = product['score'] * 100
                            st.progress(product['score'], text=f"Match: {match_percentage:.1f}%")
        
        with col2:
            st.subheader("Feature Preferences")
            
            if st.session_state.show_sliders and st.session_state.current_features:
                # Display current product info
                if st.session_state.current_product:
                    st.info(f"Current Product: **{st.session_state.current_product['title']}**")
                
                # Create sliders
                slider_result = st.session_state.chatbot.create_feature_sliders(st.session_state.current_features)
                
                if "error" in slider_result:
                    st.error(slider_result["error"])
                else:
                    slider_values = slider_result["slider_values"]
                    
                    # Submit button for finding similar products
                    if st.button("Find Similar Products", type="primary", key="find_similar"):
                        with st.spinner("Finding similar products..."):
                            similar_products = asyncio.run(st.session_state.chatbot.find_similar_products(slider_values, k=5))
                            st.session_state.similar_products = similar_products
                            st.rerun()
                    
                    # Clear selection button
                    if st.button("Clear Selection", key="clear_selection"):
                        st.session_state.current_product = None
                        st.session_state.current_features = None
                        st.session_state.show_sliders = False
                        st.session_state.similar_products = None 
                        st.rerun()
            
            else:
                st.info("Search for a product on the left to see feature sliders here!")
                
                if st.button("Reset Chat", key="reset_chat"):
                    st.session_state.chat_history_recom = []
                    st.session_state.current_product = None
                    st.session_state.current_features = None
                    st.session_state.show_sliders = False
                    st.rerun()

    def render_sidebar_actions(self):
        """Render sidebar actions"""
        with st.sidebar:
            st.header("Quick Actions")
            
            if st.button("Clear Chat History"):
                st.session_state.chat_history = []
                st.session_state.openai_messages = []
                st.rerun()
            
            if st.button("Check Redis Stats"):
                try:
                    # Properly await the async functions
                    keys = asyncio.run(scan_all_keys("doc:*"))
                    
                    # Convert to list if it's a generator or other iterable
                    if hasattr(keys, '__iter__') and not isinstance(keys, (str, dict, list)):
                        keys = list(keys)
                    elif not isinstance(keys, list):
                        keys = []
                    
                    key_count = len(keys)
                    
                    # Await the result of get_index_info
                    index_info = asyncio.run(get_index_info(st.session_state.redis_manager.index_name))
                    
                    # Ensure index_info is JSON-serializable
                    if not isinstance(index_info, dict):
                        index_info = {"info": str(index_info)}

                    # Display the results
                    st.success(f"Stats:\n- Documents: {key_count}\n- Index: {st.session_state.redis_manager.index_name}")

                except Exception as e:
                    print(f"Error in stats: {str(e)}")
                    st.error(f"Error getting stats: {str(e)}")

    def run(self):
        st.title("RediFlow AI")
        # st.markdown("A Redis-driven product knowledge and recommendation engine with a conversational AI interface to guide smarter choices.")
        st.subheader("A Redis-driven product knowledge and recommendation engine with a conversational AI interface to guide smarter choices.")
        self.render_sidebar_actions()
        
        if "active_tab" not in st.session_state:
            st.session_state.active_tab = "Upload Data"

        # Create a simple but attractive tab header
        active_tab = st.session_state.active_tab
        
        # Create tab indicator
        tab_style = """
        <style>
        .tab-container {
            display: flex;
            justify-content: center;
            margin: 20px 0;
            background: linear-gradient(135deg, #991b1b 0%, #7f1d1d 100%);
            padding: 8px;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        .tab-item {
            flex: 1;
            padding: 12px 18px;
            margin: 0 3px;
            text-align: center;
            font-weight: 600;
            font-size: 1.3rem;
            border-radius: 10px;
            color: #ffffff;
            background: rgba(153, 27, 27, 0.4);
            border: 3px solid rgba(255, 255, 255, 0.6);
        }
        .tab-item.active {
            background: linear-gradient(135deg, #450a0a 0%, #5b0f0f 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(69, 10, 10, 0.3);
            transform: translateY(-2px);
            border: 3px solid rgba(255, 255, 255, 0.8);
        }
        </style>
        """
        
        upload_class = "tab-item active" if active_tab == "Upload Data" else "tab-item"
        chat_class = "tab-item active" if active_tab == "Chat" else "tab-item"
        rec_class = "tab-item active" if active_tab == "Recommendation System" else "tab-item"
        
        st.markdown(tab_style, unsafe_allow_html=True)
        st.markdown(f"""
        <div class="tab-container">
            <div class="{upload_class}">Upload Data</div>
            <div class="{chat_class}">Chat</div>
            <div class="{rec_class}">Recommendations</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Create invisible/hidden buttons that align with the visual tabs
        col1, col2, col3 = st.columns(3)
        
        # Style the functional buttons to match the visual design
        st.markdown("""
        <style>
        /* Make the functional buttons beautiful and match the design */
        div[data-testid="column"] .stButton > button {
            background: transparent !important;
            border: none !important;
            padding: 12px 18px !important;
            margin: 0 3px !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            font-size: 1.3rem !important;
            color: #666 !important;
            width: 100% !important;
            height: auto !important;
            box-shadow: none !important;
        }
       
        /* Style active button to match active tab */
        div[data-testid="column"]:nth-child(1) .stButton > button {
            background: """ + ("linear-gradient(135deg, #450a0a 0%, #5b0f0f 100%)" if active_tab == "Upload Data" else "rgba(153, 27, 27, 0.4)") + """ !important;
            color: """ + ("white" if active_tab == "Upload Data" else "white") + """ !important;
           box-shadow: """ + ("0 4px 15px rgba(69, 10, 10, 0.3)" if active_tab == "Upload Data" else "none") + """ !important;
           transform: """ + ("translateY(-2px)" if active_tab == "Upload Data" else "translateY(0)") + """ !important;
           border: """ + ("3px solid rgba(255, 255, 255, 0.8)" if active_tab == "Upload Data" else "3px solid rgba(255, 255, 255, 0.6)") + """ !important;
       }
       
       div[data-testid="column"]:nth-child(2) .stButton > button {
            background: """ + ("linear-gradient(135deg, #450a0a 0%, #5b0f0f 100%)" if active_tab == "Chat" else "rgba(153, 27, 27, 0.4)") + """ !important;
            color: """ + ("white" if active_tab == "Chat" else "white") + """ !important;
            box-shadow: """ + ("0 4px 15px rgba(69, 10, 10, 0.3)" if active_tab == "Chat" else "none") + """ !important;
            transform: """ + ("translateY(-2px)" if active_tab == "Chat" else "translateY(0)") + """ !important;
            border: """ + ("3px solid rgba(255, 255, 255, 0.8)" if active_tab == "Chat" else "3px solid rgba(255, 255, 255, 0.6)") + """ !important;
       }
       
       div[data-testid="column"]:nth-child(3) .stButton > button {
            background: """ + ("linear-gradient(135deg, #450a0a 0%, #5b0f0f 100%)" if active_tab == "Recommendation System" else "rgba(153, 27, 27, 0.4)") + """ !important;
            color: """ + ("white" if active_tab == "Recommendation System" else "white") + """ !important;
            box-shadow: """ + ("0 4px 15px rgba(69, 10, 10, 0.3)" if active_tab == "Recommendation System" else "none") + """ !important;
            transform: """ + ("translateY(-2px)" if active_tab == "Recommendation System" else "translateY(0)") + """ !important;
            border: """ + ("3px solid rgba(255, 255, 255, 0.8)" if active_tab == "Recommendation System" else "3px solid rgba(255, 255, 255, 0.6)") + """ !important;
       }
       
       /* Hide the display-only tabs when buttons are styled */
       .tab-container {
           position: relative;
           margin-bottom: -70px;
           pointer-events: none;
           z-index: 1;
       }
       
       /* Bring buttons to front */
       div[data-testid="column"] {
           position: relative;
           z-index: 2;
       }
       </style>
       """, unsafe_allow_html=True)
        
        with col1:
            if st.button("Upload Data", key="btn_upload", use_container_width=True):
                st.session_state.active_tab = "Upload Data"
                st.rerun()
        with col2:
            if st.button("Chat", key="btn_chat", use_container_width=True):
                st.session_state.active_tab = "Chat"
                st.rerun()
        with col3:
            if st.button("Recommendations", key="btn_recommend", use_container_width=True):
                st.session_state.active_tab = "Recommendation System"
                st.rerun()
        
        # Render content based on the active tab
        if st.session_state.active_tab == "Upload Data":
            self.render_data_upload()
        elif st.session_state.active_tab == "Chat":
            self.render_chat_interface()
        elif st.session_state.active_tab == "Recommendation System":
            self.render_recommandation_interface()

if __name__ == "__main__":
    app = StreamlitApp()
    app.run()
