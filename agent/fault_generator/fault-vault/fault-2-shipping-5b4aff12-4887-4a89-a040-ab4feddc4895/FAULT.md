# Fault: Incorrect Shipping Cost Calculation Due to Integer Division

## Description
Changed the shipping cost calculation in the Controller.java file from using `Math.rint()` for proper rounding to using integer cast with division. The line:
```java
double cost = Math.rint(distance * 5) / 100.0;
```
was changed to:
```java
double cost = (int)(distance * 5) / 100.0;
```

## Symptom
Shipping costs are significantly incorrect. For distances under 20km, the cost always returns 0.0 instead of the proper rounded value. For example:
- Distance 15km: Expected cost = 0.75, Actual = 0.0
- Distance 25km: Expected cost = 1.25, Actual = 1.0
- Distance 50km: Expected cost = 2.50, Actual = 2.0

The cost is always rounded down to the nearest integer value due to the integer cast before division.

## Root Cause
The integer cast `(int)(distance * 5)` truncates the decimal portion of the multiplication result before dividing by 100.0. This causes all shipping costs to be significantly lower than they should be, effectively applying floor() rounding instead of proper nearest-integer rounding.

## Fix
Revert the change in shipping/src/main/java/com/instana/robotshop/shipping/Controller.java line 123:
```java
double cost = Math.rint(distance * 5) / 100.0;
```
