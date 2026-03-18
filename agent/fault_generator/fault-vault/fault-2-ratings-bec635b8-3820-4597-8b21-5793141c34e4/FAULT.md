# Fault: Inverted Comparison Operator in Ratings Controller

## Description
Changed the comparison operator in `ratings/html/src/Controller/RatingsApiController.php` from `===` equality check to `!==` inequality check when determining whether a product has been rated yet.

## Symptom
- When submitting a rating for a product that has NOT been rated before (avg_rating = 0), the API will attempt to update a non-existent record, causing a database error and returning HTTP 500.
- When submitting a rating for a product that HAS been rated, the API will attempt to insert a new record instead of updating the existing one, potentially creating duplicate entries or failing.
- Users will see "Unable to update rating" error messages.

## Root Cause
The conditional logic is inverted. The code originally checked `if (0 === $rating['avg_rating'])` to determine if a product is not yet rated (avg_rating = 0 means no ratings). This was changed to `if (0 !== $rating['avg_rating'])`, which causes the opposite code path to execute.

## Fix
Revert the comparison operator in `ratings/html/src/Controller/RatingsApiController.php` line 58:
- Change: `if (0 !== $rating['avg_rating']) {`
- To: `if (0 === $rating['avg_rating']) {`
