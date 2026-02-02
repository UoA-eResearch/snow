#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import json
import re
OUTPUT_FILE = 'orig_request.yaml'


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
        error_msg = r["error"]["message"]
        if ctx["format"] == "json":
            print(json.dumps({"error": error_msg}))
        else:
            print(error_msg)
        return
    if not r['result']:
        msg = "Ticket not found"
        if ctx["format"] == "json":
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return
    ticket = r['result'][0]
    p = re.compile(r'^General$', re.M)
    search_result = re.search(p, ticket['comments'])
    if not search_result:
        msg = "Could not find 'General' section in comments"
        if ctx["format"] == "json":
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return

    ticket_start_position = search_result.start()
    yaml_content = ticket['comments'][ticket_start_position:]

    with open(OUTPUT_FILE, 'w') as orig_request:
        orig_request.write(yaml_content)

    query_number = params['sysparm_query'].split('=')[1]

    if ctx["format"] == "json":
        output = {
            "ticket_number": query_number,
            "file": OUTPUT_FILE,
            "content": yaml_content
        }
        print(json.dumps(output, indent=4))
    else:
        with open(OUTPUT_FILE, 'r') as orig_request:
            print(orig_request.read())
        print(f"data associated with request {query_number} in file orig_request.yaml")
