#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import json
import re

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
    with open('orig_request.yaml','w') as orig_request:
        orig_request.write(ticket['comments'][ticket_start_position:])
    print(ticket["comments"])
    print(json.dumps(ticket, indent=4, sort_keys=True))

# vim: fenc=utf-8: ft=python:sw=4:et:nu:fdm=indent:fdn=1:syn=python

