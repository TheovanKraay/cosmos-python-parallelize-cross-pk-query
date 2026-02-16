"""
Demo: Comparing Standard vs Parallelized Cross-Partition Queries in Azure Cosmos DB

This demo shows the performance difference between:
1. Standard cross-partition query (not parallelized)
2. Parallelized cross-partition query using feed ranges

The default query is a COUNT aggregation — an ideal candidate for parallelization
because each partition can count independently and the results are summed client-side.
"""

import asyncio
import time
import json
import re
from typing import List, Dict, Any, Tuple, Union
from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential


# Pattern to detect aggregate queries whose results can be summed across partitions
# Matches: SELECT VALUE COUNT(...), SELECT VALUE SUM(...)
_AGGREGATE_PATTERN = re.compile(
    r'\bSELECT\s+VALUE\s+(COUNT|SUM)\s*\(', re.IGNORECASE
)


def is_aggregate_query(query: str) -> bool:
    """Check if the query is a COUNT or SUM aggregate that can be summed across partitions."""
    return bool(_AGGREGATE_PATTERN.search(query))


def load_config(config_file: str = 'config.json') -> Dict[str, Any]:
    """Load configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Config file '{config_file}' not found. Using defaults.")
        return {}


class CosmosQueryComparison:
    """Compare standard vs parallelized cross-partition queries."""
    
    def __init__(self, endpoint: str, credential, database_name: str, container_name: str):
        """
        Initialize with Cosmos DB connection details.
        
        Args:
            endpoint: Cosmos DB account endpoint
            credential: Azure credential (key string or DefaultAzureCredential)
            database_name: Database name
            container_name: Container name
        """
        self.endpoint = endpoint
        self.credential = credential
        self.database_name = database_name
        self.container_name = container_name
        self.client = None
        self.database = None
        self.container = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.client = CosmosClient(self.endpoint, credential=self.credential)
        self.database = self.client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.close()
        if isinstance(self.credential, DefaultAzureCredential):
            await self.credential.close()
    
    async def standard_cross_partition_query(self, query: str) -> Tuple[Union[int, List[Dict[str, Any]]], float]:
        """
        Execute a standard cross-partition query (NOT parallelized).
        
        The SDK handles aggregation internally, querying partitions sequentially.
        
        Args:
            query: SQL query string
            
        Returns:
            Tuple of (result, elapsed_time_seconds)
            result is an int for aggregate queries, or a list of items otherwise
        """
        items = []
        start_time = time.time()
        
        async for item in self.container.query_items(query=query):
            items.append(item)
        
        elapsed_time = time.time() - start_time
        
        # For aggregate queries with VALUE, the SDK returns a single scalar
        if is_aggregate_query(query) and len(items) == 1 and isinstance(items[0], (int, float)):
            return int(items[0]), elapsed_time
        
        return items, elapsed_time
    
    async def parallelized_cross_partition_query(self, query: str) -> Tuple[Union[int, List[Dict[str, Any]]], float]:
        """
        Execute a parallelized cross-partition query using feed ranges.
        
        For COUNT/SUM aggregates, each partition returns its own count/sum and
        the results are summed client-side. For non-aggregate queries, results
        are combined into a single list.
        
        Args:
            query: SQL query string
            
        Returns:
            Tuple of (result, elapsed_time_seconds)
            result is an int for aggregate queries, or a list of items otherwise
        """
        aggregate = is_aggregate_query(query)
        
        # Get all feed ranges
        feed_ranges = [feed_range async for feed_range in self.container.read_feed_ranges()]
        
        start_time = time.time()
        
        # Create tasks for parallel execution
        async def query_feed_range(feed_range):
            items = []
            async for item in self.container.query_items(query=query, feed_range=feed_range):
                items.append(item)
            return items
        
        tasks = [query_feed_range(feed_range) for feed_range in feed_ranges]
        
        # Execute all queries in parallel
        results = await asyncio.gather(*tasks)
        
        elapsed_time = time.time() - start_time
        
        # For aggregate queries, sum the per-partition results
        if aggregate:
            total = 0
            for partition_results in results:
                for value in partition_results:
                    if isinstance(value, (int, float)):
                        total += int(value)
            return total, elapsed_time
        
        # For non-aggregate queries, combine all items
        all_items = []
        for partition_results in results:
            all_items.extend(partition_results)
        
        return all_items, elapsed_time
    
    async def compare_queries(self, query: str = 'SELECT VALUE COUNT(1) FROM c') -> None:
        """
        Compare standard vs parallelized cross-partition query performance.
        
        Args:
            query: SQL query to execute
        """
        aggregate = is_aggregate_query(query)
        
        print("="*80)
        print("COSMOS DB CROSS-PARTITION QUERY COMPARISON")
        print("="*80)
        print(f"Query: {query}")
        if aggregate:
            print("Type:  Aggregate (COUNT/SUM) — results summed client-side")
        print("="*80)
        
        # Get feed range count
        feed_ranges = [feed_range async for feed_range in self.container.read_feed_ranges()]
        print(f"\nContainer has {len(feed_ranges)} feed ranges (physical partitions)\n")
        
        # Run standard query
        print("[1] Running STANDARD cross-partition query...")
        standard_result, standard_time = await self.standard_cross_partition_query(query)
        print(f"    ✓ Completed in {standard_time:.2f} seconds")
        if aggregate:
            print(f"    ✓ Result: {standard_result:,}\n")
        else:
            print(f"    ✓ Retrieved {len(standard_result):,} items\n")
        
        # Run parallelized query
        print("[2] Running PARALLELIZED cross-partition query...")
        parallel_result, parallel_time = await self.parallelized_cross_partition_query(query)
        print(f"    ✓ Completed in {parallel_time:.2f} seconds")
        if aggregate:
            print(f"    ✓ Result: {parallel_result:,} (summed from {len(feed_ranges)} partitions)\n")
        else:
            print(f"    ✓ Retrieved {len(parallel_result):,} items\n")
        
        # Show comparison
        print("="*80)
        print("RESULTS")
        print("="*80)
        print(f"Standard query time:     {standard_time:.2f} seconds")
        print(f"Parallelized query time: {parallel_time:.2f} seconds")
        
        if parallel_time > 0:
            speedup = standard_time / parallel_time
            improvement = ((standard_time - parallel_time) / standard_time) * 100
            print(f"\nSpeedup: {speedup:.2f}x faster")
            print(f"Performance improvement: {improvement:.1f}%")
        
        if aggregate:
            if standard_result == parallel_result:
                print(f"\nResults match: {standard_result:,}")
            else:
                print(f"\nNote: results differ slightly ({standard_result:,} vs {parallel_result:,}) — expected with live data")
        
        print("="*80)


async def main():
    """Run the comparison demo."""
    
    # Load configuration
    config = load_config('config.json')
    
    endpoint = config.get('endpoint', 'https://localhost:8081')
    database_name = config.get('database', 'testdb')
    container_name = config.get('container', 'testcontainer')
    query = config.get('query', 'SELECT VALUE SUM(LENGTH(c.id)) FROM c')
    use_default_credential = config.get('use_default_credential', False)
    master_key = config.get('master_key', 'C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==')
    
    # Determine credential
    if use_default_credential:
        credential = DefaultAzureCredential()
    else:
        credential = master_key
    
    # Run comparison
    async with CosmosQueryComparison(endpoint, credential, database_name, container_name) as demo:
        await demo.compare_queries(query)


if __name__ == "__main__":
    asyncio.run(main())
