import asyncio
import sys
import os

redis_project_path = os.path.join(os.path.dirname(__file__), '..', 'mcp-redis')
sys.path.append(os.path.abspath(redis_project_path))

from src.common.connection import RedisConnectionManager
from src.common.config import REDIS_CFG, set_redis_config_from_cli
from src.tools.redis_query_engine import create_vector_index_hash, vector_search_hash, get_index_info
from src.tools.hash import hset, hgetall, set_vector_in_hash
from src.tools.misc import scan_all_keys
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



function_mappings = {
    "delete": delete,
    "type": type,
    "expire": expire,
    "rename": rename,
    "scan_keys": scan_keys,
    "scan_all_keys": scan_all_keys,
    "zadd": zadd,
    "zrange": zrange,
    "zrem": zrem,
    "lpush": lpush,
    "rpush": rpush,
    "lpop": lpop,
    "rpop": rpop,
    "lrange": lrange,
    "llen": llen,
    "get_indexes": get_indexes,
    "get_index_info": get_index_info,
    "get_indexed_keys_number": get_indexed_keys_number,
    "create_vector_index_hash": create_vector_index_hash,
    "vector_search_hash": vector_search_hash,
    "hset": hset,
    "hget": hget,
    "hdel": hdel,
    "hgetall": hgetall,
    "hexists": hexists,
    "set_vector_in_hash": set_vector_in_hash,
    "get_vector_from_hash": get_vector_from_hash,
    "json_set": json_set,
    "json_get": json_get,
    "json_del": json_del,
    "dbsize": dbsize,
    "info": info,
    "client_list": client_list,
    "xadd": xadd,
    "xrange": xrange,
    "xdel": xdel,
    "publish": publish,
    "subscribe": subscribe,
    "unsubscribe": unsubscribe,
    "sadd": sadd,
    "srem": srem,
    "smembers": smembers,
    "set": set,
   
}