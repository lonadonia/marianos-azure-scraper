> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api/integration-methods/realtime.md).

# Realtime

Realtime integration for the Web Scraper API by Oxylabs. Keep the HTTPS connection open from job submission until results or an error are returned, using JSON-formatted payloads.

Realtime is a synchronous integration method. It **requires keeping the connection open** until the job is finished successfully or returns an error. It's the quickest method to implement; for large amounts of data, use [**Push-Pull**](/products/web-scraper-api/integration-methods/push-pull.md) instead.

## Job Submission

### Endpoint

The Realtime API endpoint for job submission is:

```
POST https://realtime.oxylabs.io/v1/queries
```

### Input

Provide the job parameters in a JSON payload as shown in the examples below. Python and PHP examples include comments for clarity.

{% tabs %}
{% tab title="cURL" %}

```shell
curl --user "USERNAME:PASSWORD" \
'https://realtime.oxylabs.io/v1/queries' \
-H "Content-Type: application/json" \
-d '{"source": "universal", "url": "https://example.com", "geo_location": "United States"}'
```

{% endtab %}

{% tab title="Python" %}

```python
import requests
from pprint import pprint


# Structure payload.
payload = {
    "source": "universal", # Source you choose e.g. "universal"
    "url": "https://example.com", # Check the docs of the specific source you're using to see if you should use "url" or "query"
    "geo_location": "United States", # Some sources accept post codes and/or coordinates
    #"render" : "html", # Uncomment if you want to render JavaScript on the page
    #"render" : "png", # Uncomment if you want to take a screenshot of a scraped web page
    #"parse" : True, # Check what sources support parsed data
}

# Get response.
response = requests.request(
    'POST',
    'https://realtime.oxylabs.io/v1/queries',
    auth=('YOUR_USERNAME', 'YOUR_PASSWORD'), #Your credentials go here
    json=payload,
)

# Instead of response with job status and results url, this will return the
# JSON response with results.
pprint(response.json())
```

{% endtab %}

{% tab title="PHP" %}

```php
<?php

$params = array(
    'source' => 'universal', //Source you choose e.g. "universal"
    'url' => 'https://example.com', // Check the docs of the specific source you're using to see if you should use "url" or "query"
    'geo_location' => 'United States', //Some sources accept zip-code or coordinates
    //'render' => 'html', // Uncomment if you want to render JavaScript within the page
    //'render' => 'png', // Uncomment if you want to take a screenshot of a scraped web page
    //'parse' => TRUE, // Check what sources support parsed data
);

$ch = curl_init();

curl_setopt($ch, CURLOPT_URL, "https://realtime.oxylabs.io/v1/queries");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($params));
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_USERPWD, "YOUR_USERNAME" . ":" . "YOUR_PASSWORD"); //Your credentials go here

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
            const string Username = "YOUR_USERNAME";
            const string Password = "YOUR_PASSWORD";

            var parameters = new Dictionary<string, string>()
            {
                { "source", "universal" },
                { "url", "https://example.com" },
                { "geo_location", "United States" },
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
	const Username = "YOUR_USERNAME"
	const Password = "YOUR_PASSWORD"

	payload := map[string]string{
		"source": "universal",
		"url": "https://example.com",
		"geo_location": "United States",
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

{% tab title="Java" %}

```java
package org.example;

import okhttp3.*;
import org.json.JSONObject;

public class Main implements Runnable {
    private static final String AUTHORIZATION_HEADER = "Authorization";
    public static final String USERNAME = "YOUR_USERNAME";
    public static final String PASSWORD = "YOUR_PASSWORD";

    public void run() {
        JSONObject jsonObject = new JSONObject();
        jsonObject.put("source", "universal");
        jsonObject.put("url", "https://example.com");
        jsonObject.put("geo_location", "United States");

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
                .build();

        var mediaType = MediaType.parse("application/json; charset=utf-8");
        var body = RequestBody.create(jsonObject.toString(), mediaType);
        var request = new Request.Builder()
                .url("https://realtime.oxylabs.io/v1/queries")
                .post(body)
                .build();

        try (var response = client.newCall(request).execute()) {
            assert response.body() != null;
            System.out.println(response.body().string());
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

{% tab title="Node.js" %}

```javascript
import fetch from 'node-fetch';

const username = 'YOUR_USERNAME';
const password = 'YOUR_PASSWORD';
const body = {
  source: 'universal',
  url: 'https://example.com',
  geo_location: 'United States'
};
const response = await fetch('https://realtime.oxylabs.io/v1/queries', {
  method: 'post',
  body: JSON.stringify(body),
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Basic ' + Buffer.from(`${username}:${password}`).toString('base64'),
  }
});

console.log(await response.json());
```

{% endtab %}
{% endtabs %}

### Output

Realtime API supports these result types in the output:

* **HTML**: The raw HTML content scraped from the target webpage;
* **JSON**: Structured data parsed from the HTML content, formatted in JSON format;
* **PNG**: Base64-encoded screenshot of the rendered page in PNG format.
* **XHR:** [XHR requests](/products/web-scraper-api/features/result-processing-and-storage/output-types/capturing-network-requests-fetch-xhr.md) made while loading the page.
* **Markdown:** [Markdown](/products/web-scraper-api/features/result-processing-and-storage/output-types/markdown-output.md) of a web page.

This table explains the default result types based on the parameters included in the payload of the API request:

| Render parameter | Parse parameter | Default output |
| ---------------- | --------------- | -------------- |
| -                | -               | html           |
| `html`           | -               | html           |
| `png`            | -               | png            |
| -                | `true`          | json           |
| `html`           | `true`          | json           |
| `png`            | `true`          | png            |

By default, Realtime returns only the **default output** for your payload. To receive one or more of the available outputs instead, add the `type` query parameter to the endpoint, as shown below. Each requested type is returned as a separate entry in the `results` array. This is the [**multiple result types**](/products/web-scraper-api/features/result-processing-and-storage/output-types/multi-format-output.md) feature, and it works the same way in Realtime and [**Push-Pull**](/products/web-scraper-api/integration-methods/push-pull.md).

```
POST https://realtime.oxylabs.io/v1/queries?type=raw,parsed,png
```

{% hint style="info" %}
Some sources have a [dedicated parser](/products/web-scraper-api/features/result-processing-and-storage/dedicated-parsers.md); use `parse: true` with those. For any other target, use [Custom Parser.](/products/web-scraper-api/features/custom-parser.md) Every parsed result carries a `parse_status_code`; see [response codes](/products/web-scraper-api/response-codes.md#parsers) for what each value means.
{% endhint %}

#### Output example:

```json
{
  "results": [
    {
      "content": "<!doctype html><html lang=\"en\"><head><title>Example Domain</title></head><body>CONTENT</body></html>",
      "created_at": "2026-08-21 13:00:20",
      "updated_at": "2026-08-21 13:00:21",
      "page": 1,
      "url": "https://example.com",
      "job_id": "7496551765458818050",
      "is_render_forced": false,
      "type": "raw",
      "status_code": 200
    }
  ]
}
```

{% hint style="info" %}
The response also includes `_request`, `_response`, and `session_info` objects, omitted here for brevity. When `parse` is used, `parser_type` and `parser_preset` are returned as well.
{% endhint %}


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api/integration-methods/realtime.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
