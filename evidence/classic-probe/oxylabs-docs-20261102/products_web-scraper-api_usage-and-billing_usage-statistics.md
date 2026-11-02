> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/usage-statistics.md).

# Usage Statistics

Learn how to check usage statistic of Web Scraper API using simple requests.

You can check your usage statistics free of charge by submitting an API request.

The endpoint below is for usage statistics querries :

```
GET https://data.oxylabs.io/v2/stats
```

### Input

By default, the API will return unfiltered (all-time, all sources) usage statistics. If you like, you can get grouped and/or filtered stats.

You can combine two or more parameters in the same query, e.g., group stats by day and filter by source.

| Parameter                                                                                                        | Description                                                                                                                                         | Valid values                                                                                                        | URL example                                                 |
| ---------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `group_by`                                                                                                       | Enables showing daily, monthly or yearly usage stats (instead of showing total stats)                                                               | `day`, `month`, `year`                                                                                              | `https://data.oxylabs.io/v2/stats?group_by=day`             |
| `date_from`                                                                                                      | The lower date boundary. Best used together with `date_to`.                                                                                         | Any date in `Y-m-d` format.                                                                                         | `https://data.oxylabs.io/v2/stats?date_from=2022-01-17`     |
| `date_to`                                                                                                        | The upper date boundary. Best used together with `date_from`.                                                                                       | Any date in `Y-m-d` format.                                                                                         | `https://data.oxylabs.io/v2/stats?date_to=2022-06-17`       |
| `source`                                                                                                         | Lets you get usage statistics of a single `source` of your choice.                                                                                  | Any valid `source` value.                                                                                           | `https://data.oxylabs.io/v2/stats?source=universal`         |
| <p><code>product</code><br><br>This filter is for legacy users (accounts created before September 25, 2024).</p> | Lets you get usage statistics of a single product of your choice. Only applicable if you use the same username to access more than one Scraper API. | <p><code>serp\_scraper\_api</code>;</p><p><code>ecommerce\_scraper\_api</code> ; <code>web\_scraper\_api</code></p> | `https://data.oxylabs.io/v2/stats?product=serp_scraper_api` |

The below query returns monthly statistics.

{% tabs %}
{% tab title="cURL" %}

```shell
curl --user "user:pass1" 'https://data.oxylabs.io/v2/stats?group_by=month'
```

{% endtab %}

{% tab title="Python" %}

```python
import requests
from pprint import pprint

# Get response from stats endpoint.
response = requests.request(
    method='GET',
    url='https://data.oxylabs.io/v2/stats',
    auth=('user', 'pass1'),
)

# Print prettified JSON response to stdout.
pprint(response.json())
```

{% endtab %}

{% tab title="PHP" %}

```php
<?php

$ch = curl_init();

curl_setopt($ch, CURLOPT_URL, "https://data.oxylabs.io/v2/stats");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "GET");
curl_setopt($ch, CURLOPT_USERPWD, "user" . ":" . "pass1");

$result = curl_exec($ch);
echo $result;

if (curl_errno($ch)) {
    echo 'Error:' . curl_error($ch);
}
curl_close ($ch);
?>
```

{% endtab %}
{% endtabs %}

### Output

The `v2/stats` output contains usage stats, including product-level stats (E-Commerce Scraper API / SERP Scraper API / Web Scraper API). The product-level stats are broken down into source-level stats, which are further broken down into separate statistics for HTML and parsed results. See the [**data dictionary**](#data-dictionary) section to find out the meaning of each output key.

#### Sample output

```json
{
    "meta": {
        "group_by": null,
        "date_from": null,
        "date_to": null,
        "source": null,
        "product": null
    },
    "data": {
        "products": [
            {
                "all_count": 5837,
                "mode_callback_count": 5514,
                "mode_realtime_count": 315,
                "mode_superapi_count": 8,
                "contenttype_parsed_count": 56,
                "contenttype_html_count": 5781,
                "render_count": 3,
                "geo_location_count": 2330,
                "average_response_time": 88.54,
                "request_traffic": 4685091,
                "response_traffic": 602064208,
                "title": "serp_scraper_api",
                "sources": [
                    {
                        "all_count": 5616,
                        "mode_callback_count": 5414,
                        "mode_realtime_count": 194,
                        "mode_superapi_count": 8,
                        "render_count": 0,
                        "geo_location_count": 2190,
                        "average_response_time": 91.59,
                        "request_traffic": 4550507,
                        "response_traffic": 585423946,
                        "title": "serp_source1",
                        "parsed": false
                    },
                    {
                        "all_count": 1,
                        "mode_callback_count": 0,
                        "mode_realtime_count": 1,
                        "mode_superapi_count": 0,
                        "render_count": 0,
                        "geo_location_count": 1,
                        "average_response_time": 11,
                        "request_traffic": 0,
                        "response_traffic": 0,
                        "title": "serp_source2",
                        "parsed": false
                    }
                ]
            }
        ]
    }
}
```

### Data dictionary

| Key                        | Description                                                                                   | Type        |
| -------------------------- | --------------------------------------------------------------------------------------------- | ----------- |
| `meta`                     | The container of all submitted stats [**query parameters**](#input).                          | -           |
| `data`                     | The container of all statistics data.                                                         | JSON object |
| `products`                 | The list of product-level statistics objects.                                                 | JSON array  |
| `all_count`                | The total amount of results.                                                                  | Integer     |
| `mode_callback_count`      | The amount of results, fulfilled via Push-Pull integration method.                            | Integer     |
| `mode_realtime_count`      | The amount of results, fulfilled via Realtime integration method.                             | Integer     |
| `mode_superapi_count`      | The amount of results, fulfilled via Proxy Endpoint integration method.                       | Integer     |
| `contenttype_parsed_count` | The amount of parsed results.                                                                 | Integer     |
| `contenttype_html_count`   | The amount of HTML results.                                                                   | Integer     |
| `render_count`             | The amount of results, fulfilled with JavaScript execution.                                   | Integer     |
| `geo_location_count`       | The amount of results that were fulfilled with a user-defined `geo_location` parameter value. | Integer     |
| `average_response_time`    | The average response time (seconds).                                                          | Float       |
| `request_traffic`          | The total **request** traffic (bytes).                                                        | Integer     |
| `response_traffic`         | The total **response** traffic (bytes).                                                       | Integer     |
| `title`                    | Product or source name.                                                                       | String      |
| `sources`                  | The list of sources, belonging to a particular product.                                       | String      |
| `parsed`                   | The indication whether the data in the JSON object pertains to parsed results.                | Boolean     |


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/usage-statistics.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
