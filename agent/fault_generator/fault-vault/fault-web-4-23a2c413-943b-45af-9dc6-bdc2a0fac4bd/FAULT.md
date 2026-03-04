# Fault: Corrupted Shipping Order ID

## Description

The `order_id` column in the `shipping` table of the `mysql` database has been changed from `VARCHAR(50)` to `VARCHAR(1)`. This change was made in the SQL script `mysql/scripts/10-shipping.sql`.

## Symptom

The application will fail to properly track shipping orders. When a new order is created, the `order_id` will be truncated to a single character, leading to data loss and making it impossible to correlate shipments with orders. This will manifest as users being unable to see their order status, and administrators being unable to manage shipments.

## Root cause

The `order_id` column's data type is too small to store the full order identifier. This causes the database to truncate the value, leading to data corruption.

## Fix

To fix this issue, revert the change in `mysql/scripts/10-shipping.sql` by changing the `order_id` column type back to `VARCHAR(50)`. After correcting the script, the database will need to be re-initialized to apply the correct schema.
