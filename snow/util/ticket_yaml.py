#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from .output import fail, emit_json
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
        return fail(ctx, "api_error", r["error"]["message"])
    if not r['result']:
        return fail(ctx, "ticket_not_found", "Ticket not found")
    ticket = r['result'][0]
    p = re.compile(r'^General$', re.M)
    search_result = re.search(p, ticket['comments'])
    if not search_result:
        return fail(ctx, "general_section_not_found",
                    "Could not find 'General' section in comments")

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
        emit_json(output)
    else:
        with open(OUTPUT_FILE, 'r') as orig_request:
            print(orig_request.read())
        print(f"data associated with request {query_number} in file orig_request.yaml")
