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
Setup script for MarketForge.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="marketforge",
    version="1.0.0",
    author="REICHHART Damien",
    description="A professional-grade synthetic OHLCV data generator",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/DamienReichhart/MarketForge",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.10",
    install_requires=[
        "numpy>=2.4.0",
        "scipy>=1.16.3",
        "pandas>=2.3.3",
        "click>=8.3.1",
        "tqdm>=4.67.1",
    ],
    extras_require={
        "dev": [
            "mypy>=1.19.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "marketforge=marketforge.cli.parser:main",
        ],
    },
)

