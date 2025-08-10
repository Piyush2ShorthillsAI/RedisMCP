# Rediflow AI

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)

## Overview

**Rediflow** is an intelligent data processing and chatbot platform that combines Redis vector storage with AI-powered natural language interfaces. The project integrates a Redis MCP (Model Context Protocol) Server with an advanced chatbot system for seamless data ingestion, vector search, getting smart product recommendations and intelligent query processing.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Rediflow Platform                        │
├─────────────────────────────────────────────────────────────┤
│  Intelligent Chat & Recommendation System (Streamlit)      │
│  ├── User Authentication & Session Management              │
│  ├── JSON Data Processing & Vector Indexing               │
│  ├── Natural Language Query Processing                     │
│  ├── Advanced Product Recommendation Engine               │
│  └── Feature-Based Preference Learning                     │
├─────────────────────────────────────────────────────────────┤
│  Redis MCP Server                                          │
│  ├── Model Context Protocol Implementation                 │
│  ├── Vector Similarity Search Engine                       │
│  ├── Multi-Data Structure Management                       │
│  └── Natural Language Interface                            │
├─────────────────────────────────────────────────────────────┤
│  Redis Vector Database                                     │
│  ├── High-Performance Vector Storage & Search              │
│  ├── Product Metadata & Feature Storage (Hash)            │
│  ├── Real-time Messaging (Pub/Sub)                        │
│  └── Event Streaming & Processing                          │
└─────────────────────────────────────────────────────────────┘
```

## Features

### **Core Capabilities**
- **Advanced Product Recommendation Engine**: AI-powered product recommendations based on feature preferences
- **Vector-Powered Search**: High-performance semantic search using Redis vector indexing
- **JSON Data Processing**: Intelligent processing and indexing of product catalog JSON data
- **Feature-Based Preference Learning**: Dynamic slider-based feature preference system
- **Intelligent Chatbot**: LLM-powered query analysis with automatic MCP tool selection
- **MCP Integration**: Full Model Context Protocol support for AI agent workflows

### **Recommendation System Features**
- **Smart Product Discovery**: Natural language product search with semantic understanding
- **Feature Extraction**: Automatic extraction of product features and ratings from JSON metadata
- **Interactive Preference Tuning**: Dynamic sliders for adjusting feature importance (0.0-1.0 scale)
- **Similarity Matching**: Advanced algorithms to find products matching user preferences
- **Real-time Recommendations**: Instant product recommendations based on feature similarity
- **Ranked Results**: Products ranked by compatibility score with user preferences

### **Redis Operations**
- **Vector Operations**: High-performance vector storage, indexing, and similarity search
- **Hash Operations**: Efficient storage of product metadata and feature ratings
- **JSON Storage**: Complex nested product data management
- **List Management**: Queue operations for recommendation processing
- **Set Operations**: Unique collections for product categorization
- **Sorted Sets**: Ranking and scoring systems for recommendations

### **AI-Powered Features**
- **Natural Language Product Search**: Find products using conversational queries
- **Automatic Tool Selection**: LLM intelligently chooses appropriate Redis operations
- **Context-Aware Responses**: Intelligent product information extraction and presentation
- **Feature Preference Learning**: AI-driven understanding of user preferences

## Project Structure

```
Rediflow/
├── chat_and_recommandation/          # Streamlit-based chat application
│   ├── chatbot_and_recom.py         # Main chatbot application
│   ├── login.py                      # User authentication system
│   ├── file_uploader_service_from_nifi_pipeline.py  # FastAPI file upload service
│   ├── redis_function_mappings.py   # Redis operation mappings
│   ├── redis_mcp_tools.json         # MCP tool definitions
│   ├── Ingestion_to_Redis_Database.json  # NiFi pipeline configuration
└── mcp-redis/                 # Redis MCP Server
    ├── src/                          # Source code
    │   ├── common/                   # Shared utilities
    │   ├── tools/                    # Redis operation tools
    │   └── main.py                   # MCP server entry point
    ├── examples/                     # Usage examples
    ├── pyproject.toml               # Python dependencies
└── README.md                    # setup instructions and project overview
└──.gitignore                    # list of files to exclude from Git tracking
└── requirement.txt                   # list of all Python dependencies

## Installation & Setup

### Prerequisites

- **Python 3.10 or higher**
- **Redis Database** (Redis Cloud recommended with RediSearch module)
- **Azure OpenAI** access
- **Git** for cloning the repository

### 1. Clone the Repository

```bash
git clone https://github.com/shorthills-ai/RedisMCP.git
cd  RedisMCP

```

### 2. Install Dependencies

#### For MCP Redis Server(https://github.com/redis/mcp-redis.git):
```bash
git clone https://github.com/redis/mcp-redis.git
cd mcp-redis
# Using uv (recommended)
uv venv
source .venv/bin/activate
uv sync

```

#### Rediflow AI Application:
```bash
cd RedisMCP
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file in the `chat_and_recommandation` directory:

```bash
cd chat_and_recommandation
cp .env  # If available, or create new file
```

Configure your environment variables:

```env
# Azure OpenAI
AZURE_OPENAI_API_KEY=your_azure_api_key
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
AZURE_OPENAI_DEPLOYMENT=your_azure_openai_deployement
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=your_azure_embedding_model

# Redis Configuration
REDIS_URL=rediss://username:password@host:port/db
# OR individual parameters
REDIS_HOST=your_redis_host
REDIS_PORT=6379
REDIS_PASSWORD=your_password
REDIS_SSL=true
```

### 4. Redis Database Setup

#### Option A: Redis Cloud (Recommended)
1. Create account at [redis.com](https://redis.com)
2. Create a new database with **RediSearch** module enabled
3. Copy connection details to your `.env` file

#### Option B: Local Redis with Docker
```bash
docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest
```

## Usage Guide

### Starting the Applications

#### 1. Start the MCP Redis Server

```bash
cd mcp-redis
# Using environment variables
uv run src/main.py

# Or with CLI parameters
uv run redis-mcp-server --url redis://localhost:6379/0
```

#### 2. Start the Chat & Recommendation Application

```bash
cd chat_and_recommandation
streamlit run login.py
```Demo Username = admin
   Demo Password = password123
```

### Using the Application

#### **Login & Navigation**
1. **Login**: Use demo credentials (admin/password123, user1/pass123, demo/demo123)
2. **Redis Connection**: Configure Redis connection
3. **Choose Interface**: Select between "Upload", "Chat" and "Recommendation" tabs

#### **Upload Data Interface**
- **Upload Data**: Upload JSON data to store in the Redis Database

#### **Chat Interface**
- **General Queries**: Ask questions about stored data
- **Database Operations**: Retrieve statistics and information
- **Data Search**: Find specific information using natural language

#### **Recommendation System Interface**

**Step 1: Product Search**
```
Search Examples:
- "printers with good performance"
- "papers for printers"
- "inkjet printers"
- "printer inks"
```

**Step 2: Feature Preference Tuning**
- After finding a product, feature sliders appear on the right panel
- Adjust importance levels for each feature (0.0 = least important, 1.0 = most important)
- Features extracted automatically from product metadata (e.g., battery_life, camera_quality, performance)

**Step 3: Get Recommendations**
- Click "Find Similar Products" to get personalized recommendations
- Results ranked by compatibility score with your preferences
- View detailed feature ratings for each recommended product

#### Example Recommendation Workflow:
```
1. Search: "inkjet printer"
2. Adjust sliders: ink_efficiency=0.9, print_quality=1.0, portability=0.7
3. Get recommendations: Receive 4 similar speakers ranked by preference match
4. Explore results: View detailed feature breakdowns and match percentages
```

### MCP Integration

The MCP server can be integrated with various AI tools:

#### Claude Desktop Configuration:
```json
{
    "mcpServers": {
        "redis-mcp-server": {
            "command": "uvx",
            "args": [
                "--from", "git+https://github.com/redis/mcp-redis.git",
                "redis-mcp-server",
                "--url", "redis://localhost:6379/0"
            ]
        }
    }
}
```

#### VS Code with GitHub Copilot:
```json
{
  "mcp": {
    "servers": {
      "redis": {
        "type": "stdio",
        "command": "uv",
        "args": ["run", "src/main.py"],
        "env": {
          "REDIS_HOST": "localhost",
          "REDIS_PORT": "6379"
        }
      }
    }
  }
}
```

#### Cursor Desktop:
```json
{
  "mcpServers": {
    "redis": {
      "command": "path_to_uv",
      "args": [
        "--directory",
        "path_to_redis_mcp_folder",
        "run",
        "src/main.py"
      ],
      "env": {
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "6379",
        "REDIS_DB": "0",
        "REDIS_USERNAME": "",
        "REDIS_PWD": "",
        "REDIS_SSL": "false",
        "REDIS_CA_PATH": "",
        "REDIS_CLUSTER_MODE": "false"
      }
    }
  }
}
```

## Use Cases

### 1. **E-commerce Recommendation Engine**
- **Product Discovery**: Help customers find products using natural language
- **Personalized Recommendations**: AI-driven product suggestions based on feature preferences
- **Feature-Based Filtering**: Allow customers to express preferences through intuitive sliders
- **Cross-selling**: Recommend complementary products based on similarity scores

### 2. **Retail & Inventory Management**
- **Product Catalog Search**: Semantic search across entire product catalogs
- **Inventory Analysis**: Find similar products for replacement or alternative suggestions
- **Customer Preference Analytics**: Understand customer preferences through interaction data
- **Dynamic Pricing**: Use feature ratings for competitive pricing strategies

### 3. **Content Recommendation Systems**
- **Media Streaming**: Recommend movies, music, or content based on feature preferences
- **News Aggregation**: Suggest articles based on topic similarity and user interests
- **Educational Content**: Recommend courses or materials based on learning preferences
- **Social Media**: Content recommendation based on engagement patterns

### 4. **Business Intelligence & Analytics**
- **Market Research**: Analyze product features and competitive positioning
- **Customer Insights**: Understand customer preferences through recommendation interactions
- **Trend Analysis**: Identify popular features and emerging preferences
- **Performance Metrics**: Track recommendation accuracy and user satisfaction

### 5. **AI-Powered Customer Service**
- **Intelligent Product Support**: Help customers find the right products for their needs
- **Automated Recommendations**: Provide instant product suggestions without human intervention
- **Preference Learning**: Improve recommendations over time through interaction data
- **Multi-modal Search**: Combine text search with feature-based filtering

### 6. **Data Science & Research**
- **Similarity Analysis**: Research product relationships and feature correlations
- **Vector Space Exploration**: Understand high-dimensional product feature spaces
- **Algorithm Testing**: Test and validate recommendation algorithms
- **Feature Engineering**: Experiment with different feature weighting strategies

## Available Redis Operations

### Data Structures
- **Hashes**: Field-value pairs, vector storage, metadata management

### Vector Operations
- **Index Creation**: Automatic vector index setup
- **Vector Storage**: Embed and store document vectors
- **Similarity Search**: Find semantically similar content
- **Hybrid Search**: Combine vector and metadata filtering

### Server Management
- **Database Statistics**: Monitor usage and performance
- **Connection Management**: Handle client connections
- **Index Information**: Retrieve search index details

## API Reference

### Recommendation System API

The application provides comprehensive recommendation functionality:

**Core Recommendation Methods:**
```python
# Product search and discovery
vector_search(query, k=5)          # Semantic product search
chat_recom(query, search_results)  # LLM-powered product analysis

# Feature extraction and processing
extract_weighted_features(products) # Extract feature ratings from JSON
create_feature_sliders(features)   # Generate interactive preference sliders

# Recommendation generation
find_similar_products(preferences, k=5) # Find matching products based on features
```

**Data Processing Pipeline:**
```python
# JSON product data structure expected:
{
  "raw_metadata": {
    "title": "Product Name",
    "productDescription": "Description...",
    "features": {...}
  },
  "product_ranking": {
    "features_wise": {
      "weighted_feature_rating_unit_scale": {
        "battery_life": 0.85,
        "camera_quality": 0.92,
        "performance": 0.78
      }
    }
  }
}
```

### MCP Tools

The MCP server exposes Redis operations as natural language tools:

- `create_vector_index_hash`: Initialize vector search indices for products
- `vector_search_hash`: Perform semantic similarity searches
- `set_vector_in_hash`: Store product vectors with metadata
- `hset/hget/hgetall`: Hash operations for product data storage
- `scan_all_keys`: Database exploration and product catalog statistics
- `json_set/json_get`: JSON product document management
- And many more Redis operations for data management...

## Troubleshooting

### Common Issues

#### Redis Connection Problems
```bash
# Check Redis connectivity
redis-cli ping

# Verify Redis modules
redis-cli MODULE LIST
```

#### Missing Dependencies
```bash
# Reinstall requirements
pip install --upgrade -r requirements.txt

# For MCP server
cd mcp-redis && uv sync
```

#### Vector Search Issues
- Ensure RediSearch module is enabled
- Check vector index creation in Redis
- Verify embedding model compatibility

#### Authentication Errors
- Verify OpenAI/Azure API keys
- Check Redis credentials and SSL settings
- Ensure proper environment variable configuration

### Performance Optimization

- **Chunk Size**: Adjust text chunking for your data type
- **Vector Dimensions**: Match embedding model dimensions
- **Redis Memory**: Monitor memory usage for large datasets
- **Connection Pooling**: Use connection pooling for high-load scenarios

---

**Built using Redis, Streamlit, and the Model Context Protocol** 
