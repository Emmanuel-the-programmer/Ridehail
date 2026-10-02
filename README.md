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

The API is available at `http://127.0.0.1:8000/api/`. The ASGI development
server also provides authenticated ride updates over WebSockets.

## Authentication and ride-request endpoints

- `POST /api/auth/register/` creates a rider account and returns a token.
- `POST /api/auth/login/` accepts `username` and `password` and returns a token.
- `POST /api/auth/logout/` revokes the current token.
- `POST /api/rides/` creates an authenticated rider's ride request.
- `GET /api/rides/{uuid}/` retrieves the authenticated rider's ride status and trip details.
- `POST /api/driver/location/` updates an approved driver's location and availability.
- `GET /api/driver/rides/` lists unassigned ride requests within 10 km of an online driver's location, nearest first.
- `POST /api/driver/rides/{uuid}/accept/` accepts a nearby ride.
- `POST /api/driver/rides/{uuid}/status/` advances an assigned ride through its trip statuses.
- `POST /api/driver/rides/{uuid}/cash-payment/confirm/` records cash received by the assigned driver after trip completion.
- `ws://127.0.0.1:8000/ws/rides/{uuid}/` streams ride updates to its rider and assigned driver.
- `/admin/` provides an operator interface after creating a staff user with `python manage.py createsuperuser`.

Send the returned token on protected API requests using the header
`Authorization: Token <token>`. Riders can only retrieve rides they created.

## Driver onboarding and matching

Register a user account, then have an operator create a `DriverProfile` for that
account in Django Admin and mark it approved. Driver-profile creation and approval
are deliberately operator-controlled; registering a rider account does not grant
driver privileges. Once approved, the driver can post their location and go
online. The nearby-ride endpoint returns unassigned requests within a fixed 10 km
pickup radius. Accepting a request assigns it to that driver and takes them
offline. The assigned driver advances status in order:
`accepted` → `driver_arriving` → `arrived` → `in_progress` → `completed`.

For a manual driver test, first create a rider and ride using the rider steps
below. Create and approve a `DriverProfile` for a separate test account in
`/admin/`, then log in as that account to obtain its token. Use its token and
pickup-area coordinates in these PowerShell commands:

```powershell
$driverHeaders = @{ Authorization = "Token DRIVER_TOKEN_HERE" }
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/driver/location/ `
  -Headers $driverHeaders `
  -ContentType application/json `
  -Body (@{
    latitude = 51.5000
    longitude = -0.1000
    is_available = $true
  } | ConvertTo-Json)

Invoke-RestMethod `
  -Method Get `
  -Uri http://127.0.0.1:8000/api/driver/rides/ `
  -Headers $driverHeaders

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/driver/rides/RIDE_UUID_HERE/accept/" `
  -Headers $driverHeaders

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/driver/rides/RIDE_UUID_HERE/status/" `
  -Headers $driverHeaders `
  -ContentType application/json `
  -Body (@{ status = "driver_arriving" } | ConvertTo-Json)
```

Repeat the final status request with `arrived`, `in_progress`, then `completed`.
After completing the ride, the assigned driver can confirm that cash was
received:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/driver/rides/RIDE_UUID_HERE/cash-payment/confirm/" `
  -Headers $driverHeaders
```

Rides default to cash with payment status `due`. Only the approved driver
assigned to a completed ride can confirm cash, and confirmation cannot be
repeated. This records the driver's confirmation and timestamp; it does not
calculate the fare, record an amount, or process an online payment.

Driver matching still uses a polling request to list offers. Ride status and
cash-payment changes are broadcast over WebSockets. To connect, open the ride
WebSocket and send `{"token":"YOUR_API_TOKEN"}` as the first JSON message; the
server sends the current ride and then pushes updates. Only the ride's rider
and assigned driver can subscribe.

For local development, Channels uses an in-memory channel layer, so realtime
events work in a single server process. For multi-process deployments, set
`CHANNEL_REDIS_URL` to a Redis connection URL so events are shared between
workers. The WebSocket API token is sent in the first message rather than the
URL to avoid putting credentials in browser history or URL logs.

Example browser client:

```javascript
const socket = new WebSocket(`ws://127.0.0.1:8000/ws/rides/${rideId}/`);
socket.addEventListener("open", () => {
  socket.send(JSON.stringify({ token: riderToken }));
});
socket.addEventListener("message", ({ data }) => {
  const update = JSON.parse(data);
  console.log(update.ride.status);
});
```

Driver matching still uses a database scan and is intended for a small
development pilot, not a production dispatch workload. Production will need
scalable geospatial queries, live driver-location delivery, notifications, and
operational safeguards.

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

This is a local development foundation, not ready to expose publicly: rate
limiting, production secret configuration, fare calculation, payment amount
tracking, and online payments are not implemented yet. Token authentication
and WebSockets must use HTTPS/WSS in deployment.

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
