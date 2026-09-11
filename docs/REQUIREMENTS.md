# Product brief: internal link shortener

Fallback requirements for the demo. Deliberately a little vague so the planner has to refine them.

We need a small internal service engineers can use to create short links for long URLs in docs and Slack.

- Anyone holding an API key can create a short link for a valid http(s) URL and get back a short code.
- Visiting /<code> redirects to the original URL.
- Links can optionally expire. Expired links must not redirect.
- We want to know how often each link has been used.
- Someone needs to be able to list the links that exist, with paging, because there will be thousands.
- Small Python service we can run in a container. Storage can be simple for now, but we plan to move it to DynamoDB, so keep storage behind an interface.
- Invalid input should produce clear 4xx errors, never a 500.
