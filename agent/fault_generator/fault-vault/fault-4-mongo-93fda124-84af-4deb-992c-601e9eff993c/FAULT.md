# Missing Text Index in MongoDB

## Description
The creation of the full-text index on the `products` collection in the `catalogue` database was commented out in the MongoDB initialization script (`mongo/catalogue.js`).

## Symptom
Users will not be able to search for products using the search bar. The catalogue service will return a 500 Internal Server Error when the `/search/:text` endpoint is hit, because the `$text` operator requires a text index to be present on the collection.

## Root cause
The `catalogue` service uses the `$text` operator in its MongoDB query to perform text searches. This operator relies on a text index existing on the fields being searched. Since the index creation was commented out in the initialization script, the index is never created, causing the query to fail.

## Fix
Uncomment the text index creation block in `mongo/catalogue.js`:
```javascript
// full text index for searching
db.products.createIndex({
    name: "text",
    description: "text"
});
```
Then, rebuild the `robot-shop-mongo` image and restart the MongoDB pod to apply the initialization script. Alternatively, manually create the index in the running MongoDB instance.