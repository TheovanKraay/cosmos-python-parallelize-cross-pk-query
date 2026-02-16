# Parallelizing Cross-Partition Queries in Azure Cosmos DB (Python SDK)

## The Problem

**The Azure Cosmos DB Python SDK does not parallelize cross-partition queries by default.** When you execute a query that spans multiple partitions, the SDK queries each partition sequentially, one after another. For certain query patterns, this can result in slower performance than necessary.

## The Solution

This demo shows how to **manually parallelize cross-partition queries** using feed ranges and Python's asyncio. By querying all partitions concurrently instead of sequentially, you can improve query performance — **but only for specific query patterns**.

## ⚠️ When to Use (and NOT Use) Parallelization

Parallelization via feed ranges is **not a general-purpose optimization**. It helps in a narrow set of cases and can actively hurt performance and cost in others.

### ✅ Good Candidates for Parallelization

- **Strongly filtering queries** that return a small result set from each partition:
  ```sql
  SELECT * FROM c WHERE c.status = 'active' AND c.region = 'us-east'
  ```
- **Streamable queries** without result-limiting or ordering operators
- **Point lookups across partitions** where the partition key is unknown:
  ```sql
  SELECT * FROM c WHERE c.email = 'user@example.com'
  ```

### ❌ Bad Candidates (Parallelization Will Hurt)

- **`TOP` / `LIMIT`**: Applied per feed range, so `TOP 10000` across 10 partitions returns 100,000 items (10x the RUs)
- **`ORDER BY`**: Each partition returns independently sorted results; the client must re-sort, losing the benefit
- **`OFFSET...LIMIT` / `SKIP`**: Pagination semantics break when split across feed ranges
- **Aggregates** (`COUNT`, `SUM`, `AVG`, etc.): Must be recombined client-side, adding complexity with no benefit
- **Unfiltered scans** (`SELECT * FROM c`): Same total work, but with higher peak RU consumption

> **Rule of thumb**: If the query uses `TOP`, `ORDER BY`, `OFFSET`, `LIMIT`, or aggregates, do **not** parallelize with feed ranges. Use the standard SDK query instead.

## What This Demo Shows

This demo compares two approaches using a **filtering query** (the correct use case):

1. **Standard Cross-Partition Query** (Sequential): The default SDK behavior — queries partitions one at a time
2. **Parallelized Query with Feed Ranges** (Concurrent): Uses feed ranges and asyncio to query all partitions simultaneously

Real results from a container with **100 million records** using a filtering `WHERE` clause show meaningful speedup with 10 partitions.

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
  "query": "SELECT * FROM c WHERE c.partitionKey >= 'A' AND c.partitionKey < 'B'",
  "use_default_credential": true
}
```

> **Important**: Use a filtering `WHERE` clause — not `TOP` or `LIMIT`. See [When to Use Parallelization](#️-when-to-use-and-not-use-parallelization) for details.

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
| `query` | SQL query to execute | `SELECT * FROM c WHERE c.partitionKey >= 'A' AND c.partitionKey < 'B'` |
| `use_default_credential` | Use Azure DefaultAzureCredential for authentication | `true` |

**Important**: Use a filtering `WHERE` clause that returns a manageable result set. Do **not** use `TOP`, `ORDER BY`, `OFFSET`, or aggregates — these operators do not parallelize correctly across feed ranges.

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

This output is from a container with **100 million records** partitioned by **id**, using a filtering query:

```
================================================================================
COSMOS DB CROSS-PARTITION QUERY COMPARISON
================================================================================
Query: SELECT * FROM c WHERE c.partitionKey >= 'A' AND c.partitionKey < 'B'
================================================================================

Container has 10 feed ranges (physical partitions)

[1] Running STANDARD cross-partition query...
    ✓ Completed in 6.49 seconds
    ✓ Retrieved 8523 items

[2] Running PARALLELIZED cross-partition query...
    ✓ Completed in 1.12 seconds
    ✓ Retrieved 8523 items

================================================================================
RESULTS
================================================================================
Standard query time:     6.49 seconds
Parallelized query time: 1.12 seconds

Speedup: 5.79x faster
Performance improvement: 82.7%
================================================================================
```

**Note**: Both queries return the same items because the `WHERE` clause is applied identically on every partition. This is the correct use case for feed-range parallelization — a filtering query with no `TOP`, `ORDER BY`, or aggregates.

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

- **Query Pattern Matters Most**: Only filtering/streamable queries benefit. `TOP`, `ORDER BY`, `OFFSET`, and aggregates will produce incorrect or wasteful results when parallelized
- **RU Cost**: Parallel queries consume RUs from all partitions simultaneously. Ensure sufficient throughput to avoid throttling (429 errors)
- **More Feed Ranges = More Parallelism**: Performance scales with the number of physical partitions
- **Network Latency**: Parallel queries show greater improvement with higher latency
- **Result Set Size**: Best suited for strongly-filtering queries that return a small subset of data from each partition

## Troubleshooting

### Query Hanging or Taking Too Long
- Add `WHERE` filters to narrow the result set
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
