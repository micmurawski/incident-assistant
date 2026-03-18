# Fault: Login Always Fails Due to Wrong Field Name in Query

## Description
Changed the login endpoint query in `user/server.js` to use `username` instead of `name` when searching for users in MongoDB. The `/register` endpoint correctly stores users with a `name` field, but the `/login` endpoint now queries using `username`, causing a mismatch.

## Symptom
All login attempts fail with HTTP 404 "name not found" error, even for valid registered users. Users cannot log in to the application.

## Root Cause
The login endpoint queries MongoDB using `{ username: req.body.name }` but users are stored with the field name `name`. Since the query field doesn't match the stored field, no user is ever found, causing every login attempt to return "name not found".

## Fix
Change the login query back to use `name` instead of `username`:

```javascript
usersCollection.findOne({
    name: req.body.name,
}).then((user) => {
```
