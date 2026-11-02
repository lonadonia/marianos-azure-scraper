> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api/integration-methods.md).

# Integration Methods

Explore the three integration methods for the Oxylabs Web Scraper API (Realtime, Push-Pull, Proxy Endpoint) and learn how they differ in job submission, format and workflow.

Web Scraper API supports **three integration methods,** each one with its unique benefits:

* [**Push-Pull**](/products/web-scraper-api/integration-methods/push-pull.md) **(supports batch queries)**. This integration method is **asynchronous**. This means that upon submitting your job, we will quickly return you a JSON with your job info, including the URLs for downloading the result/checking the job status. Once we are done processing your job, we will `POST` a notification about job completion to your server, at which point you can go ahead and download the results. This integration method also enables uploading results straight to your AWS S3, Google Cloud, or any S3-compatible storage.

{% hint style="success" %}
Push-Pull is our recommended integration method for reliably handling large amounts of data.
{% endhint %}

* [**Realtime**](/products/web-scraper-api/integration-methods/realtime.md). This method is synchronous. This means that upon sending your job submission request, **you will have to keep the connection open** until we successfully finish your job or return an error. This integration method is best for real-time data extraction when you need an immediate response. You can send JSON payloads with scraping and parsing parameters, while the API handles proxy management, retries, and bot traffic management automatically.
* [**Proxy Endpoint**](/products/web-scraper-api/integration-methods/proxy-endpoint.md). This method is also synchronous (like Realtime), but instead of using our service via a RESTful interface, you **can use our endpoint like a proxy**. Use Proxy Endpoint if you've used proxies before and would just like to get the available web content from us.

{% hint style="info" %}
The Time-To-Live (**TTL**) for all API connections is set to **150 seconds**. It's important to note that in rare cases, connections may timeout before receiving a response. Factors such as system load or extremely complex job submissions can contribute to timeouts.
{% endhint %}


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api/integration-methods.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
