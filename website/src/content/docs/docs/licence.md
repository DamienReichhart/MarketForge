---
title: "Licence"
description: "What the Apache-2.0 licence lets you do with MarketForge and with the data it generates."
---

MarketForge 4.0 and later are released under the **Apache License, version 2.0**. Versions before 4.0 were released under the AGPL-3.0-or-later and stay under it.

## Can I use it at work, in closed-source code?

Yes. You can import MarketForge in a proprietary backtester, a training pipeline or a hosted service, without publishing your code. Apache-2.0 asks you to keep the licence and copyright notices when you redistribute MarketForge itself, modified or not, and to say which files you changed.

## Who owns the data it generates?

You do. The candles MarketForge generates are not covered by its licence: use, sell or publish them however you like. They are synthetic. They are not the price history of any real instrument, and the symbols are labels for parameter sets.

## Can I copy the examples from this site?

Yes. The documentation's code examples are part of the repository and under the same Apache-2.0 licence, so you can paste them into any project.

## What about the software MarketForge uses?

Its dependencies keep their own licences: permissive ones (BSD, MIT, Apache-2.0 and the like), and the MPL-2.0 for part of tqdm, which binds only changes to tqdm's own files. A release is blocked if a dependency comes under any other licence. The wheel and the source package on PyPI contain only MarketForge's code: pip installs NumPy, pandas, Numba and the others from their own packages, with their own licence files. If you ship an environment with MarketForge in it, such as a container image or a frozen application, each [GitHub release](https://github.com/DamienReichhart/MarketForge/releases) has a `third-party-licenses.txt` with the licence and notice texts of every runtime dependency.

This website's code and fonts come from third parties too, and so does the [playground](../../playground/): Pyodide, CPython compiled to WebAssembly, and the NumPy, pandas and pyarrow it runs, served by this site. Their licences and notices are in the site's [third-party licences](../../third-party-licenses.txt).

## Is there a warranty?

No. MarketForge is provided "as is", without warranty of any kind (sections 7 and 8 of the licence). Nothing it produces is financial advice.

The full text is in [LICENSE](https://github.com/DamienReichhart/MarketForge/blob/main/LICENSE).
