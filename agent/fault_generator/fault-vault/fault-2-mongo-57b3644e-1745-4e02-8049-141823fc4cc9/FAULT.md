# Catalogue Products by Category Sorted Incorrectly

## Title
Catalogue Products by Category Sorted Incorrectly

## Description
In `catalogue/server.js`, the `/products/:cat` endpoint was modified to reverse the array of products before returning it to the client.

## Symptom
When users browse products by a specific category, the items will be displayed in reverse alphabetical order (Z-A) instead of the expected alphabetical order (A-Z).

## Root cause
The logic in the `/products/:cat` endpoint was changed to `res.json(products.reverse())`. Although the database query correctly sorts the products by name in ascending order (`.sort({ name: 1 })`), the `.reverse()` method flips the array before it is sent in the response, resulting in a descending sort order.

## Fix
Revert the change in `catalogue/server.js` for the `/products/:cat` endpoint to return the products in their original sorted order:
```javascript
// products in a category
app.get('/products/:cat', (req, res) => {
    if(mongoConnected) {
        collection.find({ categories: req.params.cat }).sort({ name: 1 }).toArray().then((products) => {
            if(products) {
                res.json(products);
            } else {
                res.status(404).send('No products for ' + req.params.cat);
            }
        }).catch((e) => {
            req.log.error('ERROR', e);
            res.status(500).send(e);
        });
    } else {
        req.log.error('database not available');
        res.status(500).send('database not avaiable');
    }
});