> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control.md).

# JS Rendering & Browser Control

Learn how to use a render parameter how to define browser instructions in Web Scraper API so you can scrape complex dynamic pages.

## JavaScript Rendering

If the page you want to scrape uses JavaScript to load its data into the DOM, add the `render` parameter to your request. The page is then fully rendered before we return the result, in one of two formats:

<table><thead><tr><th width="162.625">render value</th><th>You get</th></tr></thead><tbody><tr><td><code>html</code></td><td>The raw HTML of the fully rendered page</td></tr><tr><td><code>png</code></td><td>A Base64-encoded screenshot (PNG) of the rendered page</td></tr></tbody></table>

{% hint style="info" %}
If you want to scrape an image and download it, please refer to [**this section**](/products/web-scraper-api/features/result-processing-and-storage/output-types/download-images.md)**.**
{% endhint %}

### Request sample

{% tabs %}
{% tab title="cURL" %}

```shell
curl --user "USERNAME:PASSWORD" \
'https://realtime.oxylabs.io/v1/queries' \
-H "Content-Type: application/json" \
-d '{"source": "universal", "url": "https://www.example.com", "render": "html"}'
```

{% endtab %}

{% tab title="Python" %}

```python
import requests
from pprint import pprint

# Structure payload.
payload = {
    'source': 'universal',
    'url': 'https://www.example.com',
    'render': 'html',
}

# Get response.
response = requests.request(
    'POST',
    'https://realtime.oxylabs.io/v1/queries',
    auth=('USERNAME', 'PASSWORD'),
    json=payload,
)

# Instead of response with job status and results url, this will return the
# JSON response with the result.
pprint(response.json())
```

{% endtab %}

{% tab title="PHP" %}

```php
<?php

$params = [
    'source' => 'universal',
    'url' => 'https://www.example.com',
    'render' => 'html',
];

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
                { "url", "https://www.example.com" },
                { "render" : "html" },
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
		"url": "https://www.example.com",
        	"render": "html",
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
        jsonObject.put("url", "https://www.example.com");
        jsonObject.put("render", "html");

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
  'source': 'universal',
  'url': 'https://www.example.com',
  'render': 'html'
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

{% tab title="JSON" %}

```json
{
    "source": "universal", 
    "url": "https://www.example.com", 
    "render": "html"
}
```

{% endtab %}
{% endtabs %}

{% hint style="warning" %}
JavaScript rendering takes more time to scrape the page. Please set timeout on the client side to 180 seconds if using Realtime or Proxy Endpoint integration methods.
{% endhint %}

{% hint style="warning" %}
To ensure lowest traffic consumption, our system does not load unnecessary assets during page rendering.
{% endhint %}

## Forcing rendering on specific pages

For successful scraping, some page types of specific domains require rendering due to their dynamic content. For these, our system **automatically enforces rendering** even if you don't set the `render` parameter, so you always get accurate, reliable data from these otherwise difficult pages.

{% hint style="warning" %}
Please note that rendered jobs consume more traffic compared to non-rendered jobs.
{% endhint %}

If you wish to disable rendering, you can do so by adding the following parameter to your requests:

```
"render": ""
```

The full list of affected targets is maintained in the file below. We want our users to be fully aware of this when scraping the following pages:

<details>

<summary>Forced render domains</summary>

<table><thead><tr><th valign="top">Domain</th><th valign="top">Rendering category</th></tr></thead><tbody><tr><td valign="top"><code>acmemarkets</code></td><td valign="top"><code>product_pages</code></td></tr><tr><td valign="top"><code>adorebeauty</code></td><td valign="top"><code>product</code></td></tr><tr><td valign="top"><code>aeroin</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>agrizone</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>ajog</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>albertsons</code></td><td valign="top"><code>aisles</code>; <code>product_pages</code>; <code>search</code></td></tr><tr><td valign="top"><code>allegro</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>amazon</code></td><td valign="top"><code>amazon_bestsellers</code></td></tr><tr><td valign="top"><code>anbima</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>andronicos</code></td><td valign="top"><code>product_pages</code></td></tr><tr><td valign="top"><code>appliancesonline</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>aruodas</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>asda</code></td><td valign="top"><code>search</code></td></tr><tr><td valign="top"><code>auto5</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>avfoni</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>avito</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>b-parts</code></td><td valign="top"><code>product</code></td></tr><tr><td valign="top"><code>bakersplus</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>bedbathandbeyond</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>bergdorfgoodman</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>bestbuy</code></td><td valign="top"><code>site</code></td></tr><tr><td valign="top"><code>bevmo</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>bidfax</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>bilbasen</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>binglee</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>blibli</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>bloomingdales</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>book-secure</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>bookscouter</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>boulanger</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>canadagoose</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>canadiangamingbusiness</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>car</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>carfax</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>cargurus</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>carrefour</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>carrsqc</code></td><td valign="top"><code>product_pages</code></td></tr><tr><td valign="top"><code>carsales</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>carters</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>casasbahia</code></td><td valign="top"><code>search</code></td></tr><tr><td valign="top"><code>cec</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>ceneo</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>challenger</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>chewy</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>choicehotels</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>chrono24</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>citymarket</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>continentalwigs</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>costco</code></td><td valign="top"><code>products</code>; <code>categories (url)</code></td></tr><tr><td valign="top"><code>crunchbase</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>csod</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>cuinsight</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>darty</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>davidyurman</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>dillons</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>dergahtesbih</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>dextools</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>didi-food</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>didongviet</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>displays2go</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>ebay</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>ecsc-expat</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>edaboard</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>elcajonmitsubishi</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>elcapitalfinanciero</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>electroplanet</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>eraspace</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>etsy</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>exchange4media</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>expedia</code></td><td valign="top"><code>organic_requests</code></td></tr><tr><td valign="top"><code>extendedstayamerica</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>facebook</code></td><td valign="top"><code>marketplace</code></td></tr><tr><td valign="top"><code>fedex</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>flooranddecor</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>fmkorea</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>fotocasa</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>food4less</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>foodsco</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>fredmeyer</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>frysfood</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>g2</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>gerbes</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>glassdoor</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>gnc</code></td><td valign="top"><code>product</code></td></tr><tr><td valign="top"><code>goflink</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>google</code></td><td valign="top"><code>google_ai_mode</code>;<code>maps</code></td></tr><tr><td valign="top"><code>gopuff</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>grainger</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>greggyoungcdjratlantic</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>grofers</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>grok</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>haldex</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>harristeeter</code></td><td valign="top"><code>product</code>; <code>search</code>; <code>category</code>; <code>root</code></td></tr><tr><td valign="top"><code>harrods</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>harveynorman</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>hasznaltauto</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>headtopics</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>homecare</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>homedepot</code></td><td valign="top"><code>search</code></td></tr><tr><td valign="top"><code>homehardware</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>hyatt</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>hydradynellc</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>icrimewatch</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>ifood</code></td><td valign="top"><code>delivery</code></td></tr><tr><td valign="top"><code>immobilienscout24</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>indeed</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>instagram</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>interdiscount</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>intermarche</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>itsynergy</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>janesvillevw</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>jaycfoods</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>jbhifi</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>jewelosco</code></td><td valign="top"><code>product_pages</code></td></tr><tr><td valign="top"><code>kaina24</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>kayak</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>kingsoopers</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>kroger</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>laprensagrafica</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>latamairlines</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>lazada</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>leboncoin</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>leclercdrive</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>lexusofatlanticcity</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>lifestyleasia</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>loblaws</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>loccitane</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>lowes</code></td><td valign="top"><code>product</code></td></tr><tr><td valign="top"><code>loyalty360</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>luisaviaroma</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>macys</code></td><td valign="top"><code>brand</code>;<code>featured</code>;<code>product</code></td></tr><tr><td valign="top"><code>magazineluiza</code></td><td valign="top"><code>product</code></td></tr><tr><td valign="top"><code>marianos</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>master-outillage</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>mavs</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>mcmaster</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>medscape</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>menards</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>mercadolibre</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>metromarket</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>milatcikolata</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>mister-auto</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>neimanmarcus</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>norauto</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>nordstrom</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>oocl</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>ozon</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>pay-less</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>pedidosya</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>petco</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>picknsave</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>pointp</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>powerbuy</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>pricerunner</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>printus</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>publix</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>qfc</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>radwell</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>ralphs</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>raptorsupplies</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>realadvisor</code></td><td valign="top"><code>api</code></td></tr><tr><td valign="top"><code>realestate</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>redfin</code></td><td valign="top"><code>localization</code></td></tr><tr><td valign="top"><code>reporteindigo</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>researchgate</code></td><td valign="top"><code>pdf</code></td></tr><tr><td valign="top"><code>reuters</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>ripley</code></td><td valign="top"><code>product_pages</code></td></tr><tr><td valign="top"><code>runnersneed</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>rvtrader</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>safeway</code></td><td valign="top"><code>aisles</code>;<code>product_pages</code>;<code>search</code></td></tr><tr><td valign="top"><code>sahibinden</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>saksfifthavenue</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>sbermarket</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>secure-hotel-booking</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>senheng</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>sephora</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>shaws</code></td><td valign="top"><code>product_pages</code></td></tr><tr><td valign="top"><code>shein</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>shi</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>shoppersdrugmart</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>similarweb</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>smappliance</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>smithsfoodanddrug</code></td><td valign="top"><code>product</code>; <code>category</code></td></tr><tr><td valign="top"><code>smythstoys</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>sobeys</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>sociolla</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>speedo</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>starmarket</code></td><td valign="top"><code>product_pages</code></td></tr><tr><td valign="top"><code>stockx</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>stupiddope</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>svastara</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>takealot</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>target</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>theaustralian</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>theiet</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>thenonprofittimes</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>thespaces</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>tiki</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>tiktok</code></td><td valign="top"><code>all</code>;<code>search</code>;<code>user</code></td></tr><tr><td valign="top"><code>tmall</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>tomthumb</code></td><td valign="top"><code>product_pages</code></td></tr><tr><td valign="top"><code>tractorsupply</code></td><td valign="top"><code>search</code></td></tr><tr><td valign="top"><code>trendyol</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>truckpaper</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>truclothing</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top">truepeoplesearch</td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>upwork</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>vimeo</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>vivadodgeramfiat</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>vons</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>wabco-customercentre</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>walmart</code></td><td valign="top"><code>geo_location</code>; <code>search_with_video</code></td></tr><tr><td valign="top"><code>watchfinder</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>weismarkets</code></td><td valign="top"><code>organic</code></td></tr><tr><td valign="top"><code>wine</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>winoui</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>wipo</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>worten</code></td><td valign="top"><code>products</code></td></tr><tr><td valign="top"><code>wyndhamhotels</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>yelp</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>zalando</code></td><td valign="top"><code>all</code></td></tr><tr><td valign="top"><code>zoro</code></td><td valign="top"><code>all</code></td></tr></tbody></table>

</details>

## Browser instructions

When a page needs interaction, such as clicking a button, entering a search term, or scrolling to load more items, you can define your own `browser_instructions` that run while the page is rendered.

{% hint style="success" %}
The easiest way to build browser instructions is the AI-powered visual builder in the [Web Scraper API Playground](https://dashboard.oxylabs.io/?route=/api-playground). Read about it [here](/products/web-scraper-api/web-scraper-api-playground/oxycopilot.md#browser-instruction-builder).
{% endhint %}

### Quick start

First of all, browser instructions require the `render` parameter, either `html` or `png`, and are provided as a list in the `browser_instructions` field. Each item in the list is executed in order.

Say you want to search for `pizza boxes` on a website — type the term into the search field, click the search button, and wait 5 seconds for the results to load:

```json
{
    "source": "universal",
    "url": "https://www.etsy.com/",
    "render": "html",
    "browser_instructions": [
        {
            "type": "input",
            "value": "pizza boxes",
            "selector": {
                "type": "css",
                "value": "#global-enhancements-search-query"
            }
        },
        {
            "type": "click",
            "selector": {
                "type": "css",
                "value": "button[data-id='gnav-search-submit-button']"
            }
        },
        {
            "type": "wait",
            "wait_time_s": 5
        }
    ]
}
```

The result contains the HTML after the instructions have run:

```json
{
  "results": [
    {
      "content": "<!DOCTYPE html><html lang=\"en-US\">  Search results for \"pizza boxes\"  </html>",
      "created_at": "2026-08-19 12:23:06",
      "updated_at": "2026-08-19 12:23:24",
      "page": 1,
      "url": "https://www.etsy.com/search?q=pizza+boxes&ref=search_bar&instant_download=false",
      "job_id": "7495817623108602881",
      "is_render_forced": false,
      "type": "raw",
      "status_code": 200
    }
  ]
}
```

Scraped HTML should look like this:

<figure><img src="https://3826932121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FBQ7Zf9paoN3FTeGcyfY1%2Fuploads%2Fgit-blob-c2baf702d27346d7b1f44fb7493f478456ba8520%2Fimage.png?alt=media" alt=""><figcaption></figcaption></figure>

#### Fetching browser resources <a href="#fetching-browser-resources" id="fetching-browser-resources"></a>

We provide a standalone browser instruction for fetching browser resources.

The function is defined here:

Using `fetch_resource` will result in job returning the first occurrence of a Fetch/XHR resource that matches the format provided instead of the HTML that is being targeted.

Let’s say we want to target a GraphQL resource that is fetched when visiting a product page organically in the browser. We will provide job information as such:

```json
{
    "source": "universal",
    "url": "https://petstore.swagger.io/",
    "render": "html",
    "browser_instructions": [
        {
            "type": "fetch_resource",
            "filter": "/v2/swagger.json"
        }
    ]
}
```

These instructions will result in a result as such:

```json
{
    "results": [
        {
            "content": "{\"swagger\":\"2.0\",\"info\":{\"description\":\"This is a sample server Petstore server. ...",
            "created_at": "2026-09-17 12:27:43",
            "updated_at": "2026-09-17 12:28:29",
            "page": 1,
            "url": "https://petstore.swagger.io/v2/swagger.json",
            "job_id": "7506328031753955329",
            "status_code": 200
        }
    ],
    "job": {...}
}
```

## List of supported browser instructions <a href="#list-of-supported-browser-instructions" id="list-of-supported-browser-instructions"></a>

### General arguments

All the instructions defined below have a consistent set of arguments. The arguments are as follows.

#### `type` <a href="#type" id="type"></a>

* **Type**: `Enum["click", "input", "scroll", "scroll_to_bottom", "wait", "wait_for_element", "fetch_resource"]`
* **Description:** Browser instruction type.
* **Required**: `true`

#### `timeout_s` <a href="#timeout_s" id="timeout_s"></a>

* **Type**: `int`
* **Description:** How long until action is skipped if not completed in time.
* **Restrictions**: 0 < `timeout_s` <= 60
* **Default value**: 5

#### `wait_time_s` <a href="#wait_time_s" id="wait_time_s"></a>

* **Type**: `int`
* **Description:** How long to wait before executing next action.
* **Restrictions**: 0 < `wait_time_s` <= 60
* **Default value**: 0

#### `on_error` <a href="#on_error" id="on_error"></a>

* **Type**: `Enum["error", "skip"]`
* **Description:** Indicator what to do with instructions in case this instruction fails:
  * `"error"`: Stops the execution of browser instructions.
  * `"skip"`: Continues with the next instruction.
* **Default value**: `"error"`

#### Example with general arguments

```json
{
    "type": "wait_for_element",
    "selector": {
        "type": "text",
        "value": "Load More Items"
    },
    "timeout_s": 5,
    "wait_time_s": 2,
    "on_error": "skip"

}
```

### Instructions <a href="#click" id="click"></a>

#### `click` <a href="#click" id="click"></a>

* **Description**: Clicks an element and wait a set count of seconds.
* **Args:**
  * `type: str = "click"`
  * `selector: dict`
    * `type: Enum["xpath", "css", "text"]`
    * `value: str`

**Example**:

```json
{
    "type": "click",
    "selector": {
        "type": "xpath",
        "value": "//button"
    }
}
```

#### `input` <a href="#input" id="input"></a>

* **Description**: Enters a text into a selected element.
* **Args:**
  * `type: str = "input"`
  * `selector: dict`
    * `type: Enum["xpath", "css", "text"]`
    * `value: str`
  * `value: str`

**Example:**

```json
{
    "type": "input",
    "selector": {
        "type": "xpath",
        "value": "//input"
    },
    "value": "pizza boxes"
}
```

#### `scroll` <a href="#scroll" id="scroll"></a>

* **Description**: Scrolls a set count of pixels.
* **Args:**
  * `type: str = "scroll"`
  * `x: int`
  * `y: int`

**Example:**

```json
{
    "type": "scroll",
    "x": 0,
    "y": 100
}
```

#### `scroll_to_bottom` <a href="#scroll_to_bottom" id="scroll_to_bottom"></a>

* **Description**: Scrolls to bottom for a set count of seconds.
* **Args:**
  * `type: str = "scroll_to_bottom"`

**Example**:

```json
{
    "type": "scroll_to_bottom",
    "timeout_s": 10
}
```

#### `wait` <a href="#wait" id="wait"></a>

* **Description**: Waits a set count of seconds.
* **Args:**
  * `type: str = "wait"`

**Example**:

```json
{
    "type": "wait",
    "wait_time_s": 2
}
```

#### `wait_for_element` <a href="#wait_for_element" id="wait_for_element"></a>

* **Description**: Waits for element to load for a set count of seconds.
* **Args:**
  * `type: str = "wait_for_element"`
  * `selector: dict`
    * `type: Enum["xpath", "css", "text"]`
    * `value: str`

**Example:**

```json
{
    "type": "wait_for_element",
    "selector": {
        "type": "text",
        "value": "Load More Items"
    },
    "timeout_s": 5
}
```

#### `fetch_resource` <a href="#fetch_resource" id="fetch_resource"></a>

{% hint style="warning" %}
The `fetch_resource` instruction must be the final instruction in the browser instructions list; any subsequent instructions will not be executed.
{% endhint %}

* **Description**: Fetches the first occurrence of a Fetch/XHR resource matching the set pattern.
* **Args:**
  * `type: str = "fetch_resource"`
  * `filter: str(RegEx expression)`
  * `on_error: Enum["error", "skip"]`

**Example:**

```json
{
    "type": "fetch_resource",
    "filter": "/graphql/item/"
}
```

### Instruction validation

Any inconsistency in regards to instruction format will result in a `400` status code and a corresponding error message.

For example, payload as such:

```json
{
    "source": "universal",
    "url": "https://www.example.com/",
    "render": "html",
    "browser_instructions": [
        {
            "type": "unsupported-wait",
            "wait_time_s": 5
        }
    ]
}
```

Will result in:

```json
{    
    "errors": {
        "message": "Unsupported action type `unsupported-wait`, choose from 'click,fetch_resource,input,scroll,scroll_to_bottom,wait,wait_for_element'"
    }
}
```

## Troubleshooting <a href="#status-codes" id="status-codes"></a>

### Status codes <a href="#status-codes" id="status-codes"></a>

See our response codes outlined [**here**](/products/web-scraper-api/response-codes.md). Status codes in regards to instructions validation are documented [**here**](#instruction-validation).

### Errors and warnings

If there’s an error or warning resulting from your browsing actions, you’ll find it in the outcome under the keys `browser_instructions_error` or `browser_instructions_warnings`. For instance, if you’ve sent the following browser instructions and the expected `xpath` isn’t located on the page, the result will include a warning.

`browser_instructions`:

```json
[
    {
        "type": "input", 
        "selector": {
            "type": "xpath",
            "value": "//input[@type='search']"
        },
        "value": "oxylabs"
    }
]
```

Results:

```json
{
  "results": [
    {
      "content": "<!doctype html><html>
        Content after executing the instructions      
      </html>",
      "created_at": "2023-10-11 11:35:23",
      "updated_at": "2023-10-11 11:36:08",
      "browser_instructions_warnings": [
        {
          "action_type": "click",
          "msg": "Unable to find selector type `xpath` with value `//input[@type=search]` on the page."
        },
      ],
      "page": 1,
      "url": "https://example.com",
      "job_id": "7117835067442906113",
      "status_code": 200
    }
  ]
}

```

| Possible errors and warnings                                                              |
| ----------------------------------------------------------------------------------------- |
| Unexpected error happened while converting browser instructions to actions.               |
| Unexpected error happened while executing `{action.type}` browser instructions.           |
| Action `{action.type}` timed out.                                                         |
| Unable to find selector type `{selector.type}` with value `{selector.value}` on the page. |


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
