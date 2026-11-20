# DataSleuth

DataSleuth is under development. This repository currently contains an early
foundation, not a working scanner. See
[`Project_Docs/IMPLEMENTATION_STATUS.md`](Project_Docs/IMPLEMENTATION_STATUS.md)
for progress and limitations and `Project_Docs/` for the specifications.

## Windows development (foundation only)

Prerequisites: Python 3.12, a supported Node.js LTS release, and npm. PostgreSQL
and Redis will be required for later foundation work. The Compose file is not
yet verified.

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
Set-Location backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another PowerShell terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

The API process health endpoint is `http://127.0.0.1:8000/health`. Run backend
tests from `backend` with `python -m pytest` and lint with `ruff check .`.
Run `npm run build` from `frontend`. Do not expose this development build to
untrusted networks; authentication and authorization are not implemented.
