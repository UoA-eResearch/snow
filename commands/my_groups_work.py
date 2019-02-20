from pprint import pprint
from tabulate import tabulate

FIELDS_TO_DISPLAY = ["number", "opened_at", "short_description", "state", "priority", "severity", "category", "sys_created_by"]

def run(BASE_URL, s, args):
    r = s.get(BASE_URL + "/api/now/v1/table/incident?sysparm_query=assignment_group=javascript:getMyGroups()^active=true^assigned_to=^state!=-5")
    r = r.json()
    if 'error' in r:
        print(r['error']['message'])
        return
    results = r['result']
    filtered_results = []
    for r in results:
        filtered_results.append([r[key] for key in FIELDS_TO_DISPLAY])
    print(tabulate(filtered_results, headers=FIELDS_TO_DISPLAY))