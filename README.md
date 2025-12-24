# MarketForge

A professional-grade synthetic OHLCV (Open-High-Low-Close-Volume) data generator for financial markets. Designed for backtesting, algorithm development, and quantitative research, this tool generates realistic market data with proper statistical properties, correlations, and market dynamics.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Output Format](#output-format)
- [Performance](#performance)
- [Advanced Features](#advanced-features)
- [Examples](#examples)
- [Contributing](#contributing)
- [License](#license)

## Features

### Core Capabilities

- **Multi-Market Support**: Generate data for Forex (81 pairs), Crypto (53 assets), and Stocks (74 symbols)
- **Realistic Price Dynamics**: 
  - GARCH(1,1) volatility clustering
  - Regime-switching models (trend, range, high volatility, crash)
  - Correlated multi-asset returns via Cholesky decomposition
  - Geometric Brownian Motion with drift
- **Realistic OHLCV Construction**:
  - Proper intrabar high/low simulation with wicks
  - Market-specific gap handling (overnight, weekend)
  - Volume correlated with price movements and volatility
  - Time-of-day volume patterns (session-based markets)
- **Anomaly Injection**:
  - Price gaps (overnight/weekend discontinuities)
  - Spikes (fat-tail events with long wicks)
  - Flash crashes (multi-candle V-shaped recoveries)
- **Multiple Timeframes**: Automatic aggregation from m1 to W1 (m1, m5, m15, m30, H1, H4, D1, W1)
- **Batch Processing**: Memory-efficient processing with configurable batch sizes
- **Parallel Processing**: Multi-threaded batch processing for faster generation
- **Reproducibility**: Seed-based random number generation for identical outputs

### Market-Specific Features

- **Crypto**: 24/7 trading, no gaps, higher volatility, flash crash events
- **Forex**: Session-based trading, weekend gaps, lower volatility, session patterns
- **Stocks**: Market hours, overnight/weekend gaps, U-shaped volume patterns

## Installation

### Requirements

- Python 3.10 or higher

### Install from PyPI

For basic users, install the package directly from PyPI:

```bash
pip install marketforge
```

### Install from Source

For developers who want to modify the code or install the latest development version:

```bash
# Clone or download the repository
cd marketforge

# Install in development mode
pip install -e .

# Or install dependencies directly
pip install -r requirements.txt
```

### Verify Installation

```bash
python -m marketforge --help
```

## Quick Start

### Basic Example

Generate data for all markets with default settings:

```bash
python -m marketforge \
    --output-dir ./data \
    --from 1704067200 \
    --to 1704153600 \
    --seed 42
```

### Generate Specific Markets

```bash
# Generate only crypto market
python -m marketforge \
    --output-dir ./data \
    --from 1704067200 \
    --to 1704153600 \
    --market crypto \
    --seed 42

# Generate multiple markets
python -m marketforge \
    --output-dir ./data \
    --from 1704067200 \
    --to 1704153600 \
    --market forex,crypto \
    --seed 42
```

### With Anomalies

```bash
python -m marketforge \
    --output-dir ./data \
    --from 1704067200 \
    --to 1704153600 \
    --anomalies gaps,spikes,flash_crash \
    --seed 42
```

## Usage

### Command-Line Interface

The generator provides a comprehensive CLI with the following options:

#### Required Arguments

- `--output-dir, -o`: Output directory where CSV files will be written
- `--from`: Start timestamp in Unix epoch seconds (UTC)
- `--to`: End timestamp in Unix epoch seconds (UTC)

#### Optional Arguments

- `--market, -m`: Markets to generate (`forex`, `crypto`, `stocks`, `all`). Default: `all`
- `--seed, -s`: Random seed for reproducibility. Default: random
- `--anomalies`: Comma-separated anomaly types (`gaps`, `spikes`, `flash_crash`)
- `--timeframes, -t`: Comma-separated timeframes. Default: `m1,m5,m15,m30,H1,H4,D1,W1`
- `--batch-size`: Number of assets per batch (memory management). Default: 25
- `--threads, --thread-count`: Number of threads for parallel processing. Default: auto-detect
- `--progress/--no-progress`: Show/hide progress bar. Default: enabled

### Getting Unix Timestamps

**Linux/Mac:**
```bash
date +%s                    # Current timestamp
date -d "2024-01-01" +%s    # Specific date
```

**Windows (PowerShell):**
```powershell
[DateTimeOffset]::Parse("2024-01-01").ToUnixTimeSeconds()
```

**Online Tools:**
- Use online Unix timestamp converters
- Example: https://www.epochconverter.com/

### Timeframe Options

Available timeframes:
- `m1`: 1 minute
- `m5`: 5 minutes
- `m15`: 15 minutes
- `m30`: 30 minutes
- `H1`: 1 hour
- `H4`: 4 hours
- `D1`: 1 day
- `W1`: 1 week

All timeframes are aggregated from m1 data using standard OHLCV aggregation rules.

### Anomaly Types

- `gaps`: Price discontinuities between candles (overnight, weekend, news events)
- `spikes`: Sudden intrabar price moves (fat-tail events with long wicks)
- `flash_crash`: Multi-candle sharp declines with V-shaped recovery

**Note**: Gaps are automatically disabled for crypto markets (24/7 trading).

### Batch Processing

For large datasets, adjust batch size based on available memory:

```bash
# Small batch size (less memory, slower)
python -m marketforge ... --batch-size 10

# Large batch size (more memory, faster)
python -m marketforge ... --batch-size 50
```

### Parallel Processing

Enable multi-threaded processing for faster generation:

```bash
# Use 4 threads
python -m marketforge ... --threads 4

# Sequential processing (no threading)
python -m marketforge ... --threads 1

# Auto-detect (default, up to 16 threads)
python -m marketforge ...
```

## Architecture

### Key Components

#### 1. Return Generation (`core/returns.py`)

Generates correlated log-returns using:
- **Correlation Engine**: Cholesky decomposition for multi-asset correlation
- **GARCH(1,1) Model**: Volatility clustering (σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1})
- **Regime-Switching**: Markov chain for market state transitions
- **Geometric Brownian Motion**: Price evolution with drift

#### 2. OHLCV Construction (`generators/ohlcv.py`)

Converts price series to OHLCV candles:
- **Open Prices**: May include gaps for non-crypto markets
- **High/Low**: Intrabar volatility model (Garman-Klass inspired)
- **Wicks**: Realistic upper/lower shadows based on volatility
- **Volume**: Correlated with price movements and volatility

#### 3. Volume Generation (`generators/volume.py`)

Generates realistic trading volumes:
- **Log-Normal Distribution**: Base volume distribution
- **Volume Clustering**: Autoregressive component
- **Return-Volume Correlation**: Higher volume on large moves
- **Time-of-Day Patterns**: Session-based multipliers (stocks, forex)

#### 4. Anomaly Injection (`generators/anomalies.py`)

Injects market anomalies:
- **Gaps**: Price discontinuities at session boundaries
- **Spikes**: Fat-tail events with extended wicks
- **Flash Crashes**: Multi-candle decline and recovery patterns

#### 5. Timeframe Aggregation (`aggregation/timeframes.py`)

Aggregates m1 data to higher timeframes:
- Standard OHLCV rules: Open (first), High (max), Low (min), Close (last), Volume (sum)
- Efficient numpy-based aggregation

#### 6. Batch Processing (`processing/batch.py`)

Manages memory-efficient processing:
- Splits assets into batches
- Maintains correlation within batches
- Supports parallel processing via threading
- Automatic memory management

## Configuration

### Market Configurations

Each market has pre-configured:
- **Asset Definitions**: Symbols, start prices, volatilities, drifts
- **Correlation Matrices**: Realistic inter-asset correlations
- **Volume Parameters**: Base volumes and volume volatilities
- **Market Defaults**: GARCH params, regime params, anomaly configs

### Market-Specific Defaults

#### Crypto Market
- **Assets**: 53 cryptocurrencies (BTC, ETH, SOL, etc.)
- **Volatility**: Higher (0.55-1.00 annualized)
- **Gaps**: Disabled (24/7 trading)
- **Anomalies**: Spikes and flash crashes

#### Forex Market
- **Assets**: 81 currency pairs (EURUSD, GBPUSD, etc.)
- **Volatility**: Lower (0.008-0.015 annualized)
- **Gaps**: Enabled (weekend and session gaps)
- **Anomalies**: Gaps and spikes

#### Stocks Market
- **Assets**: 74 stock symbols (AAPL, MSFT, etc.)
- **Volatility**: Moderate (0.015-0.030 annualized)
- **Gaps**: Enabled (overnight and weekend)
- **Anomalies**: Gaps and spikes

### Custom Configuration

To customize market parameters, modify the configuration files:
- `marketforge/configs/crypto_config.py`
- `marketforge/configs/forex_config.py`
- `marketforge/configs/stocks_config.py`

## Output Format

### Directory Structure

```
output/
├── crypto/
│   ├── BTCUSD_m1.csv
│   ├── BTCUSD_m5.csv
│   ├── BTCUSD_H1.csv
│   ├── BTCUSD_D1.csv
│   ├── ETHUSD_m1.csv
│   └── ...
├── forex/
│   ├── EURUSD_m1.csv
│   ├── EURUSD_m5.csv
│   └── ...
└── stocks/
    ├── AAPL_m1.csv
    ├── AAPL_m5.csv
    └── ...
```

### CSV Format

Each CSV file contains:

```csv
timestamp,open,high,low,close,volume
1704067200,50000.00000000,50125.50000000,49875.25000000,50050.75000000,1250.5000
1704067260,50050.75000000,50100.00000000,50025.00000000,50075.25000000,1180.2500
...
```

**Columns:**
- `timestamp`: Unix timestamp (seconds since epoch)
- `open`: Opening price
- `high`: Highest price in the period
- `low`: Lowest price in the period
- `close`: Closing price
- `volume`: Trading volume

**Precision:**
- Prices: 8 decimal places
- Volume: 4 decimal places

### Data Validation

The generated data ensures:
- `high >= max(open, close)`
- `low <= min(open, close)`
- `high >= low`
- `volume >= 0`
- No negative prices

## Performance

### Memory Usage

Memory usage depends on:
- Number of assets per batch
- Duration (number of m1 candles)
- Number of timeframes

**Estimation:**
- Per asset (1 month, 8 timeframes): ~5-10 MB
- Batch of 25 assets: ~125-250 MB
- Full market (e.g., 53 crypto assets): ~265-530 MB per batch

**Recommendations:**
- Use `--batch-size 25` for most systems
- Reduce to `--batch-size 10` for limited RAM (< 8 GB)
- Increase to `--batch-size 50` for systems with > 16 GB RAM

## Advanced Features

### Programmatic Usage

The generator can be used programmatically:

```python
from marketforge.configs.loader import ConfigRegistry
from marketforge.processing.batch import generate_market_batched, BatchConfig
from marketforge.configs.base import MarketType
from marketforge.config.settings import AnomalyType

# Load market configuration
registry = ConfigRegistry()
crypto_config = registry.get_config(MarketType.CRYPTO)

# Configure batch processing
batch_config = BatchConfig(
    batch_size=25,
    thread_count=4,
    gc_between_batches=True
)

# Generate data
output_paths = generate_market_batched(
    market_config=crypto_config,
    start_timestamp=1704067200,
    end_timestamp=1704153600,
    output_dir="./data",
    seed=42,
    anomaly_types=frozenset({AnomalyType.SPIKES, AnomalyType.FLASH_CRASH}),
    timeframes=("m1", "m5", "H1", "D1"),
    batch_config=batch_config,
    show_progress=True
)
```

### Custom Asset Generation

To generate data for custom assets:

```python
from marketforge.config.settings import GeneratorConfig, AssetConfig, GARCHParams
from marketforge.generators.ohlcv import OHLCVBuilder
from marketforge.utils.random import RandomState
import numpy as np

# Define custom assets
assets = [
    AssetConfig("CUSTOM1", start_price=100.0, volatility=0.02, drift=0.0001),
    AssetConfig("CUSTOM2", start_price=50.0, volatility=0.03, drift=0.0002),
]

# Create correlation matrix
correlation_matrix = np.array([
    [1.0, 0.7],
    [0.7, 1.0]
])

# Create generator config
config = GeneratorConfig(
    assets=assets,
    market_type=MarketType.CRYPTO,
    start_timestamp=1704067200,
    end_timestamp=1704153600,
    correlation_matrix=correlation_matrix,
    seed=42
)

# Generate data
rng = RandomState(42)
builder = OHLCVBuilder(config)
ohlcv_data = builder.build(rng)

# Access data
btc_data = ohlcv_data["CUSTOM1"]
print(f"Generated {len(btc_data)} candles")
```

### Regime Analysis

Access regime information from return generation:

```python
from marketforge.core.returns import ReturnGenerator

generator = ReturnGenerator(config)
result = generator.generate(rng)

# Regime indices: 0=trend_up, 1=trend_down, 2=range, 3=high_vol, 4=crash
regime_indices = result.regime_indices
volatilities = result.volatilities
```

## Examples

### Example 1: Generate 1 Month of Crypto Data

```bash
# January 2024 (Unix timestamps)
python -m marketforge \
    --output-dir ./data/crypto_jan2024 \
    --from 1704067200 \
    --to 1706745599 \
    --market crypto \
    --seed 42 \
    --anomalies spikes,flash_crash \
    --timeframes m1,m5,H1,D1
```

### Example 2: Generate All Markets with Anomalies

```bash
python -m marketforge \
    --output-dir ./data/all_markets \
    --from 1704067200 \
    --to 1704153600 \
    --market all \
    --seed 42 \
    --anomalies gaps,spikes \
    --threads 8 \
    --batch-size 25
```

### Example 3: High-Performance Generation

```bash
# Large dataset with parallel processing
python -m marketforge \
    --output-dir ./data/large_dataset \
    --from 946681200 \
    --to 1767221999 \
    --market all \
    --seed 42 \
    --threads 16 \
    --batch-size 30 \
    --timeframes m1,m5,m15,m30,H1,H4,D1
```

### Example 4: Minimal Generation (Testing)

```bash
# Small dataset for testing
python -m marketforge \
    --output-dir ./data/test \
    --from 1704067200 \
    --to 1704070800 \
    --market crypto \
    --seed 42 \
    --timeframes m1,H1 \
    --batch-size 10 \
    --threads 1
```

### Example 5: Comprehensive Generation with All Features

```bash
# Generate all markets with anomalies, parallel processing, and progress tracking
python -m marketforge \
    --output-dir ./data \
    --from 946681200 \
    --to 1767221999 \
    --seed 42 \
    --anomalies gaps,spikes \
    --market all \
    --threads 8 \
    --batch-size 10 \
    --progress
```

## Contributing

Contributions are welcome! Areas for improvement:

- Additional market types
- More anomaly types
- Custom volume models
- Additional timeframes
- Performance optimizations
- Documentation improvements

### Development Setup

```bash
# Install in development mode
pip install -e ".[dev]"

# Run type checking
mypy marketforge
```

## License

AGPL-3.0 License - see LICENSE file for details.

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check existing documentation
- Review code examples in the repository

---

**Version**: 1.0.0  
**Python**: 3.10+  
**License**: AGPL-3.0

