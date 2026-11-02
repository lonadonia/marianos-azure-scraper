> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/rate-limits.md).

# Rate Limits

Learn about Web Scraper API rate limits, job submission speeds, and how domain success rates affect your limits.

## Intro

Web Scraper API user account comes with a specific job submission rate limit, tailored to your plan. These limits are designed to accommodate your monthly subscription needs effectively.

## Rate limits

The rate at which you can submit jobs depends on your plan size. Refer to the table below for a breakdown of rate limits for regular and enterprise plans:

<table><thead><tr><th width="203">Plan</th><th width="187">Results (maximum)</th><th width="179">Total jobs/s</th><th>Rendered jobs/s</th></tr></thead><tbody><tr><td>Free trial</td><td>2,000</td><td>10</td><td>3</td></tr><tr><td>Micro</td><td>98,000</td><td>50</td><td>13</td></tr><tr><td>Starter</td><td>220,000</td><td>50</td><td>13</td></tr><tr><td>Advanced</td><td>622,500</td><td>50</td><td>13</td></tr><tr><td>Venture</td><td>1,350,000</td><td>50</td><td>13</td></tr><tr><td>Business</td><td>3,330,000</td><td>100</td><td>25</td></tr><tr><td>Corporate</td><td>8,000,000</td><td>100</td><td>25</td></tr><tr><td>Custom +</td><td>Custom</td><td>Custom</td><td>Custom</td></tr></tbody></table>

## Getting rate limit information

Whenever you submit a job to our system, we will send you the rate limit information in the response headers. The header names will be structured like `x-ratelimit-limit_name-limit` and `x-ratelimit-limit_name-remaining`. The former denotes the total limit value, while the latter denotes the remaining value. There may be more than one limit applicable to you.

<figure><img src="https://3826932121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FBQ7Zf9paoN3FTeGcyfY1%2Fuploads%2Fgit-blob-9fc85af829ebac87fc60106dd2621362bf4c120c%2Fimage%20(26).png?alt=media" alt=""><figcaption></figcaption></figure>

## Limiting domain access due to a low success rate

Web Scraper API continuously monitors your success rate on every domain you scrape. If your success rate on any domain goes below 40% (measured over the last 5-minute window), your request rate to that particular domain will be limited to 1 req/s until the success rate recovers.

You may experience a low success rate due to two reasons:

* Web Scraper API's inability to handle the website's bot traffic control systems;
* Your own cookies, headers, or other variables interfering with Web Scraper API's web access logic.

When your requests to a domain are limited due to a low success rate, you will get an API response with the `429` status code and the following message:

{% code overflow="wrap" %}

```json
{
    "message": "Access to {domain} has been limited to 1 req/s due to a low success rate. If you are using custom headers or cookies, ensure they are correct, then try again. The normal request limit will be restored automatically when the success rate improves."
}
```

{% endcode %}

Upon getting this response, please ensure that your request parameters are not the cause for this issue.


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/rate-limits.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
