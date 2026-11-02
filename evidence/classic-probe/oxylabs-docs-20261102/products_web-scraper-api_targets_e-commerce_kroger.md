> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api/targets/e-commerce/kroger.md).

# Kroger

Learn how to start scraping Kroger.

With Web Scraper API, you can scrape various types of **Kroger** pages; below is an overview of all supported scrapers and their respective `source` values. The response returns the page HTML in `content`, in the standard response structure described in [Realtime](/products/web-scraper-api/integration-methods/realtime.md) and [Push-Pull](/products/web-scraper-api/integration-methods/push-pull.md).

{% hint style="warning" %}
For some targets our system **forces JavaScript rendering** even if you do not set `render`; those requests count as rendered traffic. The list of force-rendered targets and how to switch rendering off are in [Forcing rendering on specific pages](/products/web-scraper-api/features/js-rendering-and-browser-control.md#forcing-rendering-on-specific-pages).
{% endhint %}

<table><thead><tr><th width="250">Source</th><th>Description</th></tr></thead><tbody><tr><td><code>kroger_search</code></td><td><a href="#search"><strong>Search page</strong></a> for a search term of your choice.</td></tr><tr><td><code>kroger_product</code></td><td><a href="#product"><strong>Product page</strong></a> of a product ID of your choice.</td></tr></tbody></table>

Any other Kroger page can be scraped by passing its `url` alone, no `source` needed.

{% hint style="info" %}
Besides the parameters listed below, you can include additional parameters such as `user_agent_type`, `geo_location`, `render`, and more to customize your scraping request. Read more [here](/products/web-scraper-api/features.md).
{% endhint %}

## Search

### Request samples

{% tabs %}
{% tab title="cURL" %}

```shell
curl 'https://realtime.oxylabs.io/v1/queries' \
--user 'USERNAME:PASSWORD' \
-H 'Content-Type: application/json' \
-d '{
        "source": "kroger_search",
        "query": "adidas"
    }'
```

{% endtab %}

{% tab title="Python" %}

```python
import requests
from pprint import pprint

# Structure payload.
payload = {
    'source': 'kroger_search',
    'query': 'adidas'
}

# Get response.
response = requests.request(
    'POST',
    'https://realtime.oxylabs.io/v1/queries',
    auth=('USERNAME', 'PASSWORD'),
    json=payload
)

# Instead of response with job status and results url, this will return the
# JSON response with the result.
pprint(response.json())
```

{% endtab %}

{% tab title="Node.js" %}

```javascript
const https = require("https");

const username = "USERNAME";
const password = "PASSWORD";
const body = {
    source: "kroger_search",
    query: "adidas"
};

const options = {
    hostname: "realtime.oxylabs.io",
    path: "/v1/queries",
    method: "POST",
    headers: {
        "Content-Type": "application/json",
        Authorization:
            "Basic " + Buffer.from(`${username}:${password}`).toString("base64"),
    },
};

const request = https.request(options, (response) => {
    let data = "";

    response.on("data", (chunk) => {
        data += chunk;
    });

    response.on("end", () => {
        const responseData = JSON.parse(data);
        console.log(JSON.stringify(responseData, null, 2));
    });
});

request.on("error", (error) => {
    console.error("Error:", error);
});

request.write(JSON.stringify(body));
request.end();
```

{% endtab %}

{% tab title="HTTP" %}

```http
# The whole string you submit has to be URL-encoded.

https://realtime.oxylabs.io/v1/queries?source=kroger_search&query=adidas&access_token=12345abcde
```

{% endtab %}

{% tab title="PHP" %}

```php
<?php

$params = array(
    'source' => 'kroger_search',
    'query' => 'adidas'
);

$ch = curl_init();

curl_setopt($ch, CURLOPT_URL, "https://realtime.oxylabs.io/v1/queries");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($params));
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_USERPWD, "USERNAME" . ":" . "PASSWORD");

$headers = array();
$headers[] = "Content-Type: application/json";
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

$result = curl_exec($ch);
echo $result;

if (curl_errno($ch)) {
    echo 'Error:' . curl_error($ch);
}
curl_close($ch);
```

{% endtab %}

{% tab title="Golang" %}

```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "io/ioutil"
    "net/http"
)

func main() {
    const Username = "USERNAME"
    const Password = "PASSWORD"

    payload := map[string]interface{}{
        "source": "kroger_search",
        "query": "adidas",
    }

    jsonValue, _ := json.Marshal(payload)

    client := &http.Client{}
    request, _ := http.NewRequest("POST",
        "https://realtime.oxylabs.io/v1/queries",
        bytes.NewBuffer(jsonValue),
    )

    request.SetBasicAuth(Username, Password)
    response, _ := client.Do(request)

    responseText, _ := ioutil.ReadAll(response.Body)
    fmt.Println(string(responseText))
}
```

{% endtab %}

{% tab title="C#" %}

```csharp
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;

namespace OxyApi
{
    class Program
    {
        static async Task Main()
        {
            const string Username = "USERNAME";
            const string Password = "PASSWORD";

            var parameters = new {
                source = "kroger_search",
                query = "adidas"
            };

            var client = new HttpClient();

            Uri baseUri = new Uri("https://realtime.oxylabs.io");
            client.BaseAddress = baseUri;

            var requestMessage = new HttpRequestMessage(HttpMethod.Post, "/v1/queries");
            requestMessage.Content = JsonContent.Create(parameters);

            var authenticationString = $"{Username}:{Password}";
            var base64EncodedAuthenticationString = Convert.ToBase64String(System.Text.ASCIIEncoding.UTF8.GetBytes(authenticationString));
            requestMessage.Headers.Add("Authorization", "Basic " + base64EncodedAuthenticationString);

            var response = await client.SendAsync(requestMessage);
            var contents = await response.Content.ReadAsStringAsync();

            Console.WriteLine(contents);
        }
    }
}
```

{% endtab %}

{% tab title="Java" %}

```java
package org.example;

import okhttp3.*;
import org.json.JSONObject;
import java.util.concurrent.TimeUnit;

public class Main implements Runnable {
    private static final String AUTHORIZATION_HEADER = "Authorization";
    public static final String USERNAME = "USERNAME";
    public static final String PASSWORD = "PASSWORD";

    public void run() {
        JSONObject jsonObject = new JSONObject();
        jsonObject.put("source", "kroger_search");
        jsonObject.put("query", "adidas");

        Authenticator authenticator = (route, response) -> {
            String credential = Credentials.basic(USERNAME, PASSWORD);
            return response
                    .request()
                    .newBuilder()
                    .header(AUTHORIZATION_HEADER, credential)
                    .build();
        };

        var client = new OkHttpClient.Builder()
                .authenticator(authenticator)
                .readTimeout(180, TimeUnit.SECONDS)
                .build();

        var mediaType = MediaType.parse("application/json; charset=utf-8");
        var body = RequestBody.create(jsonObject.toString(), mediaType);
        var request = new Request.Builder()
                .url("https://realtime.oxylabs.io/v1/queries")
                .post(body)
                .build();

        try (var response = client.newCall(request).execute()) {
            if (response.body() != null) {
                try (var responseBody = response.body()) {
                    System.out.println(responseBody.string());
                }
            }
        } catch (Exception exception) {
            System.out.println("Error: " + exception.getMessage());
        }

        System.exit(0);
    }

    public static void main(String[] args) {
        new Thread(new Main()).start();
    }
}
```

{% endtab %}

{% tab title="JSON" %}

```json
{
    "source": "kroger_search",
    "query": "adidas"
}
```

{% endtab %}
{% endtabs %}

### Request parameter values <a href="#request-parameter-values" id="request-parameter-values"></a>

<table><thead><tr><th width="180">Parameter</th><th>Description</th><th width="160">Default Value</th></tr></thead><tbody><tr><td><mark style="background-color:green;"><strong><code>source</code></strong></mark></td><td>Sets the scraper.</td><td><code>kroger_search</code></td></tr><tr><td><mark style="background-color:green;"><strong><code>query</code></strong></mark></td><td>The keyword or phrase to search for products.</td><td>-</td></tr><tr><td><code>store_id</code>, <code>delivery_zip</code>, <code>fulfillment_type</code>, <code>price_range</code>, <code>brand</code></td><td>Optional localization and filter parameters, see <a href="#localization-and-filtering">Localization and Filtering</a>.</td><td>-</td></tr></tbody></table>

&#x20;   \- mandatory parameter

## Product <a href="#product" id="product"></a>

### Request samples

{% tabs %}
{% tab title="cURL" %}

```shell
curl 'https://realtime.oxylabs.io/v1/queries' \
--user 'USERNAME:PASSWORD' \
-H 'Content-Type: application/json' \
-d '{
        "source": "kroger_product",
        "product_id": "0021006550000"
    }'
```

{% endtab %}

{% tab title="Python" %}

```python
import requests
from pprint import pprint

# Structure payload.
payload = {
    'source': 'kroger_product',
    'product_id': '0021006550000'
}

# Get response.
response = requests.request(
    'POST',
    'https://realtime.oxylabs.io/v1/queries',
    auth=('USERNAME', 'PASSWORD'),
    json=payload
)

# Instead of response with job status and results url, this will return the
# JSON response with the result.
pprint(response.json())
```

{% endtab %}

{% tab title="Node.js" %}

```javascript
const https = require("https");

const username = "USERNAME";
const password = "PASSWORD";
const body = {
    source: "kroger_product",
    product_id: "0021006550000"
};

const options = {
    hostname: "realtime.oxylabs.io",
    path: "/v1/queries",
    method: "POST",
    headers: {
        "Content-Type": "application/json",
        Authorization:
            "Basic " + Buffer.from(`${username}:${password}`).toString("base64"),
    },
};

const request = https.request(options, (response) => {
    let data = "";

    response.on("data", (chunk) => {
        data += chunk;
    });

    response.on("end", () => {
        const responseData = JSON.parse(data);
        console.log(JSON.stringify(responseData, null, 2));
    });
});

request.on("error", (error) => {
    console.error("Error:", error);
});

request.write(JSON.stringify(body));
request.end();
```

{% endtab %}

{% tab title="HTTP" %}

```http
# The whole string you submit has to be URL-encoded.

https://realtime.oxylabs.io/v1/queries?source=kroger_product&product_id=0021006550000&access_token=12345abcde
```

{% endtab %}

{% tab title="PHP" %}

```php
<?php

$params = array(
    'source' => 'kroger_product',
    'product_id' => '0021006550000'
);

$ch = curl_init();

curl_setopt($ch, CURLOPT_URL, "https://realtime.oxylabs.io/v1/queries");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($params));
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_USERPWD, "USERNAME" . ":" . "PASSWORD");

$headers = array();
$headers[] = "Content-Type: application/json";
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

$result = curl_exec($ch);
echo $result;

if (curl_errno($ch)) {
    echo 'Error:' . curl_error($ch);
}
curl_close($ch);
```

{% endtab %}

{% tab title="Golang" %}

```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "io/ioutil"
    "net/http"
)

func main() {
    const Username = "USERNAME"
    const Password = "PASSWORD"

    payload := map[string]interface{}{
        "source": "kroger_product",
        "product_id": "0021006550000",
    }

    jsonValue, _ := json.Marshal(payload)

    client := &http.Client{}
    request, _ := http.NewRequest("POST",
        "https://realtime.oxylabs.io/v1/queries",
        bytes.NewBuffer(jsonValue),
    )

    request.SetBasicAuth(Username, Password)
    response, _ := client.Do(request)

    responseText, _ := ioutil.ReadAll(response.Body)
    fmt.Println(string(responseText))
}
```

{% endtab %}

{% tab title="C#" %}

```csharp
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;

namespace OxyApi
{
    class Program
    {
        static async Task Main()
        {
            const string Username = "USERNAME";
            const string Password = "PASSWORD";

            var parameters = new {
                source = "kroger_product",
                product_id = "0021006550000"
            };

            var client = new HttpClient();

            Uri baseUri = new Uri("https://realtime.oxylabs.io");
            client.BaseAddress = baseUri;

            var requestMessage = new HttpRequestMessage(HttpMethod.Post, "/v1/queries");
            requestMessage.Content = JsonContent.Create(parameters);

            var authenticationString = $"{Username}:{Password}";
            var base64EncodedAuthenticationString = Convert.ToBase64String(System.Text.ASCIIEncoding.UTF8.GetBytes(authenticationString));
            requestMessage.Headers.Add("Authorization", "Basic " + base64EncodedAuthenticationString);

            var response = await client.SendAsync(requestMessage);
            var contents = await response.Content.ReadAsStringAsync();

            Console.WriteLine(contents);
        }
    }
}
```

{% endtab %}

{% tab title="Java" %}

```java
package org.example;

import okhttp3.*;
import org.json.JSONObject;
import java.util.concurrent.TimeUnit;

public class Main implements Runnable {
    private static final String AUTHORIZATION_HEADER = "Authorization";
    public static final String USERNAME = "USERNAME";
    public static final String PASSWORD = "PASSWORD";

    public void run() {
        JSONObject jsonObject = new JSONObject();
        jsonObject.put("source", "kroger_product");
        jsonObject.put("product_id", "0021006550000");

        Authenticator authenticator = (route, response) -> {
            String credential = Credentials.basic(USERNAME, PASSWORD);
            return response
                    .request()
                    .newBuilder()
                    .header(AUTHORIZATION_HEADER, credential)
                    .build();
        };

        var client = new OkHttpClient.Builder()
                .authenticator(authenticator)
                .readTimeout(180, TimeUnit.SECONDS)
                .build();

        var mediaType = MediaType.parse("application/json; charset=utf-8");
        var body = RequestBody.create(jsonObject.toString(), mediaType);
        var request = new Request.Builder()
                .url("https://realtime.oxylabs.io/v1/queries")
                .post(body)
                .build();

        try (var response = client.newCall(request).execute()) {
            if (response.body() != null) {
                try (var responseBody = response.body()) {
                    System.out.println(responseBody.string());
                }
            }
        } catch (Exception exception) {
            System.out.println("Error: " + exception.getMessage());
        }

        System.exit(0);
    }

    public static void main(String[] args) {
        new Thread(new Main()).start();
    }
}
```

{% endtab %}

{% tab title="JSON" %}

```json
{
    "source": "kroger_product",
    "product_id": "0021006550000"
}
```

{% endtab %}
{% endtabs %}

### Request parameter values <a href="#request-parameter-values" id="request-parameter-values"></a>

<table><thead><tr><th width="180">Parameter</th><th>Description</th><th width="160">Default Value</th></tr></thead><tbody><tr><td><mark style="background-color:green;"><strong><code>source</code></strong></mark></td><td>Sets the scraper.</td><td><code>kroger_product</code></td></tr><tr><td><mark style="background-color:green;"><strong><code>product_id</code></strong></mark></td><td>The 13-digit product ID, found at the end of the product page URL, e.g. <code>kroger.com/p/kroger-tender-and-juicy-whole-frozen-turkey-14-16-lb/</code><strong><code>0021006550000</code></strong>.</td><td>-</td></tr><tr><td><code>store_id</code>, <code>delivery_zip</code>, <code>fulfillment_type</code></td><td>Optional localization parameters, see <a href="#localization-and-filtering">Localization and Filtering</a>.</td><td>-</td></tr></tbody></table>

&#x20;   \- mandatory parameter

## Localization and Filtering <a href="#localization-and-filtering" id="localization-and-filtering"></a>

Kroger shows search results and product availability for a selected store or delivery area. If none of the parameters below is set, the site falls back to a store of its own choice.

<table><thead><tr><th width="130.26171875">Parameter</th><th width="93.89453125">Applies to</th><th width="265.265625">Description</th><th width="270.79296875">Default</th></tr></thead><tbody><tr><td><code>store_id</code></td><td><code>kroger_search</code>, <code>kroger_product</code></td><td>Selects the store. The ID is the division number and the store number from the store's page URL on kroger.com, joined together: <code>…/stores/grocery/sc/irmo/irmo-station-st-andrews-rd/011/00002</code> → <code>01100002</code>. The full list of stores is available <a href="https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FzrXw45naRpCZ0Ku9AjY1%2Fuploads%2FAsihGe7hi5yfauUl2JIQ%2Fkroger_stores.csv?alt=media&#x26;token=40fcd869-1845-47c5-bf76-96e74cabf685"><strong>here</strong></a>. Required when <code>fulfillment_type</code> is <code>pickup</code> or <code>in_store</code>.</td><td>-</td></tr><tr><td><code>delivery_zip</code></td><td><code>kroger_search</code>, <code>kroger_product</code></td><td>ZIP code of the delivery area, e.g. <code>45202</code>. Required when <code>fulfillment_type</code> is <code>delivery</code>.</td><td>-</td></tr><tr><td><code>fulfillment_type</code></td><td><code>kroger_search</code>, <code>kroger_product</code></td><td>Fulfillment method. Available values: <code>pickup</code>, <code>delivery</code>, <code>in_store</code>. <code>pickup</code> and <code>in_store</code> need <code>store_id</code>; <code>delivery</code> needs <code>delivery_zip</code>.</td><td><code>in_store</code> with <code>store_id</code> alone, <code>delivery</code> with <code>delivery_zip</code> alone</td></tr><tr><td><code>price_range</code></td><td><code>kroger_search</code></td><td>Price filter, formatted as <code>min_price-max_price</code> with two decimal places, e.g. <code>2.00-5.00</code>.</td><td>-</td></tr><tr><td><code>brand</code></td><td><code>kroger_search</code></td><td>Filters the results to one brand, e.g. <code>Fairlife</code>.</td><td>-</td></tr></tbody></table>

If `fulfillment_type` is set without the parameter it needs, the result comes back with `status_code` 400. A `store_id` that is not a Kroger store, or one without its leading zero, returns `status_code` 400. A `delivery_zip` outside the delivery area returns `status_code` 613.

```json
{
    "source": "kroger_search",
    "query": "milk",
    "store_id": "01100002",
    "fulfillment_type": "pickup",
    "brand": "Fairlife"
}
```


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api/targets/e-commerce/kroger.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
