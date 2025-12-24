# MarketForge
# Copyright (C) 2026 REICHHART Damien
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Entry point for the MarketForge CLI.

Run with: python -m marketforge [options]

Example:
    python -m marketforge \
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

