> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information.md).

# Traffic and Billing

Learn about Web Scraper API's traffic and billing, how traffic usage is calculated, and find out which results are billable.

### Traffic usage

Web Scraper API count the number of **results**. **Results** refer to distinct entities of content (e.g., web page HTML) that were successfully retrieved from the web.

* **Successful results** (billed): All results from the target site with `2xx` or `4xx` status codes are counted as successful and are billable.
* **Unsuccessful results** (not billed): Other results are counted as unsuccessful and are not billed.

{% hint style="info" %}
Status code `429` (Too many requests) is not billed. This occurs when you exceed the rate limit. If you encounter this frequently, contact your account manager to increase your limits.
{% endhint %}

For more information about response codes, please refer to [**the Response Codes table**](/products/web-scraper-api/response-codes.md).

{% hint style="warning" %}
If the response contains `2xx` or `4xx` status codes, and the result doesn’t contain expected information, we still count it as a successful result.
{% endhint %}

### Billing

You will be billed for the number of results with successfully extracted data.

Failed attempts to scrape due to our system errors (`5xx` and `6xx` status codes) won’t be included, and you won’t be billed for them.

{% hint style="warning" %}
If a request results in a failed attempt due to a fault or error on your side, you will still be billed.
{% endhint %}

Please find a few billing case examples below:

#### Case example #1 - Successful scraping attempt

You create a scraping job, and it takes three attempts for Scraper API to fetch good content from the website successfully. You will be billed only for the result of the last attempt, which was successful.

<figure><img src="https://3826932121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FBQ7Zf9paoN3FTeGcyfY1%2Fuploads%2Fgit-blob-57b56d89cdd17ccc3b4137fb32115fb710b32390%2FScraper%20API%20%E2%80%93%201.png?alt=media" alt="Case 1"><figcaption></figcaption></figure>

#### Case example #2 - Scraping failed due to our error

You create a scraping job that has failed due to our error, e.g., we have reached our internal retry limit. In this case, you will not be billed for the received result.

<figure><img src="https://3826932121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FBQ7Zf9paoN3FTeGcyfY1%2Fuploads%2Fgit-blob-687cef62188ae2e20bb6e532f992bfe178b8a8b7%2FScraper%20API%20%E2%80%93%202.png?alt=media" alt="Case 2"><figcaption></figcaption></figure>

#### Case example #3 - Scraping failed due to the client's error

You create a scraping job that has failed due to an error on your side. You will be billed for this result.<br>

<figure><img src="https://3826932121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FBQ7Zf9paoN3FTeGcyfY1%2Fuploads%2Fgit-blob-ecc872da3499407ad558e8cb9345d6eda2a196e3%2FScraper%20API%20%E2%80%93%203.png?alt=media" alt="Case 3"><figcaption></figcaption></figure>


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
