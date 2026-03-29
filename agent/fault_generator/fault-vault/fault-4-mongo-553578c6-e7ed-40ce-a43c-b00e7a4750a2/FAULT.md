# Title: Missing text index in MongoDB catalogue database

# Description:
Commented out the creation of the full text index on the `name` and `description` fields in `mongo/catalogue.js`.

# Symptom:
Users will experience errors when trying to search for products. The `/search/:text` endpoint in the catalogue service will return a 500 Internal Server Error.

# Root cause:
The catalogue service uses the `$text` operator in its MongoDB query to search for products. This operator requires a text index to be present on the collection. Since the index creation was commented out, MongoDB throws an error when the query is executed, which is caught by the service and results in a 500 response.

# Fix:
Uncomment the text index creation in `mongo/catalogue.js` and recreate the database or manually create the index in the existing database.
