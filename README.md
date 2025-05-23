# Effortless Eighty Strava Client

A Firebase Functions backend for interfacing with the Strava API, providing authentication and data retrieval services for the Effortless Eighty application.

## Features

- Strava OAuth 2.0 authentication flow
- Access token management (acquisition and refresh)
- Secure API for fetching athlete activities and zones
- Cross-Origin Resource Sharing (CORS) support
- Comprehensive error handling and logging

## Prerequisites

- [Python 3.13](https://www.python.org/downloads/)
- [Firebase CLI](https://firebase.google.com/docs/cli)
- Firebase project created in the [Firebase Console](https://console.firebase.google.com/)
- [Strava API application](https://www.strava.com/settings/api)

## Local Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/effortless-eighty-strava-client.git
cd effortless-eighty-strava-client
```

2. Set up a Python virtual environment:
```bash
cd functions
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Create a `.env` file in the `functions` directory with your Strava API credentials:
```
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
EXPECTED_REDIRECT_URI=http://localhost:3000/exchange_token
```

4. Run the Firebase emulator:
```bash
firebase emulators:start
```

## Deployment

1. Log in to Firebase:
```bash
firebase login
```

2. Configure your Strava API credentials in Firebase:
```bash
firebase functions:config:set strava.client_id="your_client_id" strava.client_secret="your_client_secret" strava.redirect_uri="https://yourdomain.com/exchange_token"
```

3. Deploy to Firebase:
```bash
firebase deploy
```

## API Endpoints

### Authentication

#### `GET /api/auth-url`
Generate a Strava authorization URL.

Query parameters:
- `redirect_uri` (optional): Override the default redirect URI
- `scopes` (optional): Comma-separated list of Strava API scopes (default: `read,activity:read_all,profile:read_all`)

#### `POST /api/exchange-token`
Exchange an authorization code for access and refresh tokens.

Request body:
```json
{
  "code": "strava_authorization_code"
}
```

#### `POST /api/refresh-token`
Refresh an expired access token.

Request body:
```json
{
  "refresh_token": "strava_refresh_token"
}
```

### Data Retrieval

#### `GET /api/activities`
Fetch athlete activities.

Headers:
- `Authorization: Bearer access_token`

Query parameters:
- All query parameters are passed directly to the Strava API

#### `GET /api/athlete/zones`
Fetch athlete zones.

Headers:
- `Authorization: Bearer access_token`

### Debug

#### `GET /api/debug-info`
Get server configuration information (no sensitive data).

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add some amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## License

[MIT](LICENSE)
