# Parallelizing Cross-Partition Queries in Azure Cosmos DB (Python SDK)

## The Problem

**The Azure Cosmos DB Python SDK does not parallelize cross-partition queries by default.** When you execute a query that spans multiple partitions, the SDK queries each partition sequentially, one after another. This can result in slow query performance, especially for containers with many physical partitions or large datasets.

## The Solution

This demo shows how to **manually parallelize cross-partition queries** using feed ranges and Python's asyncio. By querying all partitions concurrently instead of sequentially, you can significantly improve query performance.

## What This Demo Shows

This demo compares two approaches:

1. **Standard Cross-Partition Query** (Sequential): The default SDK behavior - queries partitions one at a time
2. **Parallelized Query with Feed Ranges** (Concurrent): Uses feed ranges and asyncio to query all partitions simultaneously

Real results from a container with **100 million records** show **1.37x speedup** (6.49s → 4.74s) with 10 partitions.

## Quick Start

### 1. Create a Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Your Cosmos DB Connection

Copy the example config and update with your settings:

```bash
cp config.example.json config.json
```

Edit `config.json` with your Cosmos DB details:

```json
{
  "endpoint": "https://your-cosmos-account.documents.azure.com:443/",
  "database": "your-database-name",
  "container": "your-container-name",
  "query": "SELECT TOP 10000 * FROM c",
  "use_default_credential": true
}
```

### 4. Authenticate with Azure

```bash
az login
```

### 5. Run the Demo

```bash
python parallel_query_demo.py
```

## Configuration Options

Edit `config.json` to customize the demo:

| Field | Description | Example |
|-------|-------------|---------|
| `endpoint` | Cosmos DB endpoint URL | `https://your-account.documents.azure.com:443/` |
| `database` | Database name | `your-database` |
| `container` | Container name | `your-container` |
| `query` | SQL query to execute | `SELECT TOP 10000 * FROM c` |
| `use_default_credential` | Use Azure DefaultAzureCredential for authentication | `true` |

**Important**: Use `TOP` clause to limit results for large datasets. For 100M+ records, start with `SELECT TOP 10000 * FROM c`.

## Authentication

The demo uses `DefaultAzureCredential` which tries multiple authentication methods:
- Azure CLI (`az login`)
- Managed Identity
- Environment variables
- And more

Make sure you're authenticated:

```bash
az login
```

## Example Output

This output is from a container with **100 million records** partitioned by **id**:

```
================================================================================
COSMOS DB CROSS-PARTITION QUERY COMPARISON
================================================================================
Query: SELECT TOP 10000 * FROM c
================================================================================

Container has 10 feed ranges (physical partitions)

[1] Running STANDARD cross-partition query...
    ✓ Completed in 6.49 seconds
    ✓ Retrieved 10000 items

[2] Running PARALLELIZED cross-partition query...
    ✓ Completed in 4.74 seconds
    ✓ Retrieved 100000 items

================================================================================
RESULTS
================================================================================
Standard query time:     6.49 seconds
Parallelized query time: 4.74 seconds

Speedup: 1.37x faster
Performance improvement: 26.9%
================================================================================
```

**Note**: The parallelized query retrieves more items because `TOP` is applied per feed range (10,000 × 10 feed ranges = 100,000 items). For a fair comparison on result count, use `WHERE` clauses instead of `TOP`.

## Project Structure

```
.
├── parallel_query_demo.py       # Main demo with comparison logic
├── config.json                   # Your configuration (gitignored)
├── config.example.json           # Template configuration
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## How It Works

### Standard Cross-Partition Query
```python
async for item in container.query_items(
    query=query,
    enable_cross_partition_query=True
):
    items.append(item)
```

### Parallelized Query with Feed Ranges
```python
# Get feed ranges (physical partitions)
feed_ranges = [fr async for fr in container.read_feed_ranges()]

# Query each feed range in parallel
async def query_feed_range(feed_range):
    return [item async for item in container.query_items(
        query=query, 
        feed_range=feed_range
    )]

# Execute in parallel
results = await asyncio.gather(*[
    query_feed_range(fr) for fr in feed_ranges
])
```

## Performance Considerations

- **Large Datasets**: Always use `TOP` clause or `WHERE` filters for datasets with millions of records
- **More Feed Ranges = More Parallelism**: Performance scales with the number of physical partitions
- **Container Throughput**: Ensure sufficient RU/s for parallel queries
- **Network Latency**: Parallel queries show greater improvement with higher latency
- **Query Complexity**: Benefits vary by query type and result set size

## Troubleshooting

### Query Hanging or Taking Too Long
- Use `TOP` clause to limit results: `SELECT TOP 10000 * FROM c`
- Add `WHERE` filters to reduce the dataset
- Check container throughput and scale if needed

### Authentication Issues
- Run `az login` to authenticate with Azure
- Verify you have read permissions on the Cosmos DB account
- Check firewall rules allow your IP address

### Performance Issues
- Monitor RU consumption in Azure Portal
- Check for throttling (429 errors)
- Consider increasing container throughput
- Verify network connectivity
