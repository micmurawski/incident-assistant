# Fault: Login Endpoint Performance Degradation

## Description
An artificial delay of 5 seconds has been introduced in the `/login` endpoint of `user/server.js`. This delay occurs after a user is found in the database but before their password is validated.

## Symptom
Users will experience a significant delay (approximately 5 seconds) when attempting to log in, regardless of whether their credentials are correct or incorrect. The login process will appear slow and unresponsive.

## Root Cause
The `app.post('/login')` handler in `user/server.js` now includes an `await new Promise(resolve => setTimeout(resolve, 5000));` statement. This forces a 5-second pause in the execution flow for every login attempt, leading to a performance regression.

## Fix
Remove the artificial delay from the `/login` endpoint in `user/server.js`. Specifically, remove the line:
`await new Promise(resolve => setTimeout(resolve, 5000));`