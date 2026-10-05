"""Assignment and watch list commands: assign_to_me, add_to_watchlist."""
from .output import fail, emit_json, EXIT_ERROR


def _value(field):
    """Raw value of a field fetched with sysparm_display_value=all."""
    if isinstance(field, dict):
        return field.get("value") or ""
    return field or ""


def _display(field):
    if isinstance(field, dict):
        return field.get("display_value") or ""
    return field or ""


def _get_users(ctx, query, limit):
    s = ctx["s"]
    url = ctx["BASE_URL"] + "/api/now/table/sys_user"
    params = {
        "sysparm_query": query,
        "sysparm_fields": "sys_id,user_name,name,email",
        "sysparm_limit": str(limit),
    }
    r = s.get(url, params=params).json()
    if 'error' in r:
        return fail(ctx, "api_error", r["error"]["message"])
    return r["result"]


def get_current_user(ctx):
    """The logged-in user's sys_user record (sys_id, user_name, name).

    my_work relies on the server-side getMyAssignments(); here the sys_id
    itself is needed, so ask for the record of gs.getUserID().
    """
    users = _get_users(ctx, "sys_id=javascript:gs.getUserID()", 1)
    if not users:
        return fail(ctx, "user_not_found", "Could not resolve the logged-in user")
    return users[0]


def find_user(ctx, user):
    """Resolve a UPI/username or an email address to a sys_user record."""
    field = "email" if "@" in user else "user_name"
    if not user.strip() or "^" in user:
        # "^" would splice extra terms into the encoded query.
        return fail(ctx, "user_not_found", "No user with %s %s" % (field, user),
                    extra={"ok": False, "user": user})
    users = _get_users(ctx, "%s=%s" % (field, user), 2)
    if not users:
        return fail(ctx, "user_not_found", "No user with %s %s" % (field, user),
                    extra={"ok": False, "user": user})
    if len(users) > 1:
        return fail(ctx, "user_ambiguous", "More than one user with %s %s" % (field, user),
                    extra={"ok": False, "user": user})
    return users[0]


def _read_ticket(ctx, number, fields):
    """Fetch a few raw+display fields of a ticket from the task table."""
    s = ctx["s"]
    url = ctx["BASE_URL"] + "/api/now/table/task"
    params = {
        "sysparm_query": "number=" + number,
        "sysparm_display_value": "all",
        "sysparm_fields": ",".join(["sys_id", "sys_class_name"] + fields),
    }
    r = s.get(url, params=params).json()
    if 'error' in r:
        return fail(ctx, "api_error", r["error"]["message"],
                    extra={"ok": False, "ticket_number": number})
    if not r['result']:
        return fail(ctx, "ticket_not_found", "Ticket not found",
                    extra={"ok": False, "ticket_number": number})
    return r['result'][0]


def _patch_ticket(ctx, number, ticket, data):
    """PATCH the record through its own table (as `resolve` does), so the
    child table's business rules and choice lists apply. Fails on anything
    but 204."""
    table = _value(ticket.get("sys_class_name")) or "task"
    url = ctx["BASE_URL"] + "/api/now/table/" + table + "/" + _value(ticket["sys_id"])
    r = ctx["s"].patch(url, json=data, headers={"X-no-response-body": "true"})
    if r.status_code == 204:
        return table
    try:
        sn_error = r.json()["error"]
    except Exception:
        sn_error = {"message": "HTTP %d" % r.status_code, "detail": r.text[:500]}
    message = sn_error.get("message") if isinstance(sn_error, dict) else str(sn_error)
    return fail(ctx, "update_failed", message or "HTTP %d" % r.status_code, EXIT_ERROR,
                extra={
                    "ok": False,
                    "ticket_number": number,
                    "table": table,
                    "http_status": r.status_code,
                    "detail": sn_error,
                })


def assign_to_me(ctx, number, if_unassigned=False):
    me = get_current_user(ctx)
    my_id = me["sys_id"]
    my_name = me.get("name") or me.get("user_name")

    # The read of assigned_to and the PATCH are back to back: no other
    # request happens in between, to keep the race window as small as the
    # Table API allows (it has no conditional update).
    ticket = _read_ticket(ctx, number, ["assigned_to"])
    current = _value(ticket.get("assigned_to"))

    if current == my_id:
        already_mine = True
    elif current and if_unassigned:
        holder = _display(ticket.get("assigned_to")) or current
        return fail(ctx, "already_assigned",
                    "%s is already assigned to %s" % (number, holder),
                    extra={"ok": False, "ticket_number": number, "assigned_to": holder})
    else:
        already_mine = False
        _patch_ticket(ctx, number, ticket, {"assigned_to": my_id})

    if ctx["format"] == "json":
        emit_json({
            "ok": True,
            "ticket_number": number,
            "assigned_to": my_name,
            "already_mine": already_mine,
        })
    elif already_mine:
        print("%s is already assigned to you" % number)
    else:
        print("Assigned %s to %s" % (number, my_name))
    return True


def add_to_watchlist(ctx, number, user):
    target = find_user(ctx, user)
    user_id = target["sys_id"]
    user_name = target.get("user_name") or user

    ticket = _read_ticket(ctx, number, ["watch_list", "parent"])
    watched = number
    # A catalog task's own watch list is not on its form and is not emailed
    # the customer comments: the request item's is (as with the email
    # records, see `snow email_check`). So a catalog task's watcher goes on its
    # parent RITM. Without a parent, the task's own list is all there is.
    parent = _display(ticket.get("parent"))
    if _value(ticket.get("sys_class_name")) == "sc_task" and parent:
        watched = parent
        ticket = _read_ticket(ctx, watched, ["watch_list"])
    # watch_list is a comma-separated list of sys_user sys_ids (plain
    # email addresses are allowed too).
    watchers = [w.strip() for w in _value(ticket.get("watch_list")).split(",") if w.strip()]

    already_watching = user_id in watchers
    if not already_watching:
        _patch_ticket(ctx, watched, ticket, {"watch_list": ",".join(watchers + [user_id])})

    via = "" if watched == number else " (the request item of %s)" % number
    if ctx["format"] == "json":
        emit_json({
            "ok": True,
            "ticket_number": number,
            "watch_list_on": watched,
            "user": user_name,
            "user_sys_id": user_id,
            "already_watching": already_watching,
        })
    elif already_watching:
        print("%s is already watching %s%s" % (user_name, watched, via))
    else:
        print("Added %s to the watch list of %s%s" % (user_name, watched, via))
    return True
