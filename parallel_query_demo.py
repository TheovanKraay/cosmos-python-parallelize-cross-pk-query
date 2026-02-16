"""
Demo: Comparing Standard vs Parallelized Cross-Partition Queries in Azure Cosmos DB

This demo shows the performance difference between:
1. Standard cross-partition query (not parallelized)
2. Parallelized cross-partition query using feed ranges
"""

import asyncio
import time
import json
from typing import List, Dict, Any, Tuple
from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential


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
    
    async def standard_cross_partition_query(self, query: str) -> Tuple[List[Dict[str, Any]], float]:
        """
        Execute a standard cross-partition query (NOT parallelized).
        
        Args:
            query: SQL query string
            
        Returns:
            Tuple of (items, elapsed_time_seconds)
        """
        items = []
        start_time = time.time()
        
        async for item in self.container.query_items(query=query):
            items.append(item)
        
        elapsed_time = time.time() - start_time
        return items, elapsed_time
    
    async def parallelized_cross_partition_query(self, query: str) -> Tuple[List[Dict[str, Any]], float]:
        """
        Execute a parallelized cross-partition query using feed ranges.
        
        Args:
            query: SQL query string
            
        Returns:
            Tuple of (items, elapsed_time_seconds)
        """
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
        
        # Combine results
        all_items = []
        for partition_results in results:
            all_items.extend(partition_results)
        
        elapsed_time = time.time() - start_time
        return all_items, elapsed_time
    
    async def compare_queries(self, query: str = 'SELECT * FROM c') -> None:
        """
        Compare standard vs parallelized cross-partition query performance.
        
        Args:
            query: SQL query to execute
        """
        print("="*80)
        print("COSMOS DB CROSS-PARTITION QUERY COMPARISON")
        print("="*80)
        print(f"Query: {query}")
        print("="*80)
        
        # Get feed range count
        feed_ranges = [feed_range async for feed_range in self.container.read_feed_ranges()]
        print(f"\nContainer has {len(feed_ranges)} feed ranges (physical partitions)\n")
        
        # Run standard query
        print("[1] Running STANDARD cross-partition query...")
        standard_items, standard_time = await self.standard_cross_partition_query(query)
        print(f"    ✓ Completed in {standard_time:.2f} seconds")
        print(f"    ✓ Retrieved {len(standard_items)} items\n")
        
        # Run parallelized query
        print("[2] Running PARALLELIZED cross-partition query...")
        parallel_items, parallel_time = await self.parallelized_cross_partition_query(query)
        print(f"    ✓ Completed in {parallel_time:.2f} seconds")
        print(f"    ✓ Retrieved {len(parallel_items)} items\n")
        
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
        
        print("="*80)


async def main():
    """Run the comparison demo."""
    
    # Load configuration
    config = load_config('config.json')
    
    endpoint = config.get('endpoint', 'https://localhost:8081')
    database_name = config.get('database', 'testdb')
    container_name = config.get('container', 'testcontainer')
    query = config.get('query', "SELECT * FROM c WHERE c.partitionKey >= 'A' AND c.partitionKey < 'B'")
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
