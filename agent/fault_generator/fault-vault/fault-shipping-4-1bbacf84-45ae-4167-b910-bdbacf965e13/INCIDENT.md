# Shipping Service Memory Exhaustion and Instability

## Description

The shipping service is experiencing steadily increasing memory consumption, eventually leading to OutOfMemory errors and service restarts. Users may experience slow response times or failures when trying to calculate shipping costs or search for cities during checkout. Monitoring shows a continuous upward trend in heap usage that does not recover after garbage collection.