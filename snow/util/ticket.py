from .output import fail, EXIT_ERROR


def find_ticket(ctx, ticket_number, params_extra=None):
    """Look a ticket up by number.

    :return: (ticket, None) on success, or (None, (error_code, message))
    """
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    query = "number=" + ticket_number
    url = BASE_URL + "/api/now/table/task"
    params = {
        "sysparm_query": query,
        "sysparm_display_value": "true",
    }
    if params_extra:
        params.update(params_extra)
    r = s.get(url, params=params)
    r = r.json()
    if 'error' in r:
        return None, ("api_error", r["error"]["message"])
    if not r['result']:
        return None, ("ticket_not_found", "Ticket not found")
    return r['result'][0], None


def get_ticket(ctx, ticket_number):
    ticket, err = find_ticket(ctx, ticket_number)
    if err:
        if ctx.get("api"):
            # Library mode (util/api.py): historical behaviour.
            print(err[1])
            return None
        fail(ctx, err[0], err[1], EXIT_ERROR)
    return ticket


def get_comments_for_ticket(ctx, sys_id):
    '''
    Gets all comments and work notes for a given ticket

    :return: list of comments
    '''
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    url = BASE_URL + "/api/now/table/sys_journal_field"
    params = {
        'sysparm_query': f"element_id={sys_id}^ORDERBYsys_created_on",
        'sysparm_display_value': 'all'
    }
    r = s.get(url, params=params)
    r = r.json()
    return r['result']

def get_emails_for_ticket(ctx, sys_id):
    '''
    Gets records of all emails sent in relation to a ticket

    :return: list of email logs
    '''
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    url = BASE_URL + "/api/now/table/sys_email"
    params = {
        'sysparm_query': f"instance={sys_id}^ORDERBYsys_created_on",
        'sysparm_display_value': 'all'
    }
    r = s.get(url, params=params)
    r = r.json()
    return r['result']

def get_user_by_sys_id(ctx, sys_id):
    '''Gets user info from Service Now from sys_user table based on sys_id

    :param sys_id: ServiceNow sys_id of user
    :return: user object if sys_id is found else {}
    '''
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    url = BASE_URL + "/api/now/table/sys_user"
    params = {'sysparm_query': f'sys_id={sys_id}',
                    'sysparm_limit': '1'}
    r = s.get(url, params=params)
    r = r.json()
    r = r['result']
    return r[0] if len(r) > 0 else {}
