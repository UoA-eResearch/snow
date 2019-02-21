import util

def run(BASE_URL, s, args):
    query = "active=true^assigned_to=javascript:getMyAssignments()"
    if "resolved" not in args:
        # don't get resolved tickets by default
        query += "^stateNOT IN3,4,7,6"    
    util.get_and_print_filtered_tasks(query)