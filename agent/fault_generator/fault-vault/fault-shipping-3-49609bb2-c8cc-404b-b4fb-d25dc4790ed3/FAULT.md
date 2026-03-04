Title: Shipping service latency
Description: Introduced a 5-second delay in the `getDistance` method of `shipping/src/main/java/com/instana/robotshop/shipping/Calculator.java`.
Symptom: Users will experience a significant delay (at least 5 seconds) when requesting shipping calculations. The shipping service will appear slow or unresponsive.
Root cause: An artificial delay (Thread.sleep(5000)) was added to the distance calculation logic, intentionally increasing the processing time for every shipping request.
Fix: Remove the `try-catch` block containing `Thread.sleep(5000)` from the `getDistance` method in `shipping/src/main/java/com/instana/robotshop/shipping/Calculator.java`.