# Title: Inverted Rating Score

## Description
Changed the rating score calculation in `ratings/html/src/Controller/RatingsApiController.php` to invert the score given by the user. A 5-star rating becomes a 1-star rating, and a 1-star rating becomes a 5-star rating.

## Symptom
Users will notice that when they submit a high rating (e.g., 5 stars), the average rating of the product decreases instead of increasing. Conversely, submitting a low rating (e.g., 1 star) will increase the average rating.

## Root cause
The score is inverted using the formula `6 - $score` before it is saved to the database or used in the average calculation. This causes the opposite effect of what the user intended.

## Fix
Revert the score calculation in `ratings/html/src/Controller/RatingsApiController.php` line 46:
- Change: `$score = min(max(1, 6 - $score), 5);`
- To: `$score = min(max(1, $score), 5);`
