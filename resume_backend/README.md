# Resume Backend (FastAPI)

This service runs a FastAPI app located at `src/api/main.py`.

## Prerequisites

- Python 3.12+
- `pip` available for that Python interpreter

## Install dependencies

From this directory:

```bash
python -m pip install -r requirements.txt
```

> Note: In some environments, `pip` may fall back to a user install (e.g. `~/.local/`).
> That is fine as long as you run uvicorn using the same `python` environment.

## Run the API (dev)

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 3001
```

If you previously ran `uvicorn ...` directly and hit `ModuleNotFoundError: No module named 'fastapi'`,
it usually means `uvicorn` is using a Python environment where dependencies were not installed.
Using `python -m uvicorn ...` helps ensure the same interpreter is used.
