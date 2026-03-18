# Fault: Swapped Latitude and Longitude in Shipping Cost Calculation

## Description
Swapped the `homeLatitude` and `homeLongitude` values in the `caclc` method of `shipping/src/main/java/com/instana/robotshop/shipping/Controller.java`. The original values were `51.164896` and `7.068792` respectively, and they were changed to `7.068792` and `51.164896`.

## Symptom
Shipping costs are calculated incorrectly. Customers will see unexpectedly high or low shipping costs depending on their location, as the distance is now calculated from a location in Somalia instead of Germany.

## Root Cause
The `homeLatitude` and `homeLongitude` variables were swapped, causing the distance calculation to use an incorrect origin point. This results in incorrect distance values and consequently incorrect shipping costs.

## Fix
Revert the change in `shipping/src/main/java/com/instana/robotshop/shipping/Controller.java` lines 110-111:
```java
        double homeLatitude = 51.164896;
        double homeLongitude = 7.068792;
```
