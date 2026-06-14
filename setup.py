# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Setup script for MarketForge.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="marketforge",
    version="2.0.0",
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
        "License :: OSI Approved :: MIT License",
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
            "pytest>=8.0.0",
            "arch>=6.3.0",
            "statsmodels>=0.14.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "marketforge=marketforge.cli.parser:main",
        ],
    },
)

