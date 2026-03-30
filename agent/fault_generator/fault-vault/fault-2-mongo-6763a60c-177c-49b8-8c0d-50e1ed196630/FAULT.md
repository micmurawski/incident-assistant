# Missing Text Index in MongoDB

## Description
The creation of the full text index on the `products` collection in the `catalogue` database was commented out in the MongoDB initialization script (`mongo/catalogue.js`).

## Symptom
Users will not be able to search for products using the search bar. The `/search/:text` endpoint in the catalogue service will fail with a 500 Internal Server Error because it relies on the `$text` operator, which requires a text index to be present on the collection.

## Root cause
The `catalogue.js` script is used to initialize the MongoDB database when the container starts. By commenting out the `db.products.createIndex` block for the text index, the index is never created. When the catalogue service attempts to execute a query using `{ '$text': { '$search': req.params.text } }`, MongoDB throws an error because no text index exists to support the query.

## Fix
Uncomment the text index creation block in `mongo/catalogue.js`:
```javascript
// full text index for searching
db.products.createIndex({
    name: "text",
    description: "text"
});
```
Then, rebuild and restart the MongoDB container to apply the initialization script.