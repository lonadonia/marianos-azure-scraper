> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api.md).

# Web Scraper API (Classic)

Learn to use Web Scraper API and scrape any public website you need. Find code examples, parameter usage, localization, targets, and much more.

[**Web Scraper API**](https://oxylabs.io/products/scraper-api/web) is an **all-in-one web data collection solution** designed for extracting real-time data at scale from any public website. It covers every stage of web scraping, from crawling URLs and improving access success rates to data parsing and delivery to your preferred storage, so you don’t have to manage proxies, request management, or infrastructure.

The tool is built to meet enterprise security standards, including SOC 2 Type II compliance, and offers fast-adapting infrastructure that dynamically adjusts to target websites to ensure high success rates and reliable data extraction across search engines, e-commerce sites, travel platforms, and more.

## Getting started

**Create your API user credentials**: Reach out to [our team](mailto:hello@oxylabs.io) to gain request your API user credentials (`USERNAME` and `PASSWORD`).

### Request samples

The API manages proxy rotation, request retries, and handles bot monitoring systems automatically as part of its integrated infrastructure, so a single request is enough to retrieve all structured data.

Below, you'll find sample cURL requests. For examples in other programming languages, please refer to the relevant sections: [**Amazon**](https://developers.oxylabs.io/api-targets/e-commerce/amazon), [**Google**](https://developers.oxylabs.io/api-targets/search-engines/google), [**Other Websites**](https://developers.oxylabs.io/api-targets/).

{% tabs %}
{% tab title="Amazon" %}

```bash
curl 'https://realtime.oxylabs.io/v1/queries' \
--user "USERNAME:PASSWORD" \
-H "Content-Type: application/json" \
-d '{
        "source": "amazon_product",
        "query": "B07FZ8S74R",
        "geo_location": "90210",
        "parse": true
    }'
```

{% endtab %}

{% tab title="Google" %}

```bash
curl 'https://realtime.oxylabs.io/v1/queries' \
--user 'USERNAME:PASSWORD' \
-H 'Content-Type: application/json' \
-d '{
        "source": "google_search",
        "query": "adidas",
        "geo_location": "California,United States",
        "parse": true
    }'
```

{% endtab %}

{% tab title="Other" %}

```bash
curl 'https://realtime.oxylabs.io/v1/queries' \
--user 'USERNAME:PASSWORD' \
-H 'Content-Type: application/json' \
-d '{
        "source": "universal",
        "url": "https://sandbox.oxylabs.io/"
    }'
```

{% endtab %}
{% endtabs %}

We use synchronous [**Realtime**](/products/web-scraper-api/integration-methods/realtime.md) integration method in our examples. If you would like to use [**Proxy Endpoint**](/products/web-scraper-api/integration-methods/proxy-endpoint.md) or asynchronous [**Push-Pull**](/products/web-scraper-api/integration-methods/push-pull.md) integration, refer to the [**integration methods**](/products/web-scraper-api/integration-methods.md) section.

{% file src="/files/q6L6LYAaqoK4WmPt29Ty" %}

{% file src="/files/YikpYmKx2dVWhzeNXOTN" %}

### Request parameter values

1. <mark style="background-color:green;">**`source`**</mark> - This parameter sets the scraper that will be used to process your request.
2. <mark style="background-color:green;">**`URL`**</mark> or <mark style="background-color:green;">**`query`**</mark> - Provide the `URL` or `query` for the type of page you want to scrape. Refer to the table below and the corresponding target sub-pages for detailed guidance on when to use each parameter.
3. Optionally, you can include additional parameters such as `geo_location`, `user_agent_type`, `parse` (find the list of our parsers [**here**](/products/web-scraper-api/features/result-processing-and-storage/dedicated-parsers.md)), `render` and more to customize your scraping request. Read more: [**Features**](/products/web-scraper-api/features.md).

\- mandatory parameter

### Scraping with URLs or parametrized inputs

Oxylabs support two general groups of inputs - URLs and parametrized inputs like queries, product or video IDs. [Generic targets](https://developers.oxylabs.io/api-targets/) which do not have a dedicated source can be scraped with `universal` source.

All available targets with dedicated sources can be found [**here**](/products/web-scraper-api/targets.md).

{% hint style="info" %}
If you need help making your first request or optimizing your setup, our 24/7 expert support team is available via live chat.
{% endhint %}

## Testing via Scraper APIs Playground

Try [**Web Scraper API**](https://oxylabs.io/products/scraper-api/web) and [**OxyCopilot**](https://oxylabs.io/products/scraper-api/ai-web-scraper-copilot) in the [**Scraper APIs Playground**](https://dashboard.oxylabs.io/?route=/api-playground).

{% embed url="<https://www.youtube.com/watch?v=kDhknxrod6U>" %}

{% embed url="<https://youtu.be/9JoF8_5r5HY?si=61c3Zkx6FrH06PVa>" %}

## Testing via Postman

Get started with our API using Postman, a handy tool for making HTTP requests. Download our [**Web Scraper API Postman collection**](https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FzrXw45naRpCZ0Ku9AjY1%2Fuploads%2FMeGA0TZQMcAFHoVhRSQi%2FWeb%20Scraper%20API.new_postman_collection.json?alt=media\&token=9f51d41b-6604-4eef-b6c1-5024cf52c5bf) and import it. This collection includes examples that demonstrate the functionality of the scraper. Customize the examples to your needs or start scraping right away.

For step-by-step instructions, watch our video tutorial below. If you're new to Postman, check out this short [**guide**](/integrations/web-scraper-api-integrations/postman.md).

{% embed url="<https://www.youtube.com/watch?v=WOD0mZnu-j0>" %}

{% hint style="info" %}
*All information herein is provided on an "as is" basis and for informational purposes only. We make no representation and disclaim all liability with respect to your use of any information contained on this page. Before engaging in scraping activities of any kind you should consult your legal advisors and carefully read the particular website's terms of service or receive a scraping license.*
{% endhint %}


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
