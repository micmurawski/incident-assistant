# Product Search Functionality Broken

## Description
Users are reporting that the product search functionality on the website is completely broken. When attempting to search for any product using the search bar, the application returns an error and no results are displayed. Monitoring shows a spike in 500 Internal Server Errors originating from the catalogue service's `/search` endpoint. Other catalogue features, such as browsing by category or viewing individual products, appear to be functioning normally.