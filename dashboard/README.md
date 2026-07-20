# FerroTwin dashboard

This is a dependency-free operations dashboard, so it can be served from any static host.

For local development, use a terminal in the repository root:

```powershell
func start --cors http://localhost:8080
python -m http.server 8080 --directory dashboard
```

Open `http://localhost:8080`, choose **Connect API**, and use `http://localhost:7071/api` plus a local Function key. The Function key is stored only in session storage and is sent in the `x-functions-key` header.
