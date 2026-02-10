---
name: Data Analysis
description: Systematic approach to analyzing datasets and extracting insights
tags:
  - data
  - analysis
  - sql
  - python
triggers:
  - analyze data
  - data analysis
  - explore dataset
  - query database
priority: 10
---

# Data Analysis Workflow

When analyzing data, follow this systematic approach:

## 1. Understand the Data

Before writing any queries or code:

- List available tables with `list_tables()`
- Examine table schemas with `describe_table(table_name)`
- Understand relationships between tables
- Identify primary keys and foreign keys

## 2. Explore the Data

Start with simple exploratory queries:

```sql
-- Get row counts
SELECT COUNT(*) FROM table_name;

-- Sample data
SELECT * FROM table_name LIMIT 10;

-- Check for nulls
SELECT column_name, COUNT(*) - COUNT(column_name) as null_count
FROM table_name
GROUP BY 1;
```

## 3. Ask Good Questions

Frame your analysis around specific questions:

- What patterns exist in the data?
- What are the distributions of key metrics?
- Are there outliers or anomalies?
- What relationships exist between variables?

## 4. Use Python for Complex Analysis

For calculations that go beyond SQL:

```python
import pandas as pd

# Load data from SQL results
data = pd.DataFrame(rows, columns=columns)

# Descriptive statistics
print(data.describe())

# Grouping and aggregation
summary = data.groupby('category').agg({
    'value': ['mean', 'sum', 'count']
})
```

## 5. Document Findings

Always summarize your analysis with:

- Key insights discovered
- Data quality issues found
- Recommendations for further investigation
- Visualizations where appropriate

## Best Practices

- Start simple, add complexity as needed
- Validate results with sanity checks
- Use parameterized queries for safety
- Comment your SQL and Python code
- Consider performance for large datasets
