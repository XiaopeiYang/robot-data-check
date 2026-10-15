# Development setup

## Basics

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs uv to ~/.local/bin
source ~/.local/bin/env
uv sync                                           # package + dev group (viewer, video deps)
uv run pytest -q                                  # synthetic data only, no network
uv run ruff check . && uv run ruff format --check .
```

Set `HF_TOKEN` for anything that talks to the Hub at scale (census, studies); unauthenticated
requests are rate limited.

## Browser end-to-end tests (optional)

`tests/e2e/` drives the episode viewer in headless Chromium. It is skipped unless
`ROBOCHECK_E2E=1` is set, so CI and the default test run do not need a browser.

1. Install Playwright and its headless Chromium (no root needed):

   ```bash
   uv sync --group e2e
   uv run --group e2e playwright install chromium-headless-shell
   ```

2. If Chromium fails to start with `error while loading shared libraries` (common on
   minimal WSL / container images) and you cannot use `sudo`, fetch the missing libraries
   as packages and unpack them locally instead of installing them system-wide:

   ```bash
   mkdir -p ~/.cache/robocheck-libs/debs && cd ~/.cache/robocheck-libs/debs
   apt-get download libnspr4 libnss3 libasound2t64   # libasound2 on older Ubuntu
   for d in *.deb; do dpkg -x "$d" ~/.cache/robocheck-libs; done
   export LD_LIBRARY_PATH=~/.cache/robocheck-libs/usr/lib/x86_64-linux-gnu
   ```

   `ldd <path to chrome-headless-shell> | grep "not found"` lists what is still missing.
   With `sudo`, `uv run --group e2e playwright install-deps chromium` does the same.

3. Run:

   ```bash
   ROBOCHECK_E2E=1 uv run --group e2e pytest tests/e2e -q
   ```

   The tests find Playwright's headless shell in `~/.cache/ms-playwright`; set
   `CHROMIUM_PATH` to use another binary.

## Video decoding

`engine/video.py` needs the `video` extra (`av`, `numpy`; already in the dev group). PyAV's
bundled FFmpeg decodes AV1 (dav1d) but has no HTTPS support, so Hub videos are read through
`RangeFile` (HTTP range requests from Python).
