def get_ticket(ctx, ticket_number):
    BASE_URL = ctx["BASE_URL"]
    s = ctx["s"]
    query = "number=" + ticket_number
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
