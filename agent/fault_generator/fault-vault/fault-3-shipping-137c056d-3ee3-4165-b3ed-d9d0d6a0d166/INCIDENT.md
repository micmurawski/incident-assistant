# Shipping Service Unreachable

## Description
The shipping service is currently unreachable. Users are unable to calculate shipping costs or complete their orders. Monitoring shows that the shipping service is failing to respond to requests, and error rates for the checkout process have spiked.

## Symptoms
- Users cannot see shipping options or costs during checkout.
- Checkout process fails when attempting to calculate shipping.
- High error rates observed in the API gateway for requests routed to the shipping service.
- The shipping service pods are running, but the service endpoint is not returning successful responses.