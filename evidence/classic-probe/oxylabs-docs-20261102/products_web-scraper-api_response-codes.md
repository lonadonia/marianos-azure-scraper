> For the complete documentation index, see [llms.txt](https://developers.oxylabs.io/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://developers.oxylabs.io/products/web-scraper-api/response-codes.md).

# Response Codes

Discover Web Scraper API response codes, from success and redirect statuses to parsing results and error explanations.

Web Scraper API reports codes from four different parts of the service, and each shows up in a different place in the response:

* [**API**](/products/web-scraper-api/response-codes.md#api) - HTTP status codes. The status of the HTTP response itself, and the `status_code` of each scraped page in `results`.
* [**Parsers**](/products/web-scraper-api/response-codes.md#parsers) - `parse_status_code` inside the parsed `content` of a result (only when `parse` is `true`).
* [**Cloud storage uploader**](/products/web-scraper-api/response-codes.md#cloud-storage-uploader) – entries in the `statuses` array of the job object, when results are uploaded to your storage.
* [**Sessions**](/products/web-scraper-api/response-codes.md#sessions) -session-related codes.

Some targets have their own codes as well, for example YouTube video states (`11201`–`11211`), which are listed under **Error codes** on the [YouTube Metadata](https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-metadata), [YouTube Subtitles](https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-subtitles) and [YouTube Downloader](https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-downloader) pages.

### API

<table><thead><tr><th width="103.23558797355886">Code</th><th width="279.42175953228775">Status</th><th>Description</th></tr></thead><tbody><tr><td><code>200</code></td><td><code>OK</code></td><td>All went well, you got what you asked for.</td></tr><tr><td><code>202</code></td><td><code>Accepted</code></td><td>Your request was accepted.</td></tr><tr><td><code>204</code></td><td><code>No Content</code></td><td>You are trying to retrieve a job that has not been completed yet.</td></tr><tr><td><code>400</code></td><td><code>Multiple error messages</code></td><td>Wrong request structure: a missing required parameter, an invalid/misspelled value, or a value of the wrong type. The response body has a more specific error message.</td></tr><tr><td><code>401</code></td><td><p><code>Authorization header not provided</code></p><p><code>Invalid authorization header</code></p><p><code>Client not found</code></p></td><td>The authorization header is missing, or your login credentials are incorrect.</td></tr><tr><td><code>403</code></td><td><code>Forbidden</code></td><td>Your account does not have access to this resource.</td></tr><tr><td><code>404</code></td><td><code>Not Found</code></td><td>The job ID you are looking for does not exist or is no longer available.</td></tr><tr><td><code>422</code></td><td><code>Unprocessable Entity</code></td><td>There is something wrong with the payload you posted to us. Make sure it's a valid JSON object.</td></tr><tr><td><code>429</code></td><td><code>Too many requests</code></td><td>You exceeded the rate limit. Please get in touch with your account manager to increase your limits.</td></tr><tr><td><code>500</code></td><td><code>Internal Server Error</code></td><td>We're experiencing some issues on our side. Please try again a bit later. We're probably aware of the issues, but you can give us a shout and report it anyway.</td></tr><tr><td><code>524</code></td><td><code>Timeout</code></td><td>Service unavailable.</td></tr><tr><td><code>612</code></td><td><code>Undefined Internal Error</code></td><td>Something went wrong and we failed the job you submitted. You can try again at no extra cost, as we don't charge you for <code>faulted</code> jobs. If that doesn't work, give us a shout out.</td></tr><tr><td><code>613</code></td><td><code>Faulted After Too Many Retries</code></td><td>Something went wrong, and we failed the job you submitted. You can try again at no extra cost, as we don't charge you for <code>faulted</code> jobs. If that doesn't work, please get in touch with us.</td></tr></tbody></table>

### Parsers

<table><thead><tr><th width="151.673345890383">Code</th><th width="210">Status</th><th>Description</th></tr></thead><tbody><tr><td><code>12000</code></td><td><code>Success</code></td><td>The returned parsed content is full, and there should be no missing or broken fields.</td></tr><tr><td><code>12002</code></td><td><code>Failure</code></td><td>We couldn't parse the page entirely. There may be an issue with the target website changing its HTML structure.</td></tr><tr><td><code>12003</code></td><td><code>Not Supported</code></td><td>The web page you asked us to parse is not supported.</td></tr><tr><td><code>12004</code></td><td><code>Partial Success</code></td><td>We were able to parse the majority of the page. However, a few fields are missing.</td></tr><tr><td><code>12005</code></td><td><code>Partial Success</code></td><td>We were able to parse the majority of the page. However, some fields might have default values because we could not find them in the HTML.</td></tr><tr><td><code>12006</code></td><td><code>Failure</code></td><td>Unexpected error. Let us know you got this response, and we'll check what went wrong.</td></tr><tr><td><code>12007</code></td><td><code>Unknown</code></td><td>Unknown parsed data status. The actual result can range from a complete failure to a total success.</td></tr><tr><td><code>12008</code></td><td><code>Failure</code></td><td>Parsed content is missing.</td></tr><tr><td><code>12009</code></td><td><code>Failure</code></td><td>Product not found. Check the URL you submitted.</td></tr></tbody></table>

### Cloud storage uploader

These codes are returned in the `statuses` array of the job object. A failed upload does not change the job `status`, which stays `done`, so check `statuses` if results do not arrive in your storage.

<table><thead><tr><th width="156.30558722919042">Code</th><th width="208">Status</th><th>Description</th></tr></thead><tbody><tr><td><code>10001</code></td><td><code>Unexpected Exception</code></td><td>Something wrong happened. We probably know about this already and are fixing it. Let us know anyway.</td></tr><tr><td><code>13000</code></td><td><code>Upload Success</code></td><td>All good!</td></tr><tr><td><code>13001</code></td><td><code>Upload Failed</code></td><td>We could not upload job results to your bucket.</td></tr><tr><td><code>13102</code></td><td><code>No Such Path</code></td><td>We could not find a bucket with such a name. Please double-check.</td></tr><tr><td><code>13103</code></td><td><code>Access Denied</code></td><td>Bucket doesn't have the required permissions. To find out how to give us the required access, see <a href="/products/web-scraper-api/features/result-processing-and-storage/cloud-storage.md"><strong>here</strong></a>.</td></tr></tbody></table>

### Sessions

<table><thead><tr><th width="162">Code</th><th width="208">Status</th><th>Description</th></tr></thead><tbody><tr><td><code>15001</code></td><td><code>Session Expired</code></td><td>The session you're trying to use has expired. You can now create another session with the same <code>session_id</code> if you like.</td></tr><tr><td><code>15002</code></td><td><code>Session Failed</code></td><td>Session creation has failed. Please try again.</td></tr><tr><td><code>15003</code></td><td><code>Session Update Failed</code></td><td>Session update has failed. Please try again.</td></tr></tbody></table>


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation by asking a question.

Perform an HTTP GET request on the following URL with the `ask` and `goal` query parameters:

```
GET https://developers.oxylabs.io/products/web-scraper-api/response-codes.md?ask=<question>&goal=<user_goal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is what the user is ultimately trying to achieve, the reason they need the answer. Sharing it helps GitBook give you a better, more relevant answer. A goal is most helpful when it describes the outcome the user wants rather than restating the question. For example, with `ask=how do I create an API token`, a goal like `automate deployments from our CI pipeline` lets GitBook tailor the answer to that use case.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
