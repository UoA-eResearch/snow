from pprint import pprint
from bs4 import BeautifulSoup

fields = [
    ("Ticket details", [
        "number",
        "short_description",
        "u_requestor",
        "u_contact_details",
        "u_affected_contact",
        "user.user_name",
        "u_affiliation",
        "location",
        "u_contact_support_location",
        "watch_list"
    ]),
    ("Prioritisation", [
        "impact",
        "urgency",
        "priority",
        "u_customer_promise"
    ]),
    ("Request status", [
        "state"
    ]),
    ("Assignment status", [
        "assignment_group",
        "assigned_to",
        "u_third_party_reference"
    ]),
    ("Classification", [
        "subcategory",
        "cmdb_ci",
        "u_business_service"
    ]),
    ("Approval", [
        "approval",
    ]),
    ("Comments", [
        "comments"
    ]),
    ("Work notes", [
        "work_notes"
    ])

]

sep = "=" * 10

def run(BASE_URL, s, args):
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
    user = s.get(ticket['u_requestor']['link']).json()["result"]
    for heading, subfields in fields:
        print("\n{}\n{}\n".format(heading, sep))
        for sf in subfields:
            if "." in sf:
                sf = sf.split(".")[-1]
                val = user[sf]
            else:
                val = ticket[sf]
            if type(val) is dict:
                val = val["display_value"]
            if sf == "comments":
                soup = BeautifulSoup(val, features="lxml")
                print(soup.get_text().encode("utf-8"))
            elif sf == "work_notes":
                print(val)
            else:
                print("{} = {}".format(sf, val))