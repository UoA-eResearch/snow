#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import json
import re
OUTPUT_FILE='orig_request.yaml'

def extract(ctx, args):
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    query = "number=" + args
    url = BASE_URL + "/api/now/table/task"
    params = {
        "sysparm_query": query,
        "sysparm_display_value": "true",
    }
    r = s.get(url, params=params)
    r = r.json()
    if 'error' in r:
        print(r["error"]["message"])
        return
    if not r['result']:
        print("Ticket not found")
        return
    ticket = r['result'][0]
    p = re.compile(r'^General$', re.M)
    ticket_start_position = re.search(p, ticket['comments']).start()
    with open(OUTPUT_FILE,'w') as orig_request:
        orig_request.write(ticket['comments'][ticket_start_position:])
    query_number = params['sysparm_query'].split('=')[1]
    with open(OUTPUT_FILE, 'r') as orig_request:
        print(orig_request.read())
    print(f"data associated with request {query_number} in file orig_request.yaml")

