Title: Broken Rating Update Operation

Description:
In `ratings/html/src/Controller/RatingsApiController.php`, the `updateRatingForSKU` method call within the `put` method (lines 64) was changed to `nonExistentMethod`.

Symptom:
When a user attempts to rate a product that has already been rated, the rating update will fail, resulting in a 500 Internal Server Error for the rating service. The front-end application might show a generic error or the rating might not update.

Root cause:
The `ratingsService` object does not have a method named `nonExistentMethod`. This will cause a fatal PHP error when the code attempts to call this undefined method, leading to an unhandled exception and a 500 HTTP response.

Fix:
Change `nonExistentMethod` back to `updateRatingForSKU` in `ratings/html/src/Controller/RatingsApiController.php` on line 64.