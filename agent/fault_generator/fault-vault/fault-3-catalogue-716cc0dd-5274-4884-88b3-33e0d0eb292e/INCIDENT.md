# Catalogue Service Database Connection Failure

## Description
The catalogue service is unable to connect to its MongoDB database. Users are unable to view products, categories, or search for items. The catalogue service is returning 500 Internal Server Error responses for all product-related requests.

## Symptoms
- Users see empty product lists or error messages when browsing the shop.
- The catalogue service logs show repeated MongoDB connection errors.
- The `/health` endpoint of the catalogue service reports `mongo: false`.
- High rate of HTTP 500 errors from the catalogue service.
