# Fault: Catalogue Service Search Always Returns Empty

## Description
Modified the `/search/:text` endpoint in `catalogue/server.js` to always return an empty array `[]` instead of the actual search results (`hits`) returned by the MongoDB query.

## Symptom
When users attempt to search for products using the search bar, they will always see no results, regardless of whether the search term matches existing products in the database. The frontend will display an empty list or a "no results found" message.

## Root Cause
The `collection.find({ '$text': { '$search': req.params.text }}).toArray().then((hits) => { ... })` block in the `/search/:text` endpoint has been altered to call `res.json([])` instead of `res.json(hits)`. This discards the valid search results and sends an empty response to the client.

## Fix
Revert the change in the `/search/:text` endpoint in `catalogue/server.js` to return the actual `hits` array:

```javascript
collection.find({ '$text': { '$search': req.params.text }}).toArray().then((hits) => {
    res.json(hits);
}).catch((e) => {
    req.log.error('ERROR', e);
    res.status(500).send(e);
});