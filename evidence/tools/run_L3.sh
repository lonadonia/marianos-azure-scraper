#!/usr/bin/env bash
# TEST_PLAN_180 section 7: one submission per hypothesis, sequential, no retry here.
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
send L19 "/pl/cold-cereal/0300100001?priceBuckets=5-0-7-49" "the price bucket written with the slug the page state itself gives narrows a listing above the window (L14 used the name)"
send L20 "/pl/cold-cereal/0300100001?brandName=General%20Mills" "the brand filter proven on /search (L8) narrows a /pl/ listing above the window"
$V -X utf8 budget180.py status | tail -3
