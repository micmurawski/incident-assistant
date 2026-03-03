Title: Login always fails due to incorrect password

Description: In `user/server.js`, line 129, the condition `user.password == req.body.password` was changed to `false`. This means that the password comparison will always fail, preventing any user from logging in successfully.

Symptom: Users will be unable to log in to the Robot Shop application, even with correct credentials. The login attempt will consistently return an "incorrect password" error.

Root cause: The hardcoded `false` value in the password comparison logic at `user/server.js:129` causes all login attempts to be rejected, regardless of the actual password provided.

Fix: Revert the change on `user/server.js:129` from `if(false)` back to `if(user.password == req.body.password)`.