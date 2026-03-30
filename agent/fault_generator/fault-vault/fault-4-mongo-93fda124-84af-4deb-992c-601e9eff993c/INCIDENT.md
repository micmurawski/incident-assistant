# Product Search Failing

## Description
Users are reporting that they are unable to search for products using the search bar on the website. When attempting to search, the page either hangs or displays an error. Monitoring shows an increase in 500 Internal Server Errors originating from the catalogue service, specifically on the `/search` endpoint. Other catalogue functions, such as viewing categories or individual products, appear to be working normally.