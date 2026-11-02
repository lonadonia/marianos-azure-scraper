#!/usr/bin/env bash
# TEST_PLAN_180 section 6: one submission per hypothesis, sequential, no retry here.
cd /c/m6/tools || exit 1
export PSYCOPG_IMPL=python MSYS_NO_PATHCONV=1
V=/c/m5/wt/headless/marianos-azure-headless/.venv/Scripts/python.exe
P="$V -X utf8 probe180.py send"
S=53100502
F=pickup
B='https://www.marianos.com'
send() { # id url hypothesis
  $P "$1" /v1/scrape/marianos "{\"url\":\"$B$2\",\"store_id\":\"$S\",\"fulfillment_type\":\"$F\"}" "$3" 2>&1 | grep -E '"(id|seconds|status|kind|charged|request_id|total|available|page|location_id|modality|state_products|chars|message)"|ERR' | cut -c1-260
  date -u
}
send L11 "/pl/cold-cereal/0300100001" "a child listing named by the retailer's productsInfo.departments is served"
send L12 "/pl/cereal-granola/03001?page=11" "the last page inside the 250 window answers"
send L13 "/pl/cereal-granola/03001?page=12" "what the source does past its window"
send L14 "/pl/cold-cereal/0300100001?priceBuckets=5.0-7.49" "the retailer's price bucket, by its facet name, narrows a listing above the window"
send L15 "/pl/breakfast/03" "a department-level listing (the CSV's own /pl/ form with a 2-digit id) gives the department's tree and counts"
send L16 "/p/general-mills-gluten-free-lucky-charms-with-marshmallows-cereal/0001600012399" "a product page is served with store and pickup context"
send L18 "/search?query=cereal&searchType=default_search&page=2" "whether /search repeats page 1 at this store and fulfillment (the /pl/ route does not)"
$V -X utf8 budget180.py status | tail -3
