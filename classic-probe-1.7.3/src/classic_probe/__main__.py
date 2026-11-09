"""``python -m classic_probe``: the same commands as ``classic-probe`` (cli.py). No command sends a
request."""

from classic_probe.cli import entrypoint

if __name__ == "__main__":
    entrypoint()
