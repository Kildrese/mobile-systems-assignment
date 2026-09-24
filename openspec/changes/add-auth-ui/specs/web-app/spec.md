## REMOVED Requirements

### Requirement: Placeholder home page
**Reason**: `/` becomes the signed-in home page of the web UI, which reads the session from the database, so it can no longer be static or render without the database.
**Migration**: See `web-auth-ui` ("Signed-in home page"). The API reference stays public at `/docs`, and the home page links to it.
