from pprint import pprint
import sys
import editor

def run(BASE_URL, s, args):
    bits = args.split()
    number = bits[0]
    if sys.stdin.isatty():
        if len(bits) > 1:
            message = " ".join(bits[1:])
        else:
            message = editor.edit()
    else:
        message = sys.stdin.read()
    query = "number=" + number
    url = BASE_URL + "/api/now/table/task"
    params = {
        "sysparm_query": query,
        "sysparm_display_value": "true",
        "sysparm_fields": "sys_id"
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
    
    sys_id = ticket["sys_id"]

    data = {
        "comments": message
    }
    url = BASE_URL + "/api/now/table/task/" + sys_id
    r = s.patch(url, json = data, headers = {"X-no-response-body": "true"})
    if r.status_code == 204:
        print("Comment posted successfully")
    else:
        print("Unable to post")