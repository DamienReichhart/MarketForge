import subprocess
import sys

# Modules that take a large share of a second to import and that generating
# data does not need. `import marketforge` runs on every CLI call, so each one
# imported eagerly is paid by every user (scipy.stats alone doubled it).
HEAVY_AND_OPTIONAL = ["scipy.stats", "matplotlib", "sklearn"]


def test_importing_the_package_does_not_import_heavy_optional_modules():
    code = (
        "import sys, marketforge; "
        f"print(','.join(m for m in {HEAVY_AND_OPTIONAL!r} if m in sys.modules))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    ).stdout.strip()
    assert loaded == "", f"`import marketforge` imports {loaded}; import it where it is used"
