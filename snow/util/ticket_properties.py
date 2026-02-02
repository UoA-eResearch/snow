import json
from .ticket import get_ticket


def get(ctx, ticket_number, property):
    ticket = get_ticket(ctx, ticket_number)
    if not ticket:
        if ctx["format"] == "json":
            print(json.dumps({"error": "Ticket not found"}))
        return None

    ticket_property = ticket[property]
    if not ctx["api"]:
        if ctx["format"] == "json":
            output = {
                "ticket_number": ticket_number,
                "property": property,
                "value": ticket_property
            }
            print(json.dumps(output, indent=4))
        else:
            print(ticket_property)
    return ticket_property


def patch(ctx, ticket_number, property, value):
    ticket = get_ticket(ctx, ticket_number)
    if not ticket:
        if ctx["format"] == "json":
            print(json.dumps({"error": "Ticket not found"}))
        return {"error": "Ticket not found"}

    sys_id = ticket["sys_id"]
    data = {
        property: value
    }

    url = ctx["BASE_URL"] + "/api/now/table/task/" + sys_id
    s = ctx["s"]
    r = s.patch(url, json=data, headers={"X-no-response-body": "true"})

    if r.status_code == 204:
        result = "Success"
    else:
        result = r.json()["error"]

    if ctx["format"] == "json":
        output = {
            "ticket_number": ticket_number,
            "property": property,
            "result": result
        }
        print(json.dumps(output, indent=4))

    return result
