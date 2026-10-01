# Ridehail backend

A Python/Django REST API foundation for a ride-hailing MVP.

## Requirements

- Python 3.11+

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/`.

## Authentication and ride-request endpoints

- `POST /api/auth/register/` creates a rider account and returns a token.
- `POST /api/auth/login/` accepts `username` and `password` and returns a token.
- `POST /api/auth/logout/` revokes the current token.
- `POST /api/rides/` creates an authenticated rider's ride request.
- `GET /api/rides/{uuid}/` retrieves the authenticated rider's ride status and trip details.
- `/admin/` provides an operator interface after creating a staff user with `python manage.py createsuperuser`.

Send the returned token on protected API requests using the header
`Authorization: Token <token>`. Riders can only retrieve rides they created.

Example ride request body:

```json
{
  "pickup_address": "Central Station",
  "pickup_latitude": 51.5072,
  "pickup_longitude": -0.1276,
  "destination_address": "City Airport",
  "destination_latitude": 51.47,
  "destination_longitude": -0.4543
}
```

This is a local development foundation, not ready to expose publicly: rate limiting,
production secret configuration, fare calculation, and driver matching are not
implemented yet. Token authentication must be used over HTTPS in deployment.

## Tests

```powershell
python manage.py test
```

## Manual API smoke test (PowerShell)

Start the server with `python manage.py runserver`, then in another PowerShell
window register a test rider, create a ride, and retrieve it:

```powershell
$username = "test-rider-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
$registration = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/auth/register/ `
  -ContentType application/json `
  -Body (@{
    username = $username
    password = "RidehailTest!2026"
  } | ConvertTo-Json)

$headers = @{ Authorization = "Token $($registration.token)" }
$ride = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/rides/ `
  -Headers $headers `
  -ContentType application/json `
  -Body (@{
    pickup_address = "Central Station"
    pickup_latitude = 51.5072
    pickup_longitude = -0.1276
    destination_address = "City Airport"
    destination_latitude = 51.47
    destination_longitude = -0.4543
  } | ConvertTo-Json)

Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/api/rides/$($ride.id)/" `
  -Headers $headers
```

The registration and ride are saved in the local development database. Use a
throwaway test account; to clear local test data, delete the development
`db.sqlite3` file and rerun `python manage.py migrate`.
