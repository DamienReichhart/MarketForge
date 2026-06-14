# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Entry point for the MarketForge CLI.

Run with: marketforge [options]

Example:
    marketforge \
        --output-dir ./data \
        --market crypto \
        --from 1704067200 \
        --to 1704153600 \
        --assets BTC,ETH,SOL \
        --start-prices 50000,3000,120 \
        --volatility 0.02 \
        --drift 0.0001 \
        --seed 42 \
        --correlations 0.8,0.6,0.7
"""

from marketforge.cli.parser import main

if __name__ == "__main__":
    main()

