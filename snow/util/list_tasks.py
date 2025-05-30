from tabulate import tabulate
import json

FIELDS_TO_DISPLAY = ["number", "opened_at", "short_description", "state", "priority", "assigned_to", "assignment_group", "u_requestor"]

def get_filtered_tasks(ctx, query):
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    url = BASE_URL + "/api/now/table/task"
    fields = FIELDS_TO_DISPLAY
    if ctx["format"] == "json":
        fields.extend(["cmdb_ci", "u_business_service", "subcategory", "u_resolved", "closed_at", "business_duration", "sys_created_on", "sys_updated_on"])
    params = {
        "sysparm_query": query,
        "sysparm_display_value": "all",
        #"sysparm_fields": ",".join(fields)
    }
    r = s.get(url, params=params)
    r = r.json()
    if 'error' in r:
        print(r["error"]["message"])
        return
    return r["result"]

def get_and_print_filtered_tasks(ctx, query):
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    url = BASE_URL + "/api/now/table/task"
    fields = FIELDS_TO_DISPLAY
    if ctx["format"] == "json":
        fields.extend(["cmdb_ci", "u_business_service", "subcategory", "u_resolved", "closed_at", "business_duration", "sys_created_on", "sys_updated_on"])
    params = {
        "sysparm_query": query,
        "sysparm_display_value": "true",
        "sysparm_fields": ",".join(fields)
    }
    r = s.get(url, params=params)
    r = r.json()
    if 'error' in r:
        print(r["error"]["message"])
        return
    results = r['result']

    if ctx["format"] == "json":
        print(json.dumps(results, indent=4, sort_keys=True))
        return

    filtered_results = []
    for r in results:
        filtered_result = []
        for key in FIELDS_TO_DISPLAY:
            value = r.get(key)
            if type(value) is dict:
                value = value["display_value"]
            filtered_result.append(value)
        filtered_results.append(filtered_result)
    print(tabulate(filtered_results, headers=FIELDS_TO_DISPLAY))
