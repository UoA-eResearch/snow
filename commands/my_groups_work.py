from pprint import pprint
from tabulate import tabulate

FIELDS_TO_DISPLAY = ["number", "opened_at", "short_description", "state", "priority", "severity", "category", "assigned_to", "assignment_group", "u_requestor"]

def run(BASE_URL, s, args):
    query = "assignment_group=javascript:getMyGroups()^active=true^assigned_toANYTHING^state!=-5"
    url = BASE_URL + "/api/now/v1/table/incident"
    params = {
        "sysparm_query": query,
        "sysparm_display_value": "true"
    }
    r = s.get(url, params=params)
    r = r.json()
    if 'error' in r:
        print(r['error']['message'])
        return
    results = r['result']
    #pprint(results)
    filtered_results = []
    for r in results:
        filtered_result = []
        for key in FIELDS_TO_DISPLAY:
            value = r[key]
            if type(value) is dict:
                value = value["display_value"]
            filtered_result.append(value)
        filtered_results.append(filtered_result)
    print(tabulate(filtered_results, headers=FIELDS_TO_DISPLAY))