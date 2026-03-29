# Ratings Service Performance Regression

## Title
Ratings Service Performance Regression

## Description
A trigger was added to the `ratings` table in the `mysql` service that introduces a 2-second delay before every insert operation.

## Symptom
Users will experience a noticeable delay when submitting a new rating for a product. The overall performance of the ratings service will degrade, especially under load, as database connections are held open longer.

## Root cause
The `slow_rating_insert` trigger in `mysql/scripts/20-ratings.sql` executes `DO SLEEP(2);` before each insert on the `ratings` table, artificially inflating the response time of the database operation.

## Fix
Remove the `slow_rating_insert` trigger from `mysql/scripts/20-ratings.sql` and drop the trigger from the database.