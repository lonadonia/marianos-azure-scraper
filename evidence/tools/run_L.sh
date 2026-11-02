#!/usr/bin/env bash
# TEST_PLAN_180 section 2, stage L: one submission per hypothesis, sequential, no retry here.
cd /c/m6/tools || exit 1
export PSYCOPG_IMPL=python MSYS_NO_PATHCONV=1
V=/c/m5/wt/headless/marianos-azure-headless/.venv/Scripts/python.exe
P="$V -X utf8 probe180.py send"
S=53100502
F=pickup
B='https://www.marianos.com'
$P L2 /v1/scrape/marianos "{\"url\":\"$B/pl/cereal-granola/03001\",\"store_id\":\"$S\",\"fulfillment_type\":\"$F\"}" "the /pl/ listing page is still refused at the new store and fulfillment" 2>&1 | cut -c1-1500
$P L3 /v1/scrape/marianos/product "{\"query\":\"0001600012254\",\"store_id\":\"$S\",\"fulfillment_type\":\"$F\"}" "the product endpoint is still refused at the new store and fulfillment" 2>&1 | cut -c1-1500
$P L4 /v1/scrape/marianos "{\"url\":\"$B/q/cereal\",\"store_id\":\"$S\",\"fulfillment_type\":\"$F\"}" "/q/:slug (retailer route table) is a server-rendered route with its own product list" 2>&1 | cut -c1-1500
$P L5 /v1/scrape/marianos "{\"url\":\"$B/pb/general-mills/cereal-granola/03001\",\"store_id\":\"$S\",\"fulfillment_type\":\"$F\"}" "/pb/:brandSlug/:taxonomySlug/:taxonomyId (retailer route table) is served" 2>&1 | cut -c1-1500
$P L6 /v1/scrape/marianos "{\"url\":\"$B/search?page=2&fulfillment=all\",\"store_id\":\"$S\",\"fulfillment_type\":\"$F\"}" "the retailer's failed request in the page state shows the page.offset its server asked for page=2" 2>&1 | cut -c1-1500
$P L7 /v1/scrape/marianos/search "{\"query\":\"cereal\",\"price_range\":\"2.00-5.00\",\"store_id\":\"$S\",\"fulfillment_type\":\"$F\"}" "the documented price_range form acts with a non-zero lower bound" 2>&1 | cut -c1-1500
$P L8 /v1/scrape/marianos/search "{\"query\":\"cereal\",\"brand\":\"General Mills\",\"store_id\":\"$S\",\"fulfillment_type\":\"$F\"}" "the brand filter narrows the total at this store and fulfillment" 2>&1 | cut -c1-1500
$V -X utf8 budget180.py status | tail -4
