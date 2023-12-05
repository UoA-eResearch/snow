from .ticket import get_ticket


def get(ctx, ticket_number, property):
    ticket = get_ticket(ctx, ticket_number)
    ticket_property = ticket[property]
    if not ctx["api"]:
        print(ticket_property)
    return ticket_property


def patch(ctx, ticket_number, property, value):
    ticket = get_ticket(ctx, ticket_number)
    sys_id = ticket["sys_id"]
    data = {
        property: value
    }

    url = ctx["BASE_URL"] + "/api/now/table/task/" + sys_id
    s = ctx["s"]
    r = s.patch(url, json=data, headers={"X-no-response-body": "true"})
    if r.status_code == 204:
        return "Success"
    else:
        return r.json()["error"]
